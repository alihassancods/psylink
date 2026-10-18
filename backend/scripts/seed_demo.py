"""CLI entry for the synthetic demo dataset.

    uv run python scripts/seed_demo.py                 # seed the local/hashed DATABASE_URL
    uv run python scripts/seed_demo.py --purge         # remove the demo rows and stop
    uv run python scripts/seed_demo.py --create-auth-users

`--create-auth-users` additionally creates the four logins in Supabase through GoTrue's admin
API, which needs `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` in the environment. Without it the
profiles are seeded but nobody can sign in — the ids are derived from the emails, so creating
those users by hand in the dashboard also works, as long as the resulting auth uid is the one
this script derives (see `demo_accounts()` in the output).

Demo passwords are generated per run and printed once. They are for a throwaway account on
synthetic data; do not reuse one anywhere real.
"""

import argparse
import asyncio
import json
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

from app.services.demo_seed import (
    DEMO_USERS,
    UserCredential,
    purge_demo,
    seed_demo,
)


def _password_for(email: str) -> str:
    """A fresh random password each run — printed once, never stored by us."""
    return f"Bridge-demo-{secrets.token_urlsafe(9)}"


async def create_auth_users(*, url: str, service_key: str, password: str) -> list[dict[str, str]]:
    """Create (or sign in the ids for) the demo auth users through GoTrue's admin API.

    Already-existing emails are treated as success: re-running the seeder should not be blocked
    by an account the dashboard already holds.
    """
    created: list[dict[str, str]] = []
    async with httpx.AsyncClient(
        base_url=f"{url.rstrip('/')}/auth/admin/v1",
        headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
        timeout=15.0,
    ) as client:
        for user in DEMO_USERS:
            response = await client.post(
                "/users",
                json={
                    "email": user.email,
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"display_name": user.display_name},
                },
            )
            if response.status_code in (200, 201):
                body = response.json()
                created.append({"email": user.email, "id": body.get("id", "?"), "role": user.role})
            elif response.status_code in (422, 400) and "already" in response.text.lower():
                created.append({"email": user.email, "id": "(exists)", "role": user.role})
            else:
                created.append(
                    {"email": user.email, "id": f"FAILED {response.status_code}", "role": user.role}
                )
    return created


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--purge", action="store_true", help="delete the demo rows and exit")
    parser.add_argument(
        "--create-auth-users",
        action="store_true",
        help="create the four logins in Supabase (needs SUPABASE_URL and SUPABASE_SERVICE_KEY)",
    )
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    if args.create_auth_users:
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            print(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY are required for --create-auth-users",
                file=sys.stderr,
            )
            return 2
        password = _password_for("shared")
        users = await create_auth_users(url=url, service_key=key, password=password)
        print(json.dumps(users, indent=2) if args.json else json.dumps(users))

    if args.purge:
        await purge_demo()
        print("demo rows removed")
        return 0

    report = await seed_demo()
    report["logins"] = [
        UserCredential(u.email, u.display_name, u.role).__dict__ for u in DEMO_USERS
    ]
    report["auth_note"] = (
        "Profiles are seeded, but signing in needs matching auth users: run with "
        "--create-auth-users, or create the four emails in the Supabase dashboard."
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
