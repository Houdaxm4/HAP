"use client";

import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  chatWithAnalyst,
  getBudget,
  submitFeedback,
  type BudgetStatus,
  type ChatReplyDto,
  type ChatTurn,
} from "@/lib/api";
import { getAnalystLabel } from "@/lib/app_config";

type AnalystChatProps = {
  analysisId: string;
};

type UiTurn = ChatTurn & {
  tools?: { name: string; ok: boolean }[];
  rating?: "up" | "down";
  source?: ChatReplyDto["source"];
  needsClaude?: boolean;
  estimatedCost?: number | null;
  /** The conversation that produced this turn, so "Ask Claude" can resend it. */
  askedWith?: ChatTurn[];
};

const SOURCE_LABEL: Record<ChatReplyDto["source"], string> = {
  built_in: "Built-in answer · free",
  cache: "Remembered answer · free",
  claude: "Claude · paid",
  none: "Not answered",
};

const SUGGESTIONS = [
  "Summarise this analysis and what needs my attention.",
  "What drove the recommendation and the scores?",
  "Are there validation failures or discrepancies I should look at?",
  "What is waiting for my review?",
];

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

export default function AnalystChat({ analysisId }: AnalystChatProps) {
  const [turns, setTurns] = useState<UiTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [budget, setBudget] = useState<BudgetStatus | null>(null);
  const [whyIndex, setWhyIndex] = useState<number | null>(null);
  const [why, setWhy] = useState("");
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, busy]);

  useEffect(() => {
    getBudget()
      .then(setBudget)
      .catch(() => undefined);
  }, []);

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const next: UiTurn[] = [...turns, { role: "user", content }];
    setTurns(next);
    setDraft("");
    setError(null);
    setBusy(true);
    try {
      const reply = await chatWithAnalyst(
        analysisId,
        next.map(({ role, content: body }) => ({ role, content: body })),
      );
      if (reply.budget) setBudget(reply.budget);
      setTurns([
        ...next,
        {
          role: "assistant",
          content: reply.reply || "(No answer returned.)",
          tools: reply.tool_calls.map((c) => ({ name: c.name, ok: c.ok })),
          source: reply.source,
          needsClaude: reply.needs_claude,
          estimatedCost: reply.estimated_cost_usd,
          askedWith: next.map(({ role, content: body }) => ({ role, content: body })),
        },
      ]);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the analyst. Please try again.",
      );
      getBudget()
        .then(setBudget)
        .catch(() => undefined);
    } finally {
      setBusy(false);
    }
  }

  async function askClaude(index: number) {
    const turn = turns[index];
    if (!turn?.askedWith || busy) return;
    setError(null);
    setBusy(true);
    try {
      const reply = await chatWithAnalyst(analysisId, turn.askedWith, "claude");
      if (reply.budget) setBudget(reply.budget);
      setTurns((current) =>
        current.map((t, i) =>
          i === index
            ? {
                ...t,
                content: reply.reply || "(No answer returned.)",
                tools: reply.tool_calls.map((c) => ({ name: c.name, ok: c.ok })),
                source: reply.source,
                needsClaude: false,
                estimatedCost: reply.estimated_cost_usd,
              }
            : t,
        ),
      );
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the analyst. Please try again.",
      );
    } finally {
      setBusy(false);
      getBudget()
        .then(setBudget)
        .catch(() => undefined);
    }
  }

  async function rate(index: number, rating: "up" | "down", reason?: string) {
    const answer = turns[index];
    const question = [...turns.slice(0, index)].reverse().find((t) => t.role === "user");
    setTurns((current) => current.map((t, i) => (i === index ? { ...t, rating } : t)));
    setWhyIndex(null);
    setWhy("");
    try {
      await submitFeedback(analysisId, {
        target: "chat_answer",
        action: rating === "up" ? "thumbs_up" : "thumbs_down",
        reason: reason?.trim() || undefined,
        context: {
          question: question?.content.slice(0, 400),
          answer: answer?.content.slice(0, 600),
        },
      });
    } catch {
      setError("Could not save your feedback. Please try again.");
    }
  }

  const blocked = budget?.level === "exceeded";

  return (
    <section className="flex h-[calc(100vh-18rem)] min-h-[28rem] w-full flex-col overflow-hidden rounded-lg border border-hap-border bg-hap-panel">
      <div className="flex shrink-0 items-center gap-3 border-b border-hap-border px-6 py-4 lg:px-8">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-hap-orange to-hap-orange-dim text-xs font-bold text-black">
          AI
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-semibold">{getAnalystLabel()}</h3>
          <p className="text-[11px] text-hap-muted">
            Read-only. Explains and cites this analysis; decisions stay with you.
          </p>
        </div>
        {budget && (
          <p
            className={`text-[11px] ${
              budget.level === "ok" ? "text-hap-muted" : budget.level === "warning" ? "text-hap-warning" : "text-red-300"
            }`}
            title={`Claude spend for ${budget.month}`}
          >
            {formatUsd(budget.spent_usd)} of {formatUsd(budget.cap_usd)} this month
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-6 py-5 lg:px-8">
        {turns.length === 0 && (
          <div className="space-y-3">
            <p className="text-sm text-hap-muted">Ask about this analysis. For example:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => send(suggestion)}
                  disabled={busy || blocked}
                  className="rounded-full border border-hap-border px-3 py-1.5 text-xs text-hap-muted transition-colors hover:border-hap-orange hover:text-hap-orange disabled:opacity-50"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((turn, index) => (
          <div key={index} className={turn.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-lg px-4 py-3 text-sm leading-relaxed ${
                turn.role === "user"
                  ? "bg-hap-orange/15 text-foreground"
                  : "border border-hap-border bg-hap-panel-elevated text-foreground"
              }`}
            >
              {turn.content}
              {turn.role === "assistant" && turn.needsClaude && (
                <div className="mt-3">
                  <button
                    onClick={() => void askClaude(index)}
                    disabled={busy || blocked}
                    className="rounded-md bg-hap-orange px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-40"
                  >
                    Ask Claude
                    {typeof turn.estimatedCost === "number" ? ` (about ${formatUsd(turn.estimatedCost)})` : ""}
                  </button>
                </div>
              )}
              {turn.role === "assistant" && (
                <div className="mt-2 space-y-2 border-t border-hap-border pt-2 text-[10px] text-hap-muted">
                  {turn.source && <p>{SOURCE_LABEL[turn.source]}</p>}
                  {turn.tools && turn.tools.length > 0 && (
                    <p>Looked at: {turn.tools.map((t) => t.name.replace(/_/g, " ")).join(", ")}</p>
                  )}
                  {turn.rating ? (
                    <p>{turn.rating === "up" ? "Marked helpful. Thank you." : "Marked not right. Thank you."}</p>
                  ) : turn.needsClaude ? null : whyIndex === index ? (
                    <div className="space-y-1">
                      <textarea
                        value={why}
                        onChange={(event) => setWhy(event.target.value)}
                        rows={2}
                        maxLength={2000}
                        placeholder="What was wrong or missing? (optional)"
                        className="w-full resize-none rounded border border-hap-border bg-hap-panel px-2 py-1 text-xs text-foreground outline-none focus:border-hap-orange"
                      />
                      <div className="flex gap-2">
                        <button
                          onClick={() => void rate(index, "down", why)}
                          className="rounded bg-hap-orange px-2 py-1 text-[11px] font-semibold text-black"
                        >
                          Send feedback
                        </button>
                        <button onClick={() => setWhyIndex(null)} className="px-2 py-1 text-[11px] hover:text-foreground">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3">
                      <span>Was this right?</span>
                      <button onClick={() => void rate(index, "up")} className="hover:text-hap-orange">
                        Helpful
                      </button>
                      <button
                        onClick={() => {
                          setWhyIndex(index);
                          setWhy("");
                        }}
                        className="hover:text-hap-orange"
                      >
                        Not right
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && <p className="text-xs text-hap-muted">HAP Analyst is reading the analysis…</p>}
        {budget?.level === "warning" && (
          <p className="text-xs text-hap-warning">
            You have used {budget.percent_used.toFixed(0)}% of this month&apos;s Claude budget.
          </p>
        )}
        {error && (
          <p role="alert" className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-xs text-red-300">
            {error}
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
        className="shrink-0 border-t border-hap-border px-6 py-4 lg:px-8"
      >
        <div className="flex items-end gap-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send(draft);
              }
            }}
            rows={2}
            maxLength={8000}
            disabled={blocked}
            placeholder={blocked ? "Monthly Claude budget reached." : "Ask HAP about this analysis…"}
            className="min-h-[3rem] flex-1 resize-none rounded-md border border-hap-border bg-hap-panel-elevated px-3 py-2 text-sm outline-none focus:border-hap-orange disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={busy || blocked || !draft.trim()}
            className="rounded-md bg-hap-orange px-4 py-2 text-sm font-semibold text-black transition-opacity disabled:opacity-40"
          >
            Send
          </button>
        </div>
        <p className="mt-2 text-[10px] text-hap-muted">
          Answers use this analysis&apos;s stored results, which are sent to the Claude API. Check key figures before
          relying on them.
        </p>
      </form>
    </section>
  );
}
