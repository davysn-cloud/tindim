-- Habilita a extensão UUID se ainda não estiver habilitada
create extension if not exists "uuid-ossp";

-- Tabela de Artigos (Notícias)
create table public.articles (
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

-- Tabela de Assinantes
create table public.subscribers (
    id uuid default uuid_generate_v4() primary key,
    phone_number text not null unique,
    name text not null,
    is_active boolean default true,
    interests jsonb default '["GERAL"]'::jsonb,
    created_at timestamp with time zone default now()
);

-- Índices para performance
create index idx_articles_url on public.articles(url);
create index idx_subscribers_active on public.subscribers(is_active);
