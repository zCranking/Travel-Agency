"""Seeds one demo company, 4 employees, and a policy. Idempotent: re-running
clears prior Acme Corp rows first (dev-only script, no production guard needed
since this is a single-demo-company build).
"""
from core.db import get_db

ACME_RULES = {
    "max_fare_class": "economy",
    "max_hotel_nightly_rate_cents": 25000,
    "advance_booking_days_required": 3,
    "approval_threshold_cents": 150000,
}


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

    print(f"Seeded Acme Corp ({company_id}) with manager + {len(employees)} employees.")


if __name__ == "__main__":
    seed()
