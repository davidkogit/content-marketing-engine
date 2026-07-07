# Content Marketing Engine

LLM-powered marketing content generation platform with Kanban workflow management.

## Features

- **PIM Core** — Product Information Management with categories, segments, claims, and version tracking
- **Document Processor** — PDF text extraction and URL content fetching with LLM-based spec extraction
- **RAG Pipeline** — Context-aware content generation with source anchoring and brand-rule compliance
- **Kanban Workflow** — 3-stage content pipeline: Draft → Review → Approved → Exported
- **Role-Based Access** — Super Admin, Admin, Editor, and Viewer roles with granular permissions
- **Export Engine** — Configurable CSV export with field mapping and export history

## Tech Stack

| Layer     | Technology                       |
|-----------|----------------------------------|
| Backend   | Python 3.11+ / FastAPI (async)   |
| Frontend  | React + Vite + Tailwind CSS + shadcn/ui |
| Database  | SQLite (single file)             |
| Auth      | JWT + bcrypt                     |
| LLM       | OpenAI / Anthropic (configurable)|
| Server    | Caddy (reverse proxy / auto HTTPS) |

## Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Caddy (for production deployment)

### Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edit with your configuration
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Quick Start

1. Start the backend: `cd backend && uvicorn app.main:app --reload`
2. Start the frontend: `cd frontend && npm run dev`
3. Open `http://localhost:5173` in your browser
4. Log in with the default Super Admin account (created on first run)

## API Documentation

Once the backend is running, interactive API docs are available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Deployment

See the `deploy/` directory for Caddyfile, systemd service unit, and setup scripts.

```bash
# One-shot VPS setup
sudo bash deploy/setup.sh
```

## Project Structure

```
content-marketing-engine/
├── backend/             # FastAPI application
│   ├── app/             # Application package
│   │   ├── auth/        # JWT authentication & RBAC
│   │   ├── products/    # PIM CRUD
│   │   ├── documents/   # PDF/URL processing
│   │   ├── llm/         # RAG orchestrator
│   │   ├── workflow/    # Kanban state machine
│   │   ├── export/      # CSV export engine
│   │   ├── settings/    # Super Admin configuration
│   │   └── models/      # SQLite schema & models
│   ├── data/            # Database, rules, uploads
│   └── requirements.txt
├── frontend/            # React SPA
│   └── src/
│       ├── components/  # Reusable UI components
│       ├── pages/       # Route pages
│       ├── hooks/       # Custom React hooks
│       ├── lib/         # Utilities & API client
│       └── types/       # TypeScript type definitions
├── deploy/              # Deployment configuration
└── .gitignore
```

## License

Proprietary — All rights reserved.
