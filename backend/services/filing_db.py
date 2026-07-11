"""SQLite persistence for SEC filing metadata."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from models.filings import FilingCollectionResult, FilingDocumentMeta

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "storage" / "hap.db"


class FilingDatabase:
    """Local SQLite store for companies, collections, and filing metadata."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS companies (
                    cik TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    company_name TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS filing_collections (
                    id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    cik TEXT NOT NULL,
                    company_name TEXT,
                    status TEXT NOT NULL,
                    historical_years INTEGER NOT NULL,
                    latest_10k_accession TEXT,
                    latest_10q_accession TEXT,
                    historical_10k_count INTEGER NOT NULL DEFAULT 0,
                    cache_dir TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    error TEXT,
                    message TEXT
                );

                CREATE TABLE IF NOT EXISTS filings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    collection_id TEXT,
                    cik TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    accession_number TEXT NOT NULL UNIQUE,
                    form TEXT NOT NULL,
                    base_form TEXT NOT NULL,
                    is_amendment INTEGER NOT NULL DEFAULT 0,
                    filing_date TEXT NOT NULL,
                    report_date TEXT,
                    primary_document TEXT,
                    primary_document_url TEXT,
                    index_url TEXT,
                    html_url TEXT,
                    html_path TEXT,
                    xbrl_url TEXT,
                    xbrl_path TEXT,
                    fiscal_year INTEGER,
                    selected_role TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (collection_id) REFERENCES filing_collections(id),
                    FOREIGN KEY (cik) REFERENCES companies(cik)
                );

                CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker);
                CREATE INDEX IF NOT EXISTS idx_filings_cik ON filings(cik);
                CREATE INDEX IF NOT EXISTS idx_filings_form ON filings(base_form);
                CREATE INDEX IF NOT EXISTS idx_collections_ticker ON filing_collections(ticker);
                """
            )

    def upsert_company(self, cik: str, ticker: str, company_name: str | None) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO companies (cik, ticker, company_name, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cik) DO UPDATE SET
                    ticker = excluded.ticker,
                    company_name = excluded.company_name,
                    updated_at = excluded.updated_at
                """,
                (cik, ticker.upper(), company_name, utc_now_iso()),
            )

    def save_collection(self, result: FilingCollectionResult, historical_years: int) -> None:
        """Persist a full collection result and its filing rows."""
        self.upsert_company(result.cik, result.ticker, result.company_name)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO filing_collections (
                    id, ticker, cik, company_name, status, historical_years,
                    latest_10k_accession, latest_10q_accession, historical_10k_count,
                    cache_dir, created_at, completed_at, error, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    latest_10k_accession = excluded.latest_10k_accession,
                    latest_10q_accession = excluded.latest_10q_accession,
                    historical_10k_count = excluded.historical_10k_count,
                    cache_dir = excluded.cache_dir,
                    completed_at = excluded.completed_at,
                    error = excluded.error,
                    message = excluded.message
                """,
                (
                    result.collection_id,
                    result.ticker.upper(),
                    result.cik,
                    result.company_name,
                    result.status,
                    historical_years,
                    result.latest_10k.accession_number if result.latest_10k else None,
                    result.latest_10q.accession_number if result.latest_10q else None,
                    len(result.historical_10ks),
                    result.cache_dir,
                    result.created_at,
                    result.completed_at,
                    result.error,
                    result.message,
                ),
            )

            for filing in result.filings:
                connection.execute(
                    """
                    INSERT INTO filings (
                        collection_id, cik, ticker, accession_number, form, base_form,
                        is_amendment, filing_date, report_date, primary_document,
                        primary_document_url, index_url, html_url, html_path,
                        xbrl_url, xbrl_path, fiscal_year, selected_role, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(accession_number) DO UPDATE SET
                        collection_id = excluded.collection_id,
                        form = excluded.form,
                        base_form = excluded.base_form,
                        is_amendment = excluded.is_amendment,
                        filing_date = excluded.filing_date,
                        report_date = excluded.report_date,
                        primary_document = excluded.primary_document,
                        primary_document_url = excluded.primary_document_url,
                        index_url = excluded.index_url,
                        html_url = excluded.html_url,
                        html_path = excluded.html_path,
                        xbrl_url = excluded.xbrl_url,
                        xbrl_path = excluded.xbrl_path,
                        fiscal_year = excluded.fiscal_year,
                        selected_role = excluded.selected_role
                    """,
                    (
                        result.collection_id,
                        result.cik,
                        result.ticker.upper(),
                        filing.accession_number,
                        filing.form,
                        filing.base_form,
                        1 if filing.is_amendment else 0,
                        filing.filing_date,
                        filing.report_date,
                        filing.primary_document,
                        filing.primary_document_url,
                        filing.index_url,
                        filing.html_url,
                        filing.html_path,
                        filing.xbrl_url,
                        filing.xbrl_path,
                        filing.fiscal_year,
                        filing.selected_role,
                        utc_now_iso(),
                    ),
                )

    def get_collection(self, collection_id: str) -> FilingCollectionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM filing_collections WHERE id = ?",
                (collection_id,),
            ).fetchone()
            if row is None:
                return None
            filings = connection.execute(
                "SELECT * FROM filings WHERE collection_id = ? ORDER BY filing_date DESC",
                (collection_id,),
            ).fetchall()
        return self._row_to_collection(row, filings)

    def get_latest_collection_for_ticker(self, ticker: str) -> FilingCollectionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM filing_collections
                WHERE ticker = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (ticker.upper(),),
            ).fetchone()
            if row is None:
                return None
            filings = connection.execute(
                "SELECT * FROM filings WHERE collection_id = ? ORDER BY filing_date DESC",
                (row["id"],),
            ).fetchall()
        return self._row_to_collection(row, filings)

    def list_filings_for_ticker(self, ticker: str) -> list[FilingDocumentMeta]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM filings
                WHERE ticker = ?
                ORDER BY filing_date DESC, accession_number DESC
                """,
                (ticker.upper(),),
            ).fetchall()
        return [self._row_to_filing(row) for row in rows]

    def _row_to_collection(
        self,
        row: sqlite3.Row,
        filing_rows: list[sqlite3.Row],
    ) -> FilingCollectionResult:
        filings = [self._row_to_filing(item) for item in filing_rows]
        latest_10k = next((f for f in filings if f.selected_role == "latest_10k"), None)
        latest_10q = next((f for f in filings if f.selected_role == "latest_10q"), None)
        historical = [f for f in filings if f.selected_role == "historical_10k"]
        return FilingCollectionResult(
            collection_id=row["id"],
            ticker=row["ticker"],
            cik=row["cik"],
            company_name=row["company_name"],
            status=row["status"],
            latest_10k=latest_10k,
            latest_10q=latest_10q,
            historical_10ks=historical,
            filings=filings,
            cache_dir=row["cache_dir"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error=row["error"],
            message=row["message"] or "Filings collected. No extraction performed.",
        )

    @staticmethod
    def _row_to_filing(row: sqlite3.Row) -> FilingDocumentMeta:
        return FilingDocumentMeta(
            accession_number=row["accession_number"],
            form=row["form"],
            base_form=row["base_form"],
            is_amendment=bool(row["is_amendment"]),
            filing_date=row["filing_date"],
            report_date=row["report_date"],
            primary_document=row["primary_document"],
            primary_document_url=row["primary_document_url"],
            index_url=row["index_url"],
            html_url=row["html_url"],
            html_path=row["html_path"],
            xbrl_url=row["xbrl_url"],
            xbrl_path=row["xbrl_path"],
            fiscal_year=row["fiscal_year"],
            selected_role=row["selected_role"],
        )

    def to_debug_dict(self) -> dict[str, Any]:
        with self._connect() as connection:
            companies = connection.execute("SELECT COUNT(*) AS c FROM companies").fetchone()["c"]
            filings = connection.execute("SELECT COUNT(*) AS c FROM filings").fetchone()["c"]
            collections = connection.execute(
                "SELECT COUNT(*) AS c FROM filing_collections"
            ).fetchone()["c"]
        return {
            "db_path": str(self.db_path),
            "companies": companies,
            "filings": filings,
            "collections": collections,
        }
