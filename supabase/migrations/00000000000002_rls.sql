-- Closes the RLS-disabled advisory. The backend (api/) uses the service-role
-- key and bypasses RLS entirely, so these policies only govern what the
-- browser (anon/authenticated key) can read directly.
--
-- employees/trips/trip_messages are the only tables the frontend queries
-- directly (login + itinerary + chat pages) — each policy scopes strictly to
-- rows owned by the signed-in employee. companies/policies/policy_chunks/
-- bookings are read only through the backend today, so RLS is enabled with
-- no policy (default-deny for anon/authenticated) rather than inventing
-- access rules nothing needs yet.

alter table companies enable row level security;
alter table employees enable row level security;
alter table policies enable row level security;
alter table policy_chunks enable row level security;
alter table trips enable row level security;
alter table bookings enable row level security;
alter table trip_messages enable row level security;

create policy "employees read own row"
    on employees for select
    to authenticated
    using (auth_user_id = auth.uid());

create policy "employees read own trips"
    on trips for select
    to authenticated
    using (
        employee_id in (
            select id from employees where auth_user_id = auth.uid()
        )
    );

create policy "employees read own trip messages"
    on trip_messages for select
    to authenticated
    using (
        trip_id in (
            select t.id from trips t
            join employees e on e.id = t.employee_id
            where e.auth_user_id = auth.uid()
        )
    );
