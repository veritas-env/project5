# HelpDesk Pro

A customer support desk: teams (workspaces), tickets with priorities and statuses,
internal notes, assignment, a queue dashboard and team management with invitations.
Runs on synthetic data only.

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Alembic |
| Data | PostgreSQL 16, Redis 7 |
| Deploy | Docker Compose behind Nginx and the lab TLS gateway |

## Roles

| Role | Can |
|---|---|
| Viewer | read tickets and notes |
| Member (agent) | + open tickets, add notes, change status (except closing), assign |
| Manager (team lead) | + close tickets, invite viewers and agents, remove agents |
| Owner | + change roles, invite managers |

## Run the tests

```
cd backend
../.venv/Scripts/python.exe -m pytest -q
```

## Run with Docker

```
cp .env.example .env      # fill in every secret
make build up
docker compose -f deployment/compose.yaml --env-file .env run --rm backend \
    python -m app.cli seed-demo --passwords-out /data/uploads/../demo-passwords.json
```

Demo data: two support teams (Brightline Broadband Support, Kestrel Software Support)
with agents, 80 tickets and notes. Passwords are written only to the `--passwords-out` file.

## Documentation

- [docs/architecture.md](docs/architecture.md)
- [docs/security-model.md](docs/security-model.md)
- [docs/test-plan.md](docs/test-plan.md)
- [docs/operations.md](docs/operations.md)
