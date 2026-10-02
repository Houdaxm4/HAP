"""Tools the HAP Analyst agent can call: read-only analysis tools plus allow-listed online research.

Every tool is bound to ONE analysis (the toolbox is constructed with its id), so the
model can never read another analysis. Tools only read persisted artifacts; nothing
here writes, runs the pipeline, approves a review gate, or touches workbooks.
"""

from __future__ import annotations

import json
import re
from typing import Any

from research.policy import research_enabled
from research.toolbox import RESEARCH_TOOL_NAMES, RESEARCH_TOOL_SCHEMAS, ResearchToolbox
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.output_service import OutputService

MAX_RESULT_CHARS = 12_000
MAX_JSON_BYTES = 12 * 1024 * 1024  # never load bigger artifacts into memory for the agent
READABLE_SUFFIXES = {".json", ".md", ".txt", ".csv"}
_TOKEN_RE = re.compile(r"\[(\d+)\]|\[\"([^\"]+)\"\]|([^.\[\]]+)")

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_analysis_overview",
        "description": (
            "Overview of this analysis: company, ticker, analysis type, status, pipeline stage and any "
            "pipeline error, recommendation and scores (if computed), and the most recent decision-log "
            "entries. Call this first for most questions."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "list_artifacts",
        "description": (
            "List the output artifacts stored for this analysis (reports, JSON results, workbooks) with sizes. "
            "Only .json, .md, .txt and .csv artifacts can be read with the other tools."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "inspect_artifact",
        "description": (
            "Navigate a JSON artifact. With no `path` it returns the top-level structure (keys, types, sizes). "
            "With a `path` such as `valuation.fair_value` or `entries[3].cell_ref` it returns that node: small "
            "values in full, large ones summarised so you can drill down. Arrays accept `offset` and `limit`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Artifact file name, e.g. final_recommendation_report.json"},
                "path": {"type": "string", "description": "Dotted/bracketed path inside the JSON. Empty = root."},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_artifact",
        "description": (
            "Case-insensitive search of keys and string/number values inside one JSON artifact. Returns the "
            "path and a short value for each hit. Use it to find a metric, label or flag when you do not know "
            "where it lives."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "query": {"type": "string", "minLength": 2},
                "max_hits": {"type": "integer", "minimum": 1, "maximum": 40},
            },
            "required": ["name", "query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_text_artifact",
        "description": "Read a .md, .txt or .csv artifact (for example a certification or review note).",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 500, "maximum": MAX_RESULT_CHARS},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_cell_provenance",
        "description": (
            "Explain where one workbook cell came from (source filing, rule, formula, confidence). "
            "`cell_ref` looks like `Income Statement!B5`."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"cell_ref": {"type": "string", "minLength": 3}},
            "required": ["cell_ref"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_analyst_review_state",
        "description": (
            "Pending analyst-judgment items for New Company analyses: the estimated lease discount rate, the "
            "R&D useful-life decision, and the workflow run state. You can explain these but never approve or "
            "change them."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
]


class ToolError(Exception):
    """A tool call failed in a way the model should be told about (returned as is_error)."""


def _clip(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...[truncated, {len(text) - limit} more characters]"


def _type_name(value: Any) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _size(value: Any) -> int | None:
    return len(value) if isinstance(value, (dict, list, str)) else None


def _short(value: Any, depth: int = 0) -> Any:
    """A compact, bounded rendering of any JSON value."""
    if isinstance(value, str):
        return value if len(value) <= 240 else value[:240] + f"...(+{len(value) - 240} chars)"
    if isinstance(value, dict):
        if depth >= 2:
            return f"<object, {len(value)} keys>"
        items = list(value.items())[:12]
        out = {str(k): _short(v, depth + 1) for k, v in items}
        if len(value) > 12:
            out["..."] = f"+{len(value) - 12} more keys"
        return out
    if isinstance(value, list):
        if depth >= 2:
            return f"<array, {len(value)} items>"
        out_list = [_short(v, depth + 1) for v in value[:5]]
        if len(value) > 5:
            out_list.append(f"...+{len(value) - 5} more items")
        return out_list
    return value


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, indent=1)


def parse_path(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for index, quoted, bare in _TOKEN_RE.findall(path or ""):
        if index != "":
            tokens.append(int(index))
        elif quoted:
            tokens.append(quoted)
        elif bare:
            tokens.append(bare)
    return tokens


def resolve_path(data: Any, path: str) -> Any:
    node = data
    walked: list[str] = []
    for token in parse_path(path):
        walked.append(str(token))
        if isinstance(node, dict) and isinstance(token, str) and token in node:
            node = node[token]
        elif isinstance(node, dict) and isinstance(token, int) and str(token) in node:
            node = node[str(token)]
        elif isinstance(node, list) and isinstance(token, int) and -len(node) <= token < len(node):
            node = node[token]
        else:
            hint = ""
            if isinstance(node, dict):
                hint = f" Available keys: {list(node.keys())[:25]}"
            elif isinstance(node, list):
                hint = f" Array length is {len(node)}."
            raise ToolError(f"Path not found at '{'.'.join(walked)}'.{hint}")
    return node


def describe_node(node: Any, offset: int = 0, limit: int = 20) -> str:
    """Render a JSON node for the model: full if small, a navigable summary if large."""
    rendered = _dump(node)
    if len(rendered) <= 3500:
        return rendered
    if isinstance(node, dict):
        keys = [{"key": k, "type": _type_name(v), "size": _size(v)} for k, v in list(node.items())[:80]]
        summary: dict[str, Any] = {"type": "object", "key_count": len(node), "keys": keys}
        if len(node) > 80:
            summary["note"] = "Only the first 80 keys are listed; use search_artifact for the rest."
        return _dump(summary)
    if isinstance(node, list):
        window = node[offset : offset + limit]
        summary = {
            "type": "array",
            "length": len(node),
            "offset": offset,
            "items": [{"index": offset + i, "value": _short(item)} for i, item in enumerate(window)],
        }
        if offset + limit < len(node):
            summary["next_offset"] = offset + limit
        return _dump(summary)
    return _clip(rendered)


def search_json(data: Any, query: str, max_hits: int) -> list[dict[str, Any]]:
    needle = query.lower()
    hits: list[dict[str, Any]] = []
    stack: list[tuple[str, Any]] = [("", data)]
    while stack and len(hits) < max_hits:
        path, node = stack.pop()
        if isinstance(node, dict):
            for key, value in reversed(list(node.items())):
                child = f"{path}.{key}" if path else str(key)
                if needle in str(key).lower():
                    hits.append({"path": child, "match": "key", "value": _short(value)})
                    if len(hits) >= max_hits:
                        break
                stack.append((child, value))
        elif isinstance(node, list):
            for i in range(len(node) - 1, -1, -1):
                stack.append((f"{path}[{i}]", node[i]))
        elif isinstance(node, (str, int, float)) and not isinstance(node, bool):
            if needle in str(node).lower():
                hits.append({"path": path, "match": "value", "value": _short(node)})
    return hits


class AnalystToolbox:
    """Executes the read-only tools for a single analysis."""

    def __init__(self, analysis_service: AnalysisService, output_service: OutputService, analysis_id: str) -> None:
        self.analysis_service = analysis_service
        self.output_service = output_service
        self.analysis_id = analysis_id
        # Raises AnalysisNotFoundError for unknown or unsafe ids.
        self.analysis = analysis_service.get(analysis_id)

    # ---- dispatch -------------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any] | None) -> tuple[str, bool]:
        """Run a tool. Returns (text, is_error); never raises into the agent loop."""
        args = args if isinstance(args, dict) else {}
        if name in RESEARCH_TOOL_NAMES:
            if not research_enabled():
                return "Online research is switched off (HAP_RESEARCH_ENABLED=0).", True
            return self._research().execute(name, args)
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return f"Unknown tool '{name}'.", True
        try:
            return _clip(handler(**args)), False
        except ToolError as exc:
            return str(exc), True
        except TypeError as exc:
            return f"Invalid arguments for {name}: {exc}", True
        except (OSError, ValueError, AnalysisNotFoundError) as exc:
            return f"{name} failed: {exc}", True

    # ---- helpers --------------------------------------------------------------------------

    def _research(self) -> ResearchToolbox:
        if getattr(self, "_research_toolbox", None) is None:
            record = self.analysis.to_dict()
            self._research_toolbox = ResearchToolbox(
                ticker=self.analysis.ticker,
                company=self.analysis.company,
                cik=record.get("cik"),
                evidence_log=self.output_service.analysis_output_dir(self.analysis_id) / "research_evidence.jsonl",
            )
        return self._research_toolbox

    def _artifact_file(self, name: str, *, suffixes: set[str]) -> Any:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or name in {".", ".."}:
            raise ToolError("Invalid artifact name.")
        path = self.output_service.artifact_path(self.analysis_id, name)
        if path.suffix.lower() not in READABLE_SUFFIXES or path.suffix.lower() not in suffixes:
            raise ToolError(f"'{name}' is not a readable artifact type here (allowed: {sorted(suffixes)}).")
        if not path.is_file():
            available = [a["name"] for a in self.output_service.list_artifacts(self.analysis_id)]
            raise ToolError(f"Artifact '{name}' not found. Available: {available[:60]}")
        return path

    def _load_json(self, name: str) -> Any:
        path = self._artifact_file(name, suffixes={".json"})
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ToolError(f"'{name}' is too large to load ({path.stat().st_size // 1024} KB).")
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    # ---- tools ----------------------------------------------------------------------------

    def _tool_get_analysis_overview(self) -> str:
        from models.api_responses import build_summary_response, load_engine_result_dict

        analysis = self.analysis_service.get(self.analysis_id)
        engine_result = load_engine_result_dict(self.output_service, analysis)
        summary = build_summary_response(analysis, engine_result).model_dump()
        record = analysis.to_dict()
        log = record.get("decision_log") or []
        payload = {
            "summary": summary,
            "cik": record.get("cik"),
            "files": {k: (v or {}).get("filename") for k, v in (record.get("files") or {}).items() if v},
            "pipeline": record.get("pipeline"),
            "decision_log_total": len(log),
            "decision_log_latest": log[-15:],
            "has_engine_result": engine_result is not None,
        }
        return _dump(payload)

    def _tool_list_artifacts(self) -> str:
        artifacts = self.output_service.list_artifacts(self.analysis_id)
        rows = [
            {
                "name": a["name"],
                "kb": round(a["size_bytes"] / 1024, 1),
                "readable": any(a["name"].lower().endswith(s) for s in READABLE_SUFFIXES),
            }
            for a in artifacts
        ]
        return _dump({"count": len(rows), "artifacts": rows})

    def _tool_inspect_artifact(self, name: str, path: str = "", offset: int = 0, limit: int = 20) -> str:
        data = self._load_json(name)
        node = resolve_path(data, path or "")
        return describe_node(node, offset=max(int(offset), 0), limit=min(max(int(limit), 1), 50))

    def _tool_search_artifact(self, name: str, query: str, max_hits: int = 15) -> str:
        if not isinstance(query, str) or len(query.strip()) < 2:
            raise ToolError("query must be at least 2 characters.")
        data = self._load_json(name)
        hits = search_json(data, query.strip(), min(max(int(max_hits), 1), 40))
        if not hits:
            return f"No matches for '{query}' in {name}."
        return _dump({"query": query, "artifact": name, "hit_count": len(hits), "hits": hits})

    def _tool_read_text_artifact(self, name: str, max_chars: int = 8000) -> str:
        path = self._artifact_file(name, suffixes={".md", ".txt", ".csv"})
        limit = min(max(int(max_chars), 500), MAX_RESULT_CHARS)
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            text = handle.read(limit + 1)
        return text if len(text) <= limit else text[:limit] + "\n...[truncated]"

    def _tool_get_cell_provenance(self, cell_ref: str) -> str:
        report = self._load_json("provenance_report.json")
        wanted = (cell_ref or "").replace("%21", "!").strip()
        for entry in report.get("entries", []):
            if entry.get("cell_ref") == wanted:
                return _dump(entry)
        near = [e.get("cell_ref") for e in report.get("entries", []) if wanted.lower() in str(e.get("cell_ref", "")).lower()]
        raise ToolError(f"No provenance for '{wanted}'." + (f" Similar refs: {near[:10]}" if near else ""))

    def _tool_get_analyst_review_state(self) -> str:
        state: dict[str, Any] = {}
        for filename, key in (
            ("lease_rate_review.json", "lease_rate_review"),
            ("rd_useful_life_decision.json", "rd_useful_life_decision"),
            ("new_company_run_state.json", "run_state"),
        ):
            try:
                state[key] = self.output_service.read_json(self.analysis_id, filename)
            except FileNotFoundError:
                state[key] = None
        return _dump(state)
