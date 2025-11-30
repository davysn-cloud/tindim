-- Adicionar usuário de teste
-- IMPORTANTE: Substitua o número pelo seu WhatsApp no formato internacional
-- Exemplo: 5511999999999 (Brasil: 55 + DDD + número)

INSERT INTO subscribers (phone_number, name, interests)
VALUES ('5511999999999', 'Usuário Teste', '["TECH", "CRYPTO", "FINANCE"]')
ON CONFLICT (phone_number) DO UPDATE
SET name = EXCLUDED.name,
    interests = EXCLUDED.interests,
    is_active = true;

-- Ver o usuário criado
SELECT * FROM subscribers WHERE phone_number = '5511999999999';
