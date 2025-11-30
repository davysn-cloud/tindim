# 📚 Exemplos de Uso da API - Tindim

## Endpoints de Teste

Base URL: `http://localhost:8000/api/v1` (desenvolvimento) ou `https://seu-dominio.com/api/v1` (produção)

### 1. Health Check

Verifica se a API está funcionando.

```bash
curl http://localhost:8000/api/v1/test/health
```

**Resposta:**
```json
{
  "status": "healthy",
  "service": "Tindim API",
  "version": "1.0.0"
}
```

---

### 2. Coletar Notícias (Ingestão)

Coleta notícias dos feeds RSS configurados.

```bash
curl -X POST http://localhost:8000/api/v1/test/ingest-news
```

**Resposta:**
```json
{
  "status": "success",
  "articles_collected": 15
}
```

---

### 3. Processar Artigos com IA

Processa artigos pendentes e gera resumos.

```bash
curl -X POST http://localhost:8000/api/v1/test/process-articles
```

**Resposta:**
```json
{
  "status": "success",
  "articles_processed": 15
}
```

---

### 4. Enviar Resumos via WhatsApp

Envia resumos personalizados para todos os assinantes ativos.

```bash
curl -X POST http://localhost:8000/api/v1/test/send-digest
```

**Resposta:**
```json
{
  "status": "success",
  "message": "Resumos enviados"
}
```

---

### 5. Gerar Áudio Personalizado

Gera um áudio personalizado para um assinante específico.

```bash
curl -X POST http://localhost:8000/api/v1/test/generate-audio \
  -H "Content-Type: application/json" \
  -d '{
    "subscriber_id": "uuid-do-assinante"
  }'
```

**Resposta:**
```json
{
  "status": "success",
  "audio_url": "https://seu-bucket.supabase.co/storage/v1/object/public/audio-digests/audio_20231129_080000.mp3"
}
```

---

### 6. Testar Chat Assistant

Simula uma mensagem de usuário e retorna a resposta do assistente.

```bash
curl -X POST http://localhost:8000/api/v1/test/chat-message \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "5511999999999",
    "message": "Me explica mais sobre a notícia de crypto"
  }'
```

**Resposta:**
```json
{
  "status": "success",
  "response": "Com certeza! A notícia sobre crypto fala sobre... [resposta da IA]"
}
```

---

## Endpoints de Produção

### Webhook do WhatsApp

**Verificação (GET)**
```
GET /api/v1/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=SEU_TOKEN&hub.challenge=CHALLENGE
```

**Receber Mensagens (POST)**
```
POST /api/v1/webhook/whatsapp
```

Este endpoint é chamado automaticamente pelo WhatsApp quando um usuário envia uma mensagem.

---

## Exemplos com Python

### Enviar Resumo Manualmente

```python
import asyncio
from app.services.whatsapp import WhatsAppService

async def main():
    wa = WhatsAppService()
    await wa.broadcast_digest()
    print("Resumos enviados!")

asyncio.run(main())
```

### Gerar Áudio para Usuário

```python
import asyncio
from app.services.audio_generator import AudioGeneratorService

async def main():
    audio_service = AudioGeneratorService()
    audio_url = await audio_service.generate_personalized_audio("subscriber-uuid")
    print(f"Áudio gerado: {audio_url}")

asyncio.run(main())
```

### Processar Mensagem de Chat

```python
import asyncio
from app.services.chat_assistant import ChatAssistantService

async def main():
    chat = ChatAssistantService()
    response = await chat.process_user_message(
        "5511999999999",
        "Quero saber mais sobre IA"
    )
    print(f"Resposta: {response}")

asyncio.run(main())
```

---

## Queries SQL Úteis

### Ver Assinantes Ativos

```sql
SELECT name, phone_number, interests, created_at
FROM subscribers
WHERE is_active = true
ORDER BY created_at DESC;
```

### Ver Últimas Notícias Processadas

```sql
SELECT 
  title,
  category,
  summary_json->>'headline' as headline,
  processed_at
FROM articles
WHERE processed_at IS NOT NULL
ORDER BY processed_at DESC
LIMIT 10;
```

### Ver Conversas Ativas

```sql
SELECT 
  s.name,
  s.phone_number,
  c.message_count,
  c.last_message_at
FROM conversations c
JOIN subscribers s ON c.subscriber_id = s.id
WHERE c.is_active = true
ORDER BY c.last_message_at DESC;
```

### Ver Histórico de Mensagens de uma Conversa

```sql
SELECT 
  role,
  content,
  created_at
FROM messages
WHERE conversation_id = 'uuid-da-conversa'
ORDER BY created_at ASC;
```

### Ver Áudios Gerados

```sql
SELECT 
  s.name,
  a.audio_url,
  a.topics,
  a.sent_at,
  a.created_at
FROM audio_digests a
JOIN subscribers s ON a.subscriber_id = s.id
ORDER BY a.created_at DESC
LIMIT 10;
```

### Adicionar Novo Assinante

```sql
INSERT INTO subscribers (phone_number, name, interests)
VALUES ('5511999999999', 'João Silva', '["TECH", "CRYPTO", "FINANCE"]')
RETURNING *;
```

### Atualizar Interesses de um Assinante

```sql
UPDATE subscribers
SET interests = '["TECH", "AGRO", "BUSINESS"]'
WHERE phone_number = '5511999999999';
```

### Desativar Assinante

```sql
UPDATE subscribers
SET is_active = false
WHERE phone_number = '5511999999999';
```

---

## Testando Localmente com ngrok

Para testar o webhook do WhatsApp localmente:

1. Instale o ngrok: https://ngrok.com/download

2. Execute sua API:
```bash
uvicorn app.main:app --reload
```

3. Em outro terminal, execute o ngrok:
```bash
ngrok http 8000
```

4. Copie a URL gerada (ex: `https://abc123.ngrok.io`)

5. Configure no Meta for Developers:
   - Callback URL: `https://abc123.ngrok.io/api/v1/webhook/whatsapp`

6. Envie uma mensagem de teste pelo WhatsApp!

---

## Monitoramento

### Verificar Logs em Tempo Real

```bash
# Se estiver usando Docker
docker logs -f container-name

# Se estiver usando systemd
journalctl -u tindim -f

# Logs do Railway/Render
# Acesse o dashboard e veja a aba "Logs"
```

### Métricas Importantes

- **Taxa de entrega**: Quantas mensagens foram enviadas com sucesso
- **Taxa de resposta**: Quantos usuários interagem com o chat
- **Artigos processados/dia**: Quantas notícias foram resumidas
- **Áudios gerados/dia**: Quantos áudios foram criados
- **Conversas ativas**: Quantas conversas estão em andamento

---

## Dicas de Performance

1. **Cache de Resumos**: Resumos são gerados uma vez e enviados para todos os usuários interessados no tópico

2. **Rate Limiting**: O WhatsApp tem limites de mensagens por segundo. O código já inclui delays (`asyncio.sleep`)

3. **Processamento em Lote**: Artigos são processados em lote para otimizar chamadas à API do Gemini

4. **Áudio Assíncrono**: A geração de áudio é feita de forma assíncrona para não bloquear outras operações

---

**Precisa de mais exemplos?** Consulte o código-fonte ou abra uma issue!
