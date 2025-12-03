-- Migration: Adiciona campos de configuração de horário para subscribers
-- Execute este arquivo no Supabase SQL Editor
-- Data: 2024-12-02

-- =============================================================================
-- 1. ADICIONA COLUNA DE HORÁRIOS PREFERIDOS
-- =============================================================================

-- Adiciona coluna para horário preferido (formato HH:MM)
-- Generalista: usa apenas o primeiro horário
-- Estrategista: usa ambos os horários
ALTER TABLE public.subscribers 
ADD COLUMN IF NOT EXISTS preferred_times jsonb DEFAULT '["07:00", "19:00"]'::jsonb;

-- Comentário explicativo
COMMENT ON COLUMN public.subscribers.preferred_times IS 
'Horários preferidos para receber resumos. Generalista usa apenas o primeiro, Estrategista usa ambos. Formato: ["HH:MM", "HH:MM"]';

-- =============================================================================
-- 2. ATUALIZA ESTADOS DE ONBOARDING
-- =============================================================================

-- Remove constraint antiga
ALTER TABLE public.subscribers 
DROP CONSTRAINT IF EXISTS subscribers_onboarding_state_check;

-- Adiciona nova constraint com estados de configuração
ALTER TABLE public.subscribers 
ADD CONSTRAINT subscribers_onboarding_state_check 
CHECK (onboarding_state IN (
    'new_lead',              -- Primeiro contato
    'selecting_interests',   -- Escolhendo interesses
    'selecting_profile',     -- Micro-profiling
    'selecting_tone',        -- Escolhendo tom
    'demo_sent',             -- Resumo demo enviado
    'awaiting_payment',      -- Aguardando pagamento
    'active',                -- Assinante ativo
    'configuring',           -- Menu de configurações
    'config_schedule',       -- Alterando horários
    'config_interests'       -- Alterando tópicos
));

-- =============================================================================
-- 3. ÍNDICES PARA PERFORMANCE
-- =============================================================================

-- Índice para buscar por horário (para o scheduler)
CREATE INDEX IF NOT EXISTS idx_subscribers_preferred_times 
ON public.subscribers USING gin (preferred_times);

-- =============================================================================
-- 4. ATUALIZA USUÁRIOS EXISTENTES (opcional)
-- =============================================================================

-- Define horários padrão para usuários que não têm
UPDATE public.subscribers 
SET preferred_times = '["07:00", "19:00"]'::jsonb 
WHERE preferred_times IS NULL;

-- =============================================================================
-- VERIFICAÇÃO
-- =============================================================================
-- Execute para verificar se a migration foi aplicada:
-- SELECT column_name, data_type, column_default 
-- FROM information_schema.columns 
-- WHERE table_name = 'subscribers' AND column_name = 'preferred_times';
