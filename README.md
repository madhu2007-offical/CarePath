# CareGate

**AI-assisted Prior Authorization readiness copilot for healthcare providers.**

CareGate reads a patient's clinical record, checks it against a payer's medical-necessity criteria, drafts a submission-ready prior authorization (PA) letter, and scores how likely the request is to be accepted — flagging exactly what's missing before it becomes a denial.

Built for [Hackathon Name] — *Rise of the Agents: Agentic AI & Autonomous Systems*.

---

## Why This Exists

Prior authorization is the single biggest source of care delay and physician burnout in U.S. healthcare — 94%+ of physicians report it delays care, and practices spend 12+ hours/week on it. Existing tools either store data (EHRs), serve the payer's interest (utilization-management AI), or automate one brittle step (RPA). None of them own the coordination layer: read the chart, match it to payer criteria, assemble a submission-ready packet, and flag what's missing — before the payer does.

CareGate is that missing layer, scoped honestly: it drafts and validates, it does not auto-submit, and it escalates anything outside its documented rule base to a human reviewer.

Full problem statement and research grounding: see [`docs/PROBLEM_STATEMENT.md`](docs/PROBLEM_STATEMENT.md).

---

## How It Works

```
Patient Dataset (CSV)
        │
        ▼
  Patient Database (SQLite)
        │
        ▼
  Policy Validation Engine   ← deterministic rule matching, not an LLM
        │
        ▼
     Gemini API              ← clinical letter generation + suggested next steps
        │
        ▼
  Readiness Score + Frontend Display
```

**Core principle:** the LLM only writes clinical narrative. Every other decision — which fields are missing, whether step-therapy criteria are met, what the readiness score is — is deterministic Python logic checked against a rule base. This keeps the system auditable and avoids the administrative-field gaps that generic LLM wrappers are known to produce.

---

## Screens

| Screen | Purpose |
|---|---|
| **Dashboard** | Upload a patient record, view status badges, browse previous requests |
| **Patient Details** | Display extracted patient info (diagnosis, medications, referral, labs) |
| **Policy Validation** | Checklist of required fields — ✅ present / ❌ missing, against payer criteria |
| **Generated Letter** | AI-drafted PA letter, grounded in the patient record and validation results |
| **Submission Readiness** | Readiness score (%), missing documents list, suggested next steps |

---

## Tech Stack

| Layer | Tool | Notes |
|---|---|---|
| Frontend | React | Clean, card-based, minimal — optimized for live demo |
| Backend | FastAPI (Python) | REST endpoints for upload, validation, letter generation |
| Database | SQLite | Patient records + request history; swap to PostgreSQL for production |
| AI | Gemini API | Letter generation + suggested next steps only — no model training |
| Dataset | Kaggle patient dataset (mock) + hardcoded payer policy rules | See `data/` |

No model training is used or required. All medical reasoning beyond narrative drafting is deterministic rule-matching against `data/policy_rules.json`.

---

## Project Structure

```
caregate/
├── backend/
│   ├── main.py                 # FastAPI app, route definitions
│   ├── models.py                # Patient / Request DB models
│   ├── validation.py            # Deterministic policy-matching logic
│   ├── gemini_client.py         # Letter + next-steps generation
│   └── db.sqlite3
├── frontend/
│   ├── src/
│   │   ├── pages/                # Dashboard, PatientDetails, Validation, Letter, Readiness
│   │   └── components/
│   └── package.json
├── data/
│   ├── patients.csv              # Kaggle-sourced mock patient dataset
│   └── policy_rules.json         # Mock payer medical-necessity criteria
├── docs/
│   └── PROBLEM_STATEMENT.md
└── README.md
```

---

## API Endpoints

| Method | Route | Description |
|---|---|---|
| `POST` | `/upload` | Ingest dataset, populate patient records |
| `GET` | `/patients` | List all patients |
| `GET` | `/patients/{id}` | Get one patient's full record |
| `POST` | `/patients/{id}/validate` | Run policy validation → checklist + readiness score |
| `POST` | `/patients/{id}/generate-letter` | Call Gemini → return drafted PA letter |
| `GET` | `/requests` | List previously generated requests with scores |

---

## Setup

```bash
# Backend
cd backend
pip install -r requirements.txt --break-system-packages
export GEMINI_API_KEY=your_key_here
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Requires a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

---

## Scope & Limitations (Read Before Demo)

CareGate is deliberately scoped, not because of time constraints alone, but because current research shows fully autonomous provider–payer negotiation is not yet safely automatable — recent benchmarking on this exact workflow found frontier agent success collapses to 0% in end-to-end negotiation between a provider and payer agent.

CareGate does **not**:
- Auto-submit requests to a payer
- Autonomously negotiate, appeal, or handle peer-to-peer review calls
- Handle "gray-zone" cases outside its documented rule base without flagging them for human review

CareGate **does**:
- Draft a clinically strong, submission-ready letter
- Catch missing documentation before submission, not after denial
- Score readiness transparently, with every finding traceable to a specific rule
- Explicitly flag low-confidence or out-of-scope cases for human review rather than guessing

---

## Team

4 Epochs

## License

Hackathon project — not for clinical use. All patient data used in this demo is synthetic or sourced from public mock datasets.
