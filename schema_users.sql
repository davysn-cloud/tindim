-- Schema de Usuários Web para o Tindim
-- Execute este arquivo no seu Supabase SQL Editor APÓS o schema_tindim.sql

-- 1. Tabela de Usuários Web (para login via site)
create table if not exists public.users (
    id uuid default uuid_generate_v4() primary key,
    email text not null unique,
    password_hash text not null,
    name text not null,
    phone_number text unique, -- Opcional, para vincular ao WhatsApp
    interests jsonb default '["economy", "politics"]'::jsonb,
    plan text default 'generalista' check (plan in ('generalista', 'estrategista')),
    
    -- Stripe
    stripe_customer_id text unique,
    stripe_subscription_id text unique,
    subscription_status text default 'trialing' check (subscription_status in ('trialing', 'active', 'canceled', 'past_due', 'incomplete')),
    trial_ends_at timestamp with time zone default (now() + interval '5 days'),
    
    -- Vínculo com subscriber (WhatsApp)
    subscriber_id uuid references public.subscribers(id) on delete set null,
    
    -- Metadata
    is_active boolean default true,
    email_verified boolean default false,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

-- 2. Tabela de Sessões (para autenticação)
create table if not exists public.sessions (
    id uuid default uuid_generate_v4() primary key,
    user_id uuid not null references public.users(id) on delete cascade,
    token text not null unique,
    expires_at timestamp with time zone not null,
    created_at timestamp with time zone default now()
);

-- 3. Índices
create index if not exists idx_users_email on public.users(email);
create index if not exists idx_users_stripe_customer on public.users(stripe_customer_id);
create index if not exists idx_users_subscriber on public.users(subscriber_id);
create index if not exists idx_sessions_token on public.sessions(token);
create index if not exists idx_sessions_user on public.sessions(user_id);
create index if not exists idx_sessions_expires on public.sessions(expires_at);

-- 4. Função para atualizar updated_at automaticamente
create or replace function update_updated_at_column()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

-- 5. Trigger para atualizar updated_at
drop trigger if exists update_users_updated_at on public.users;
create trigger update_users_updated_at
    before update on public.users
    for each row
    execute function update_updated_at_column();

-- 6. Função para limpar sessões expiradas (rode periodicamente)
create or replace function cleanup_expired_sessions()
returns void as $$
begin
    delete from public.sessions where expires_at < now();
end;
$$ language plpgsql;
