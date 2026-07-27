"""Seeds one demo company, 4 employees, and a policy. Idempotent: re-running
clears prior Acme Corp rows first (dev-only script, no production guard needed
since this is a single-demo-company build).
"""
import uuid

from core.db import get_db

ACME_RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "approval_threshold_cents": 150000,
}

DEMO_LOGIN_EMAIL = "jordan@acme-demo.test"
DEMO_LOGIN_PASSWORD = "demo-password-123"


def _create_demo_auth_user(db) -> str:
    """Create (idempotently) the demo login auth user, returning its id.

    ponytail: dev-only seed — if the user already exists, delete and recreate
    rather than reconcile. supabase-py has no get-by-email, so we scan list_users.
    """
    try:
        return db.auth.admin.create_user({
            "email": DEMO_LOGIN_EMAIL,
            "password": DEMO_LOGIN_PASSWORD,
            "email_confirm": True,
        }).user.id
    except Exception:  # noqa: BLE001 — dev seed: any create failure means "already exists"
        for user in db.auth.admin.list_users():
            if user.email == DEMO_LOGIN_EMAIL:
                db.auth.admin.delete_user(user.id)
        return db.auth.admin.create_user({
            "email": DEMO_LOGIN_EMAIL,
            "password": DEMO_LOGIN_PASSWORD,
            "email_confirm": True,
        }).user.id


def seed() -> None:
    db = get_db()

    db.table("companies").delete().eq("name", "Acme Corp").execute()

    company = db.table("companies").insert({"name": "Acme Corp"}).execute().data[0]
    company_id = company["id"]

    manager = db.table("employees").insert({
        "company_id": company_id,
        "name": "Dana Kim",
        "email": "dana@acme-demo.test",
    }).execute().data[0]

    employees = db.table("employees").insert([
        {
            "company_id": company_id,
            "name": "Jordan Lee",
            "email": "jordan@acme-demo.test",
            "manager_employee_id": manager["id"],
        },
        {
            "company_id": company_id,
            "name": "Priya Nair",
            "email": "priya@acme-demo.test",
            "manager_employee_id": manager["id"],
        },
        {
            "company_id": company_id,
            "name": "Sam Ortiz",
            "email": "sam@acme-demo.test",
            "manager_employee_id": manager["id"],
        },
    ]).execute().data

    db.table("policies").insert({
        "company_id": company_id,
        "rules": ACME_RULES,
    }).execute()

    # Jordan Lee is the demo login user (employees[0]).
    jordan = employees[0]
    auth_user_id = _create_demo_auth_user(db)
    db.table("employees").update({"auth_user_id": auth_user_id}).eq(
        "id", jordan["id"]
    ).execute()

    trip = db.table("trips").insert({
        "company_id": company_id,
        "employee_id": jordan["id"],
        "thread_id": str(uuid.uuid4()),
    }).execute().data[0]

    print(f"Seeded Acme Corp ({company_id}) with manager + {len(employees)} employees.")
    print(
        f"Demo login: {DEMO_LOGIN_EMAIL} / {DEMO_LOGIN_PASSWORD}  ->  trip id: {trip['id']}"
    )


if __name__ == "__main__":
    seed()
