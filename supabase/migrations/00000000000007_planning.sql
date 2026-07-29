-- Constraint planner: the traveler states meetings, the solver produces
-- itineraries. Meetings live in their own table rather than a blob on `trips`
-- specifically so a future calendar connector writes rows here and nothing
-- else changes.

create table meetings (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    title text not null,
    city text,                 -- IATA code; required for in-person
    mode text not null check (mode in ('in_person', 'virtual')),
    starts_at timestamptz not null,
    ends_at timestamptz not null,
    -- false => binding. The solver may not violate a binding meeting: an
    -- itinerary that would is infeasible, not merely worse. Defaults to
    -- binding -- fail closed, same as the fare-class and token checks.
    flexible boolean not null default false,
    created_at timestamptz not null default now(),
    constraint in_person_needs_a_city check (mode = 'virtual' or city is not null),
    constraint meeting_ends_after_it_starts check (ends_at > starts_at)
);

-- Itineraries are persisted, not held client-side, for the same reason Duffel
-- offers are cached server-side: selection must reference something the server
-- issued. A plan handed back by a client (or a model) that we never produced
-- gets refused, exactly like an unknown offer id.
create table itineraries (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    legs jsonb not null,
    total_price_cents int not null,
    soft_violations jsonb not null default '[]',
    rank int,
    rationale text,
    concerns jsonb not null default '[]',
    risk jsonb,
    selected boolean not null default false,
    created_at timestamptz not null default now()
);

alter table trips add column origin_city text;
-- Soft, not hard: over budget is a flagged plan, never a hidden one.
alter table trips add column budget_cents int;

-- {avoid_red_eyes: bool, max_connections: int, earliest_departure: "HH:MM",
--  latest_arrival: "HH:MM"} -- all soft, all optional.
alter table employees add column travel_preferences jsonb;

-- Read only through the backend (service role), like `bookings`: RLS on with
-- no policy is default-deny for anon/authenticated, rather than inventing
-- access rules nothing needs yet.
alter table meetings enable row level security;
alter table itineraries enable row level security;

create index meetings_trip_id_idx on meetings (trip_id);
create index itineraries_trip_id_idx on itineraries (trip_id);
