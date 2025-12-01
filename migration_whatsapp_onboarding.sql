-- Migration: Adiciona campos para onboarding via WhatsApp
-- Execute este arquivo no Supabase SQL Editor

-- 1. Adiciona coluna onboarding_state
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'onboarding_state') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN onboarding_state text DEFAULT 'new_lead';
    END IF;
END $$;

-- 2. Adiciona coluna onboarding_data (JSONB para dados temporários)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'onboarding_data') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN onboarding_data jsonb DEFAULT '{}'::jsonb;
    END IF;
END $$;

-- 3. Adiciona coluna tone (tom preferido)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'tone') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN tone text DEFAULT 'casual';
    END IF;
END $$;

-- 4. Adiciona coluna stripe_customer_id
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'stripe_customer_id') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN stripe_customer_id text;
    END IF;
END $$;

-- 5. Adiciona coluna stripe_subscription_id
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'stripe_subscription_id') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN stripe_subscription_id text;
    END IF;
END $$;

-- 6. Adiciona coluna subscription_status
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'subscription_status') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN subscription_status text DEFAULT 'none';
    END IF;
END $$;

-- 7. Atualiza subscribers existentes para estado 'active' se is_active = true
UPDATE public.subscribers 
SET onboarding_state = 'active' 
WHERE is_active = true AND (onboarding_state IS NULL OR onboarding_state = 'new_lead');

-- 8. Atualiza is_active para false em novos leads
UPDATE public.subscribers 
SET is_active = false 
WHERE onboarding_state = 'new_lead' OR onboarding_state IS NULL;

-- 9. Adiciona constraint de check para onboarding_state (com novo estado selecting_profile)
DO $$
BEGIN
    -- Remove constraint antiga se existir
    ALTER TABLE public.subscribers DROP CONSTRAINT IF EXISTS subscribers_onboarding_state_check;
    
    -- Adiciona nova constraint com todos os estados
    ALTER TABLE public.subscribers 
    ADD CONSTRAINT subscribers_onboarding_state_check 
    CHECK (onboarding_state IN (
        'new_lead', 'selecting_interests', 'selecting_profile', 'selecting_tone', 
        'demo_sent', 'awaiting_payment', 'active'
    ));
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

-- 10. Adiciona índice para busca por estado de onboarding
CREATE INDEX IF NOT EXISTS idx_subscribers_onboarding_state 
ON public.subscribers(onboarding_state);

-- Confirma as alterações
SELECT 
    id, 
    phone_number, 
    name, 
    is_active,
    onboarding_state,
    plan,
    subscription_status
FROM public.subscribers 
LIMIT 10;
