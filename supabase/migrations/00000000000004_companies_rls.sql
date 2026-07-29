-- The sidebar footer shows the signed-in employee's company name, so the
-- browser needs to read that one companies row. Previously companies was
-- default-deny (enabled, no policy) because only the backend read it.
-- Scoped to the company the employee actually belongs to — not all companies.

create policy "employees read own company"
    on companies for select
    to authenticated
    using (
        id in (
            select company_id from employees where auth_user_id = auth.uid()
        )
    );
