-- Let a signed-in employee edit their own basic profile (name, phone) direct
-- from the browser. Table-wide UPDATE was already granted to `authenticated`
-- by default (Supabase's standard schema grants) but had no RLS policy, so it
-- was a silent no-op (0 rows affected). Column-level grant keeps the write
-- scoped to profile fields only -- company_id/auth_user_id/manager_employee_id
-- stay writable only via the service role (e.g. onboarding, org changes).
revoke update on employees from authenticated;
grant update (name, traveler_profile) on employees to authenticated;

create policy "employees update own row"
    on employees for update
    to authenticated
    using (auth_user_id = auth.uid())
    with check (auth_user_id = auth.uid());
