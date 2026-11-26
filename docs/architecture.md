# Architecture

- **Frontend**: Next.js. Pages: teams, ticket queue (search, status filter, sort), ticket
  detail with internal notes, team & invitations, invitation landing page.
- **Backend**: FastAPI. Routers: `auth`, `workspaces` (members), `invitations`, `tickets`
  (tickets, notes, dashboard), `admin` (security events, alerts).
- **Data model**: `workspaces` → `memberships(role)`, `invitations`, `tickets` → `ticket_notes`;
  `activity`; `security_events` (append-only) and `alerts`.
- **Demo data**: `python -m app.cli seed-demo` (see `app/demo_data.py`).
