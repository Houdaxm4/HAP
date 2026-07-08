# HAP — Houda's Analyst Platform

HAP is an AI-assisted investment analysis platform designed to help prepare, verify, update, and analyze company research workbooks.

The central object in HAP is an **Analysis**.

Each Analysis contains:
- company information
- task type: new company, annual update, or quarterly update
- input files
- workbook updates
- verification results
- discrepancy reports
- decision log
- analyst summary
- lessons learned

HAP is built to automate repetitive analyst work while preserving human judgment.

## Working from any computer

**GitHub is the source of truth.** Your local folder is a copy that stays in sync via Git.

- **Repo:** https://github.com/Houdaxm4/HAP
- **Branch to use:** `main` (always pull this before you start work)

### First time on a new computer

```bash
git clone https://github.com/Houdaxm4/HAP.git
cd HAP
```

### Every time you sit down to work

```bash
cd /path/to/HAP
git checkout main
git pull origin main
```

### When you finish a work session

```bash
git add .
git commit -m "Describe what you changed"
git push origin main
```

If you are on a feature branch instead of `main`:

```bash
git push -u origin your-branch-name
```

Then open a pull request on GitHub and merge it into `main` before switching computers.

### Run the project after pulling

```bash
# Backend
cd backend
pip install -r requirements.txt
python3 -m uvicorn main:app --reload --host 127.0.0.1 --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

### Important

- Do **not** rely on only a local folder (e.g. `Downloads/HAP`) without pushing to GitHub — other machines will not see those changes.
- Runtime data (`backend/storage/uploads`, `backend/storage/outputs`, `backend/storage/analyses`) is local and gitignored; only code syncs through GitHub.
- Before starting work, always `git pull`. Before leaving a machine, always `git push`.
