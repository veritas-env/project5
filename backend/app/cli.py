"""Admin command line. Never exposed over HTTP.

    python -m app.cli migrate
    python -m app.cli seed --file seed.json --passwords-out /run/secrets/seed-passwords.json
    python -m app.cli reset --yes          (refused in production unless --force)
    python -m app.cli create-admin --email root@lab.test   (password read from stdin)
    python -m app.cli seed-demo --passwords-out /run/secrets/demo-passwords.json

Seed file format (no passwords in it; they're generated and written to --passwords-out):
    {"workspaces": [{"name": "Workspace A", "members": [{"email": "a@lab.test", "name": "A", "role": "owner"}]}],
     "platform_admins": [{"email": "root@lab.test", "name": "Root"}]}
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.security import hash_password, password_problems
from .models import ROLES, Membership, Workspace, User


def _alembic(url: str, *args: str) -> None:
    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parents[1]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    cfg.attributes["url"] = url
    if args[0] == "upgrade":
        command.upgrade(cfg, args[1])
    elif args[0] == "downgrade":
        command.downgrade(cfg, args[1])


def _user(s: Session, email: str, name: str, admin: bool, passwords: dict) -> User:
    email = email.lower()
    u = s.scalar(select(User).where(User.email == email))
    if u is None:
        pw = "Lab-" + secrets.token_urlsafe(18)
        u = User(email=email, display_name=name, password_hash=hash_password(pw), is_platform_admin=admin)
        s.add(u)
        s.flush()
        passwords[email] = pw
    return u


def cmd_seed(args) -> int:
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    engine = create_engine(get_settings().database_url)
    passwords: dict[str, str] = {}
    with Session(engine) as s:
        for a in data.get("platform_admins", []):
            _user(s, a["email"], a["name"], True, passwords)
        for o in data.get("workspaces", []):
            org = s.scalar(select(Workspace).where(Workspace.name == o["name"]))
            if org is None:
                org = Workspace(name=o["name"])
                s.add(org)
                s.flush()
            for m in o.get("members", []):
                if m["role"] not in ROLES:
                    raise SystemExit(f"invalid role {m['role']!r}")
                u = _user(s, m["email"], m["name"], False, passwords)
                if s.get(Membership, (org.id, u.id)) is None:
                    s.add(Membership(workspace_id=org.id, user_id=u.id, role=m["role"]))
        s.commit()
    out = Path(args.passwords_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(passwords, f, indent=2)
    print(f"seeded; {len(passwords)} new account password(s) written to {out}")
    return 0


def _write_passwords(path: str, passwords: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(passwords, f, indent=2)


def cmd_seed_demo(args) -> int:
    from .demo_data import seed_demo

    settings = get_settings()
    engine = create_engine(settings.database_url)
    with Session(engine) as s:
        passwords = seed_demo(s, settings.upload_dir)
    _write_passwords(args.passwords_out, passwords)
    print(f"demo data created; {len(passwords)} account password(s) written to {args.passwords_out}")
    return 0


def cmd_reset(args) -> int:
    settings = get_settings()
    if not args.yes:
        print("refusing without --yes", file=sys.stderr)
        return 2
    if settings.is_production and not args.force:
        print("refusing in production without --force", file=sys.stderr)
        return 2
    engine = create_engine(settings.database_url)
    with engine.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    _alembic(settings.database_url, "upgrade", "head")
    print("database reset to an empty schema")
    return 0


def cmd_create_admin(args) -> int:
    pw = sys.stdin.readline().rstrip("\n")
    problems = password_problems(pw, args.email)
    if problems:
        print("password " + "; ".join(problems), file=sys.stderr)
        return 2
    engine = create_engine(get_settings().database_url)
    with Session(engine) as s:
        s.add(User(email=args.email.lower(), display_name=args.name, password_hash=hash_password(pw), is_platform_admin=True))
        s.commit()
    print("created")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sp = sub.add_parser("seed")
    sp.add_argument("--file", required=True)
    sp.add_argument("--passwords-out", required=True)
    rp = sub.add_parser("reset")
    rp.add_argument("--yes", action="store_true")
    rp.add_argument("--force", action="store_true")
    dp = sub.add_parser("seed-demo")
    dp.add_argument("--passwords-out", required=True)
    ap = sub.add_parser("create-admin")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Administrator")
    args = p.parse_args(argv)
    if args.cmd == "migrate":
        _alembic(get_settings().database_url, "upgrade", "head")
        print("migrated")
        return 0
    return {"seed": cmd_seed, "seed-demo": cmd_seed_demo, "reset": cmd_reset,
            "create-admin": cmd_create_admin}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
