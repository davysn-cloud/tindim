# ⚡ Comandos Rápidos - Tindim

## 🚀 Iniciar o Sistema

```bash
# Ativar ambiente virtual (se necessário)
.venv\Scripts\activate

# Iniciar servidor
python -m uvicorn app.main:app --reload
```

O servidor estará em: `http://localhost:8000`
Documentação automática: `http://localhost:8000/docs`

---

## 🧪 Testes Rápidos

### Testar Tudo
```bash
python test_local.py
```

### Health Check
```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/v1/test/health
```

### Coletar Notícias
```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/v1/test/ingest-news -Method POST
```

### Processar com IA
```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/v1/test/process-articles -Method POST
```

### Enviar Resumo (⚠️ Envia WhatsApp real!)
```powershell
Invoke-WebRequest -Uri http://localhost:8000/api/v1/test/send-digest -Method POST
```

---

## 📱 Adicionar Usuário de Teste

### Via SQL (Supabase)
```sql
INSERT INTO subscribers (phone_number, name, interests)
VALUES ('5511999999999', 'Seu Nome', '["TECH", "CRYPTO", "FINANCE"]')
ON CONFLICT (phone_number) DO UPDATE
SET is_active = true;
```

### Via Python
```python
from app.db.client import supabase

supabase.table("subscribers").insert({
    "phone_number": "5511999999999",
    "name": "Seu Nome",
    "interests": ["TECH", "CRYPTO", "FINANCE"]
}).execute()
```

---

## 🔍 Ver Dados no Banco

### Ver Artigos Coletados
```sql
SELECT title, category, processed_at 
FROM articles 
ORDER BY created_at DESC 
LIMIT 10;
```

### Ver Assinantes
```sql
SELECT name, phone_number, interests, is_active 
FROM subscribers;
```

### Ver Conversas Ativas
```sql
SELECT 
  s.name,
  c.message_count,
  c.last_message_at
FROM conversations c
JOIN subscribers s ON c.subscriber_id = s.id
WHERE c.is_active = true;
```

---

## 🌐 Webhook (Receber Mensagens)

### Teste Local com ngrok
```bash
# Terminal 1: Servidor
python -m uvicorn app.main:app --reload

# Terminal 2: ngrok
ngrok http 8000
```

**URL do webhook:** `https://seu-id.ngrok.io/api/v1/webhook/whatsapp`

### Configurar no Meta for Developers
1. WhatsApp > Configuration
2. Callback URL: `https://seu-id.ngrok.io/api/v1/webhook/whatsapp`
3. Verify Token: `insightflow_token_seguro`
4. Subscribe to: `messages`

---

## 🎵 Testar Áudio (Precisa chave ElevenLabs)

### Gerar Áudio para Usuário
```python
import asyncio
from app.services.audio_generator import AudioGeneratorService

async def test():
    audio = AudioGeneratorService()
    url = await audio.generate_personalized_audio("subscriber-uuid")
    print(f"Áudio: {url}")

asyncio.run(test())
```

---

## 🐛 Resolver Problemas

### Reinstalar Dependências
```bash
pip install -r requirements.txt --upgrade
```

### Limpar Cache
```bash
pip cache purge
```

### Ver Logs Detalhados
```bash
# Adicione --log-level debug
python -m uvicorn app.main:app --reload --log-level debug
```

---

## 📦 Deploy Rápido

### Railway
```bash
# 1. Instalar CLI
npm i -g @railway/cli

# 2. Login
railway login

# 3. Deploy
railway up
```

### Render
1. Conecte o repositório no dashboard
2. Configure variáveis de ambiente
3. Deploy automático!

---

## 🔑 Variáveis de Ambiente Essenciais

```env
SUPABASE_URL="https://seu-projeto.supabase.co"
SUPABASE_KEY="sua-chave-service-role"
GOOGLE_API_KEY="sua-gemini-key"
WHATSAPP_API_TOKEN="seu-whatsapp-token"
WHATSAPP_PHONE_NUMBER_ID="seu-phone-id"
WHATSAPP_VERIFY_TOKEN="seu-token-secreto"
ELEVENLABS_API_KEY="sua-elevenlabs-key"  # Opcional
```

---

## 📊 Monitorar Sistema

### Ver Status das Tabelas
```sql
SELECT 
  'articles' as tabela,
  COUNT(*) as total,
  COUNT(CASE WHEN processed_at IS NOT NULL THEN 1 END) as processados
FROM articles
UNION ALL
SELECT 
  'subscribers',
  COUNT(*),
  COUNT(CASE WHEN is_active = true THEN 1 END)
FROM subscribers;
```

### Ver Últimas Atividades
```sql
SELECT 
  'article' as tipo,
  title as descricao,
  created_at
FROM articles
UNION ALL
SELECT 
  'message',
  content,
  created_at
FROM messages
ORDER BY created_at DESC
LIMIT 20;
```

---

## 🎯 Fluxo Completo de Teste

```bash
# 1. Iniciar servidor
python -m uvicorn app.main:app --reload

# 2. Coletar notícias
python test_local.py

# 3. Adicionar usuário no Supabase (SQL)

# 4. Enviar resumo
Invoke-WebRequest -Uri http://localhost:8000/api/v1/test/send-digest -Method POST

# 5. Configurar webhook com ngrok

# 6. Enviar mensagem pelo WhatsApp e ver resposta!
```

---

**Dica:** Mantenha este arquivo aberto para referência rápida! 🚀
