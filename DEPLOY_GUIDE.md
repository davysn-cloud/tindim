# 🚀 Guia de Deploy - Tindim

## Pré-requisitos

- [ ] Conta no Supabase (banco de dados)
- [ ] Conta no Google AI Studio (Gemini API)
- [ ] Conta no Meta for Developers (WhatsApp Business API)
- [ ] Conta no ElevenLabs (geração de áudio)
- [ ] Servidor com Python 3.9+ (Railway, Render, AWS, etc.)

## Passo a Passo

### 1. Configurar Supabase

1. Crie um novo projeto no [Supabase](https://supabase.com)
2. Vá em **SQL Editor** e execute `schema_tindim.sql`
3. Vá em **Storage** e crie um bucket chamado `audio-digests`
4. Execute `setup_storage.sql` para configurar permissões
5. Copie a **URL** e **anon/service key** do projeto

### 2. Configurar Google Gemini

1. Acesse [Google AI Studio](https://aistudio.google.com)
2. Crie uma API Key
3. Copie a chave

### 3. Configurar WhatsApp Business API

1. Acesse [Meta for Developers](https://developers.facebook.com)
2. Crie um app e ative **WhatsApp Business API**
3. Configure um número de telefone de teste
4. Copie:
   - `WHATSAPP_API_TOKEN` (token de acesso)
   - `WHATSAPP_PHONE_NUMBER_ID` (ID do número)
5. Crie um `WHATSAPP_VERIFY_TOKEN` (qualquer string secreta)

### 4. Configurar ElevenLabs

1. Crie conta no [ElevenLabs](https://elevenlabs.io)
2. Vá em **Profile** > **API Keys**
3. Copie a API Key
4. Escolha uma voz em **VoiceLab** e copie o Voice ID (ou use o padrão: `21m00Tcm4TlvDq8ikWAM`)

### 5. Configurar Variáveis de Ambiente

Crie um arquivo `.env` com base no `.env.example`:

```bash
SUPABASE_URL="https://seu-projeto.supabase.co"
SUPABASE_KEY="sua-chave-service-role"
GOOGLE_API_KEY="sua-gemini-key"
WHATSAPP_API_TOKEN="seu-whatsapp-token"
WHATSAPP_PHONE_NUMBER_ID="seu-phone-id"
WHATSAPP_VERIFY_TOKEN="seu-verify-token-secreto"
ELEVENLABS_API_KEY="sua-elevenlabs-key"
ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"
```

### 6. Deploy da Aplicação

#### Opção A: Railway

1. Conecte seu repositório no [Railway](https://railway.app)
2. Adicione as variáveis de ambiente
3. Deploy automático!

#### Opção B: Render

1. Crie um novo **Web Service** no [Render](https://render.com)
2. Conecte o repositório
3. Configure:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Adicione as variáveis de ambiente
5. Deploy!

#### Opção C: Docker (qualquer servidor)

```bash
# Build
docker build -t tindim .

# Run
docker run -d \
  --env-file .env \
  -p 8000:8000 \
  tindim
```

### 7. Configurar Webhook do WhatsApp

1. Após deploy, copie a URL pública (ex: `https://seu-app.railway.app`)
2. No Meta for Developers:
   - Vá em **WhatsApp** > **Configuration**
   - **Callback URL**: `https://seu-app.railway.app/api/v1/webhook/whatsapp`
   - **Verify Token**: o mesmo do `.env`
   - **Webhook fields**: marque `messages`
3. Clique em **Verify and Save**

### 8. Testar

#### Teste 1: Health Check
```bash
curl https://seu-app.railway.app/api/v1/test/health
```

#### Teste 2: Coletar Notícias
```bash
curl -X POST https://seu-app.railway.app/api/v1/test/ingest-news
```

#### Teste 3: Processar com IA
```bash
curl -X POST https://seu-app.railway.app/api/v1/test/process-articles
```

#### Teste 4: Enviar Resumo
```bash
curl -X POST https://seu-app.railway.app/api/v1/test/send-digest
```

### 9. Adicionar Primeiro Usuário

Execute no Supabase SQL Editor:

```sql
INSERT INTO subscribers (phone_number, name, interests)
VALUES ('5511999999999', 'Seu Nome', '["TECH", "CRYPTO", "FINANCE"]');
```

### 10. Monitorar

- **Logs**: Veja os logs no painel do Railway/Render
- **Banco**: Monitore tabelas no Supabase
- **WhatsApp**: Veja mensagens no Meta for Developers > Webhooks

## 🔧 Troubleshooting

### Webhook não funciona
- Certifique-se de que a URL está acessível publicamente
- Verifique se o verify token está correto
- Veja logs do webhook no Meta for Developers

### Áudio não é enviado
- Confirme que o bucket `audio-digests` existe
- Verifique credenciais do ElevenLabs
- Veja logs para erros de API

### Scheduler não executa
- Certifique-se de que o servidor está em UTC ou ajuste os horários
- Verifique se o processo não está sendo reiniciado constantemente

## 📊 Monitoramento de Custos

### APIs Gratuitas (com limites)
- **Supabase**: 500MB DB, 1GB Storage
- **Google Gemini**: 60 requisições/minuto (free tier)
- **WhatsApp**: 1000 conversas/mês (free tier)
- **ElevenLabs**: 10.000 caracteres/mês (free tier)

### Estimativa para 100 usuários/dia
- **Gemini**: ~200 requisições/dia = OK
- **WhatsApp**: ~200 mensagens/dia = OK
- **ElevenLabs**: ~15.000 caracteres/dia = Precisa plano pago (~$5/mês)

## 🎯 Próximos Passos

1. Configure domínio personalizado
2. Adicione SSL/HTTPS
3. Configure backups do Supabase
4. Implemente analytics
5. Crie landing page para inscrições

---

**Dúvidas?** Abra uma issue no repositório!
