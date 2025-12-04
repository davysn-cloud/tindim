-- Migration: Sistema de Beta Testing, Analytics e Feedback
-- Execute este arquivo no Supabase SQL Editor
-- Data: Dezembro 2024

-- =============================================================================
-- 1. TABELA DE EVENTOS (Analytics)
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.user_events (
    id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
    subscriber_id uuid REFERENCES public.subscribers(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    event_data jsonb DEFAULT '{}'::jsonb,
    session_id text,
    created_at timestamp with time zone DEFAULT now()
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_events_subscriber ON public.user_events(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON public.user_events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_created ON public.user_events(created_at);

COMMENT ON TABLE public.user_events IS 'Tracking de eventos do usuário para analytics';
COMMENT ON COLUMN public.user_events.event_type IS 'Tipos: message_sent, message_received, button_clicked, digest_opened, audio_played, feedback_given, error_reported, config_changed';

-- =============================================================================
-- 2. TABELA DE FEEDBACK
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.feedback (
    id uuid DEFAULT uuid_generate_v4() PRIMARY KEY,
    subscriber_id uuid REFERENCES public.subscribers(id) ON DELETE CASCADE,
    feedback_type text NOT NULL CHECK (feedback_type IN (
        'nps', 'implicit', 'bug_report', 'feature_request', 'content_quality'
    )),
    score integer, -- 0-10 para NPS, 1-3 para implicit
    comment text,
    context jsonb DEFAULT '{}'::jsonb,
    resolved boolean DEFAULT false,
    resolved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_subscriber ON public.feedback(subscriber_id);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON public.feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON public.feedback(created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_unresolved ON public.feedback(resolved) WHERE resolved = false;

COMMENT ON TABLE public.feedback IS 'Feedback dos usuários: NPS, bugs, sugestões';

-- =============================================================================
-- 3. CAMPOS ADICIONAIS NO SUBSCRIBER
-- =============================================================================

-- Campos de feedback
ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS last_feedback_at timestamp with time zone;

ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS last_nps_at timestamp with time zone;

ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS last_message_at timestamp with time zone DEFAULT now();

ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS nps_score integer;

-- Campos de beta tester
ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS is_beta_tester boolean DEFAULT false;

ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS beta_joined_at timestamp with time zone;

ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS beta_features jsonb DEFAULT '[]'::jsonb;

-- Campo de profile (micro-profiling)
ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS profile text DEFAULT 'curioso' CHECK (profile IN ('curioso', 'profissional', 'investidor'));

-- Índice para beta testers
CREATE INDEX IF NOT EXISTS idx_subscribers_beta ON public.subscribers(is_beta_tester) WHERE is_beta_tester = true;

-- Índice para usuários inativos
CREATE INDEX IF NOT EXISTS idx_subscribers_last_message ON public.subscribers(last_message_at);

-- =============================================================================
-- 4. FUNÇÃO PARA INCREMENTO ATÔMICO (Rate Limiting)
-- =============================================================================

CREATE OR REPLACE FUNCTION increment_counter(
    p_subscriber_id uuid,
    p_counter_field text
)
RETURNS void AS $$
BEGIN
    IF p_counter_field = 'daily_message_count' THEN
        UPDATE subscribers 
        SET daily_message_count = daily_message_count + 1,
            last_message_at = now()
        WHERE id = p_subscriber_id;
    ELSIF p_counter_field = 'daily_ai_count' THEN
        UPDATE subscribers 
        SET daily_ai_count = daily_ai_count + 1
        WHERE id = p_subscriber_id;
    END IF;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION increment_counter IS 'Incrementa contadores de rate limiting de forma atômica';

-- =============================================================================
-- 5. FUNÇÃO PARA RESET DIÁRIO DE CONTADORES
-- =============================================================================

CREATE OR REPLACE FUNCTION reset_daily_counters()
RETURNS void AS $$
BEGIN
    UPDATE subscribers 
    SET daily_message_count = 0,
        daily_ai_count = 0,
        last_reset_at = now()
    WHERE last_reset_at < CURRENT_DATE;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION reset_daily_counters IS 'Reseta contadores diários de todos os usuários';

-- =============================================================================
-- 6. VIEW PARA MÉTRICAS DE ENGAJAMENTO
-- =============================================================================

CREATE OR REPLACE VIEW public.engagement_metrics AS
SELECT 
    s.id,
    s.phone_number,
    s.name,
    s.plan,
    s.is_beta_tester,
    s.is_active,
    s.created_at,
    s.last_message_at,
    s.nps_score,
    EXTRACT(DAY FROM (now() - s.last_message_at)) as days_since_last_message,
    EXTRACT(DAY FROM (now() - s.created_at)) as days_since_signup,
    (SELECT COUNT(*) FROM user_events e WHERE e.subscriber_id = s.id AND e.created_at > now() - interval '7 days') as events_last_7_days,
    (SELECT COUNT(*) FROM feedback f WHERE f.subscriber_id = s.id) as total_feedback
FROM subscribers s
WHERE s.is_active = true;

COMMENT ON VIEW public.engagement_metrics IS 'Métricas de engajamento por usuário ativo';

-- =============================================================================
-- 7. VIEW PARA DASHBOARD DE FEEDBACK
-- =============================================================================

CREATE OR REPLACE VIEW public.feedback_dashboard AS
SELECT 
    feedback_type,
    COUNT(*) as total,
    AVG(score) as avg_score,
    COUNT(*) FILTER (WHERE resolved = false) as unresolved,
    MAX(created_at) as last_feedback
FROM feedback
GROUP BY feedback_type;

COMMENT ON VIEW public.feedback_dashboard IS 'Dashboard resumido de feedback';

-- =============================================================================
-- VERIFICAÇÃO
-- =============================================================================
-- Execute para verificar se a migration foi aplicada:
-- SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name IN ('user_events', 'feedback');
-- SELECT column_name FROM information_schema.columns WHERE table_name = 'subscribers' AND column_name = 'is_beta_tester';
