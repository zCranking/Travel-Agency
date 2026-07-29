-- Duffel order creation requires passenger details (legal name, date of
-- birth, gender, title, contact) that `employees.name`/`email` don't carry.
-- One jsonb column rather than six typed columns, matching how `policies.rules`
-- and `bookings.details` already store shaped-but-evolving data here.
--
-- This holds traveler PII. RLS is already enabled on `employees` by
-- 00000000000002_rls.sql, so the existing owner-scoped policies cover this
-- column too — no new grants, and the anon key still can't read it.
alter table employees add column traveler_profile jsonb;

comment on column employees.traveler_profile is
    'Duffel passenger fields: given_name, family_name, born_on (YYYY-MM-DD), '
    'gender (m|f), title (mr|ms|mrs|miss|dr), phone_number (E.164). '
    'Contains PII — never expose via a public/anon-key read path.';
