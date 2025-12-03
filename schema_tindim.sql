-- Schema completo do Tindim
-- Execute este arquivo no seu Supabase SQL Editor

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
    processed_at timestamp with time zone,
    created_at timestamp with time zone default now()
);

-- 3. Tabela de Assinantes (Leads + Assinantes)
create table if not exists public.subscribers (
    id uuid default uuid_generate_v4() primary key,
    phone_number text not null unique,
    email text unique,
    name text not null default 'Lead',
    is_active boolean default false, -- Só ativa após pagamento
    interests jsonb default '[]'::jsonb, -- Tópicos que o usuário escolheu
    tone text default 'casual' check (tone in ('formal', 'casual')), -- Tom preferido
    plan text default 'generalista' check (plan in ('generalista', 'estrategista')), -- Plano do usuário
    
    -- Configurações de horário
    preferred_times jsonb default '["07:00", "19:00"]'::jsonb, -- Horários preferidos para receber resumos
    
    -- Onboarding via WhatsApp
    onboarding_state text default 'new_lead' check (onboarding_state in (
        'new_lead', 'selecting_interests', 'selecting_profile', 'selecting_tone', 
        'demo_sent', 'awaiting_payment', 'active', 
        'configuring', 'config_schedule', 'config_interests'
    )),
    onboarding_data jsonb default '{}'::jsonb, -- Dados temporários do onboarding
    
    -- Stripe
    stripe_customer_id text,
    stripe_subscription_id text,
    subscription_status text default 'none' check (subscription_status in (
        'none', 'trialing', 'active', 'past_due', 'canceled'
    )),
    
    -- Contadores diários
    daily_message_count integer default 0, -- Contador de mensagens do dia
    daily_ai_count integer default 0, -- Contador de uso de IA do dia
    last_reset_at timestamp with time zone default now(), -- Última vez que resetou o contador
    
    created_at timestamp with time zone default now()
);

-- 4. Tabela de Conversas (Chat Interativo)
create table if not exists public.conversations (
    id uuid default uuid_generate_v4() primary key,
    subscriber_id uuid not null references public.subscribers(id) on delete cascade,
    article_id uuid references public.articles(id) on delete set null,
    message_count integer default 0, -- Quantas mensagens já foram trocadas nesta conversa
    context jsonb default '{}'::jsonb, -- Armazena o contexto da conversa
    is_active boolean default true, -- Se a conversa ainda está ativa
    started_at timestamp with time zone default now(),
    last_message_at timestamp with time zone default now(),
    created_at timestamp with time zone default now()
);

-- 5. Tabela de Mensagens (Histórico de Chat)
create table if not exists public.messages (
    id uuid default uuid_generate_v4() primary key,
    conversation_id uuid not null references public.conversations(id) on delete cascade,
    role text not null check (role in ('user', 'assistant')), -- Quem enviou
    content text not null,
    created_at timestamp with time zone default now()
);

-- 6. Tabela de Áudios Gerados
create table if not exists public.audio_digests (
    id uuid default uuid_generate_v4() primary key,
    subscriber_id uuid not null references public.subscribers(id) on delete cascade,
    audio_url text, -- URL do áudio gerado (pode ser armazenado no Supabase Storage ou ElevenLabs)
    script text not null, -- Roteiro usado para gerar o áudio
    topics jsonb not null, -- Tópicos incluídos neste áudio
    duration_seconds integer, -- Duração do áudio
    sent_at timestamp with time zone,
    created_at timestamp with time zone default now()
);

-- 7. Índices para performance
create index if not exists idx_articles_url on public.articles(url);
create index if not exists idx_articles_category on public.articles(category);
create index if not exists idx_articles_processed_at on public.articles(processed_at);
create index if not exists idx_subscribers_active on public.subscribers(is_active);
create index if not exists idx_subscribers_phone on public.subscribers(phone_number);
create index if not exists idx_conversations_subscriber on public.conversations(subscriber_id);
create index if not exists idx_conversations_active on public.conversations(is_active);
create index if not exists idx_messages_conversation on public.messages(conversation_id);
create index if not exists idx_audio_digests_subscriber on public.audio_digests(subscriber_id);

-- 8. Políticas RLS (Row Level Security) - Opcional, mas recomendado
-- Descomente se quiser ativar segurança em nível de linha
-- alter table public.subscribers enable row level security;
-- alter table public.conversations enable row level security;
-- alter table public.messages enable row level security;
-- alter table public.audio_digests enable row level security;
