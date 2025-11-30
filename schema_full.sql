-- 1. Habilita a extensão UUID
create extension if not exists "uuid-ossp";

-- 2. Tabela de Artigos (Notícias)
create table if not exists public.articles (
    id uuid default uuid_generate_v4() primary key,
    title text not null,
    url text not null unique,
    original_content text,
    summary_json jsonb,
    category text,
    published_at timestamp with time zone,
    processed_at timestamp with time zone default now(),
    created_at timestamp with time zone default now()
);

-- 3. Tabela de Assinantes (Já com o campo email)
create table if not exists public.subscribers (
    id uuid default uuid_generate_v4() primary key,
    phone_number text not null unique,
    email text unique,  -- Novo campo adicionado
    name text not null,
    is_active boolean default true,
    interests jsonb default '["GERAL"]'::jsonb,
    created_at timestamp with time zone default now()
);

-- 4. Índices para performance
create index if not exists idx_articles_url on public.articles(url);
create index if not exists idx_subscribers_active on public.subscribers(is_active);
create index if not exists idx_subscribers_email on public.subscribers(email);
