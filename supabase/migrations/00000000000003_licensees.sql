create table licensees (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    api_key text not null unique,
    created_at timestamptz not null default now()
);

alter table licensees enable row level security;
