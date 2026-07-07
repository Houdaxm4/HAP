# HAP Backend

FastAPI service for **Houda's Analyst Platform (HAP)**.

## Quick Start

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/analyses` | List all analyses |
| GET | `/api/analyses/{id}` | Get analysis by ID |
| POST | `/api/analyses` | Create analysis (multipart uploads) |
| PATCH | `/api/analyses/{id}` | Update status/progress |
| GET | `/api/analyses/{id}/chat` | Get chat history |
| POST | `/api/analyses/{id}/chat` | Send chat message |
| WS | `/api/ws/analyses/{id}` | Real-time progress updates |

## Project Layout

```
backend/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Settings
│   ├── database.py          # SQLAlchemy setup
│   ├── api/routes/          # HTTP + WebSocket routes
│   ├── models/              # Database models
│   ├── schemas/             # Pydantic request/response types
│   ├── services/            # Business logic
│   ├── agents/              # Analysis pipeline agents
│   └── data/seed.py         # Mock seed data
├── uploads/                 # Uploaded workbooks (gitignored)
└── requirements.txt
```

## Golden Rules

1. Never overwrite formulas.
2. Never invent financial data.
3. Never recompute proprietary metrics from `custom_run_filter`.
4. Preserve traceability for every important number.
5. Prefer SEC filings as the source of truth.
6. Human judgment always overrides automation.
