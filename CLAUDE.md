# CLAUDE.md

## Tech stack
FastAPI (Python 3.13) + LangGraph backend in `api/`, owns all Claude/Duffel/Voyage
calls. Next.js (TypeScript, App Router) + Tailwind + shadcn/ui frontend in `web/`.
Supabase (Postgres + pgvector, Auth) for data. One seeded demo company ("Acme Corp").

## Commands
```bash
# api/ (from repo root)
cd api && .venv/Scripts/python.exe -m uvicorn main:app --reload   # dev server
cd api && .venv/Scripts/python.exe -m pytest                      # test
cd api && .venv/Scripts/python.exe -m ruff check .                # lint

# web/ (from repo root)
npm run dev --prefix web
npm run lint --prefix web
npm run build --prefix web

# supabase/ (from repo root)
npx supabase db push
```

## Architecture (one paragraph, not a tour)
Employees log into `web/` (Supabase Auth) and chat with a single LangGraph agent
(`api/agent/`) that calls three tools: `search_travel` (mock Duffel data today,
`api/travel/duffel_client.py`), `check_policy` (hardcoded rules first,
`api/policy/rules.py`, then pgvector-backed RAG over the uploaded policy PDF,
`api/policy/retrieval.py`, when the "why" matters), and `create_booking`, which
writes a `bookings` row as `booked` or `pending_approval`. `web/`'s itinerary page
reads bookings and lets a manager approve/reject pending ones. Nothing in `web/`
calls Claude, Duffel, or Voyage directly.

## Conventions
- One demo company only in this build — do not add multi-tenant admin UI.
- No MCP tool-wiring layer yet — tools are plain Python functions bound into the
  LangGraph graph. Revisit if/when a second agent needs to share tool infra.
- UI changes go through the `frontend-design` skill, not generic shadcn defaults.
