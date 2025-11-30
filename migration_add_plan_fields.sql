-- Migration: Adiciona campos de plano e controle de uso na tabela subscribers
-- Execute este arquivo no Supabase SQL Editor

-- 1. Adiciona coluna plan se não existir
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'plan') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN plan text DEFAULT 'generalista' 
        CHECK (plan IN ('generalista', 'estrategista'));
    END IF;
END $$;

-- 2. Adiciona coluna daily_ai_count se não existir
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'subscribers' AND column_name = 'daily_ai_count') THEN
        ALTER TABLE public.subscribers 
        ADD COLUMN daily_ai_count integer DEFAULT 0;
    END IF;
END $$;

-- 3. Atualiza subscribers existentes para ter o plano padrão
UPDATE public.subscribers 
SET plan = 'generalista' 
WHERE plan IS NULL;

-- 4. Atualiza daily_ai_count para 0 onde for NULL
UPDATE public.subscribers 
SET daily_ai_count = 0 
WHERE daily_ai_count IS NULL;

-- Confirma as alterações
SELECT 
    id, 
    phone_number, 
    name, 
    plan, 
    daily_message_count, 
    daily_ai_count 
FROM public.subscribers 
LIMIT 5;
