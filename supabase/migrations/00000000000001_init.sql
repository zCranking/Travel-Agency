create extension if not exists vector;
create extension if not exists pgcrypto;

create table companies (
    id uuid primary key default gen_random_uuid(),
    name text not null
);

create table employees (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    auth_user_id uuid references auth.users(id),
    name text not null,
    email text not null unique,
    manager_employee_id uuid references employees(id)
);

create table policies (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    rules jsonb not null,
    policy_doc_storage_path text
);

-- embedding dim matches Voyage AI voyage-3 (1024 dims); change here and in
-- the embedding call together if the embedding model ever changes.
create table policy_chunks (
    id uuid primary key default gen_random_uuid(),
    policy_id uuid not null references policies(id) on delete cascade,
    content text not null,
    embedding vector(1024)
);

create table trips (
    id uuid primary key default gen_random_uuid(),
    company_id uuid not null references companies(id) on delete cascade,
    employee_id uuid not null references employees(id) on delete cascade,
    thread_id text not null unique,
    created_at timestamptz not null default now()
);

create table bookings (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    kind text not null check (kind in ('flight', 'hotel')),
    details jsonb not null,
    price_cents int not null,
    status text not null default 'booked'
        check (status in ('booked', 'pending_approval', 'rejected')),
    created_at timestamptz not null default now()
);

create table trip_messages (
    id uuid primary key default gen_random_uuid(),
    trip_id uuid not null references trips(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    created_at timestamptz not null default now()
);

create index policy_chunks_embedding_idx on policy_chunks
    using ivfflat (embedding vector_cosine_ops) with (lists = 10);
create index employees_company_id_idx on employees (company_id);
create index trips_employee_id_idx on trips (employee_id);
create index bookings_trip_id_idx on bookings (trip_id);
create index trip_messages_trip_id_idx on trip_messages (trip_id);
