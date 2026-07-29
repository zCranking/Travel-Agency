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


def _traveler(given, family, born_on, gender, title, phone):
    """Duffel passenger fields. Fabricated demo identities — these are the
    values sent to Duffel test mode when booking a real test order."""
    return {
        "given_name": given,
        "family_name": family,
        "born_on": born_on,
        "gender": gender,
        "title": title,
        "phone_number": phone,
    }


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


def _flight(code, airline, fare_class, origin, dest, date, cents, conf=None):
    details = {
        "id": code,
        "airline": airline,
        "fare_class": fare_class,
        "origin": origin,
        "destination": dest,
        "depart_date": date,
        "price_cents": cents,
    }
    if conf:
        details["confirmation_code"] = conf
    return details


def _hotel(code, name, location, check_in, check_out, nightly, conf=None):
    details = {
        "id": code,
        "name": name,
        "location": location,
        "check_in": check_in,
        "check_out": check_out,
        "nightly_rate_cents": nightly,
    }
    if conf:
        details["confirmation_code"] = conf
    return details


def _demo_trips(jordan, manager, employees) -> list[dict]:
    """Demo itineraries for the UI.

    Destination codes are picked so /duty-of-care's mock risk hash spreads
    across low/medium/high (LOS=high, JFK=medium, LHR/AMS=low) — change a code
    and the risk colour changes with it.
    """
    priya, sam = employees[1], employees[2]
    return [
        # --- Jordan (the demo login): oldest departure first, NYC inserted last ---
        {
            "key": "tokyo",
            "employee_id": jordan["id"],
            "bookings": [{
                "kind": "flight",
                "details": _flight(
                    "fl_nrt", "ANA", "business", "SFO", "NRT", "2026-11-20", 324000
                ),
                "price_cents": 324000,
                "status": "rejected",
            }],
        },
        {
            "key": "chicago",
            "employee_id": jordan["id"],
            "bookings": [
                {
                    "kind": "flight",
                    "details": _flight(
                        "fl_ord", "United", "economy", "SFO", "ORD",
                        "2026-10-02", 41200, "UA7Q2K",
                    ),
                    "price_cents": 41200,
                    "status": "booked",
                },
                {
                    "kind": "hotel",
                    "details": _hotel(
                        "ht_ord", "The Langham", "Chicago",
                        "2026-10-02", "2026-10-05", 28900,
                    ),
                    "price_cents": 86700,
                    "status": "pending_approval",
                },
            ],
        },
        {
            "key": "austin",
            "employee_id": jordan["id"],
            "bookings": [{
                "kind": "flight",
                "details": _flight(
                    "fl_aus", "Alaska", "business", "SFO", "AUS", "2026-09-15", 189000
                ),
                "price_cents": 189000,
                "status": "pending_approval",
            }],
        },
        {
            "key": "nyc",
            "employee_id": jordan["id"],
            "bookings": [
                {
                    "kind": "flight",
                    "details": _flight(
                        "fl_jfk", "United", "economy", "SFO", "JFK",
                        "2026-08-04", 62400, "UA4X8B",
                    ),
                    "price_cents": 62400,
                    "status": "booked",
                },
                {
                    "kind": "hotel",
                    "details": _hotel(
                        "ht_jfk", "The Standard", "New York",
                        "2026-08-04", "2026-08-07", 21500, "STD9M4",
                    ),
                    "price_cents": 64500,
                    "status": "booked",
                },
            ],
            "messages": [
                ("user", "I need to be in New York August 4th through the 7th."),
                (
                    "assistant",
                    (
                        "Found 3 nonstop options SFO to JFK on Aug 4. The best value "
                        "in policy is United 8:05a at $624 economy. Want me to hold it?"
                    ),
                ),
                ("user", "Yes, book that one. And somewhere to stay near Midtown."),
                (
                    "assistant",
                    (
                        "Booked United 8:05a — confirmation UA4X8B. For the hotel, The "
                        "Standard is $215/night, under the $250 nightly cap. Booked for "
                        "3 nights, confirmation STD9M4. You're all set."
                    ),
                ),
            ],
        },
        # --- teammates: one trip each, so duty of care has a real roster ---
        {
            "key": "dana_ams",
            "employee_id": manager["id"],
            "bookings": [{
                "kind": "flight",
                "details": _flight(
                    "fl_ams", "KLM", "economy", "SFO", "AMS",
                    "2026-08-12", 89000, "KL3R7T",
                ),
                "price_cents": 89000,
                "status": "booked",
            }],
        },
        {
            "key": "priya_los",
            "employee_id": priya["id"],
            "bookings": [{
                "kind": "flight",
                "details": _flight(
                    "fl_los", "Delta", "economy", "JFK", "LOS",
                    "2026-08-02", 118000, "DL8W1C",
                ),
                "price_cents": 118000,
                "status": "booked",
            }],
        },
        {
            "key": "sam_lhr",
            "employee_id": sam["id"],
            "bookings": [{
                "kind": "flight",
                "details": _flight(
                    "fl_lhr", "British Airways", "economy", "SFO", "LHR",
                    "2026-08-20", 76000, "BA5N2P",
                ),
                "price_cents": 76000,
                "status": "booked",
            }],
        },
    ]


def seed() -> None:
    db = get_db()

    db.table("companies").delete().eq("name", "Acme Corp").execute()

    company = db.table("companies").insert({"name": "Acme Corp"}).execute().data[0]
    company_id = company["id"]

    manager = db.table("employees").insert({
        "company_id": company_id,
        "name": "Dana Kim",
        "email": "dana@acme-demo.test",
        "traveler_profile": _traveler(
            "Dana", "Kim", "1981-03-19", "f", "ms", "+14155550118"
        ),
    }).execute().data[0]

    employees = db.table("employees").insert([
        {
            "company_id": company_id,
            "name": "Jordan Lee",
            "email": "jordan@acme-demo.test",
            "manager_employee_id": manager["id"],
            "traveler_profile": _traveler(
                "Jordan", "Lee", "1990-06-12", "m", "mr", "+14155550142"
            ),
        },
        {
            "company_id": company_id,
            "name": "Priya Nair",
            "email": "priya@acme-demo.test",
            "manager_employee_id": manager["id"],
            "traveler_profile": _traveler(
                "Priya", "Nair", "1987-11-04", "f", "ms", "+14155550163"
            ),
        },
        {
            "company_id": company_id,
            "name": "Sam Ortiz",
            "email": "sam@acme-demo.test",
            "manager_employee_id": manager["id"],
            "traveler_profile": _traveler(
                "Sam", "Ortiz", "1994-02-27", "m", "mr", "+14155550175"
            ),
        },
    ]).execute().data

    db.table("policies").insert({
        "company_id": company_id,
        "rules": ACME_RULES,
    }).execute()

    db.table("licensees").delete().eq("name", "Wayfare Web (internal)").execute()
    licensee = db.table("licensees").insert({
        "name": "Wayfare Web (internal)",
        "company_id": company_id,
        "api_key": f"wf_live_{uuid.uuid4().hex}",
    }).execute().data[0]

    # Jordan Lee is the demo login user (employees[0]).
    jordan = employees[0]
    auth_user_id = _create_demo_auth_user(db)
    db.table("employees").update({"auth_user_id": auth_user_id}).eq(
        "id", jordan["id"]
    ).execute()

    # Jordan's trips are inserted oldest-departure-last so the NYC trip is the
    # most recent row — /duty-of-care reads each employee's latest trip.
    trips_by_key = {}
    for spec in _demo_trips(jordan, manager, employees):
        trip = db.table("trips").insert({
            "company_id": company_id,
            "employee_id": spec["employee_id"],
            "thread_id": str(uuid.uuid4()),
        }).execute().data[0]
        trips_by_key[spec["key"]] = trip["id"]

        db.table("bookings").insert([
            {"trip_id": trip["id"], **b} for b in spec["bookings"]
        ]).execute()

        if spec.get("messages"):
            db.table("trip_messages").insert([
                {"trip_id": trip["id"], "role": role, "content": content}
                for role, content in spec["messages"]
            ]).execute()

    print(f"Seeded Acme Corp ({company_id}) with manager + {len(employees)} employees.")
    print(f"Seeded {len(trips_by_key)} trips with bookings.")
    print(
        f"Demo login: {DEMO_LOGIN_EMAIL} / {DEMO_LOGIN_PASSWORD}"
        f"  ->  chat trip id: {trips_by_key['nyc']}"
    )
    print(f"Licensee API key: {licensee['api_key']}")


if __name__ == "__main__":
    seed()
