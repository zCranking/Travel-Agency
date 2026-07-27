# Wayfare AI Travel Assistant

AI-native corporate travel booking assistant. Single-company MVP: employees chat
with an agent to search/book flights and hotels; bookings are checked against
company policy (rules + RAG) and route to manager approval when out-of-policy.

## What's in here
```
CLAUDE.md          persistent project context (read every session)
docs/architecture.md   how the pieces fit together
docs/superpowers/  specs and plans for this and future build phases
api/               FastAPI + LangGraph backend
web/               Next.js frontend
supabase/          Postgres/pgvector schema migrations
```

See `CLAUDE.md` for commands.
