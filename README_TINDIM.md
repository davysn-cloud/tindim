# 📱 Tindim - Notícias Personalizadas via WhatsApp

Sistema inteligente que envia notícias personalizadas via WhatsApp baseado nos tópicos de interesse do usuário, com resumos em texto, áudios gerados por IA e chat interativo.

## 🚀 Funcionalidades Implementadas

### ✅ 1. Personalização por Tópicos
- Usuário escolhe tópicos de interesse: **TECH**, **AGRO**, **CRYPTO**, **FINANCE**, **BUSINESS**, etc.
- Recebe apenas notícias dos tópicos selecionados
- Mensagens agrupadas por categoria com emojis

### ✅ 2. Resumos de Texto
- Resumos gerados por IA (Google Gemini)
- Enviados 2x ao dia (07:00 e 18:00)
- Formatação otimizada para WhatsApp
- Análise de sentimento (positivo/negativo/neutro)

### ✅ 3. Áudios Personalizados
- Geração de roteiro personalizado com nome do usuário
- Conversão texto-para-fala via ElevenLabs
- Áudio enviado às 08:00 (após resumo da manhã)
- Duração: 1-3 minutos

### ✅ 4. Chat Interativo
- Usuário pode aprofundar qualquer notícia
- Limite de 10 mensagens por conversa
- Respostas contextualizadas pela IA
- Histórico de conversas salvo no banco

### ✅ 5. Webhook WhatsApp
- Recebe mensagens dos usuários em tempo real
- Processa perguntas e envia respostas automaticamente
- Endpoint: `/api/v1/webhook/whatsapp`

## 📊 Arquitetura

```
┌─────────────┐
│  RSS Feeds  │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Ingestion      │ ──► Coleta notícias a cada 2h
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI Processor   │ ──► Categoriza e resume (Gemini)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│  WhatsApp Service                   │
│  • Filtro por tópicos               │
│  • Envio de texto (07:00 e 18:00)   │
│  • Envio de áudio (08:00)           │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  Chat Assistant │ ──► Responde perguntas (limite 10 msgs)
└─────────────────┘
```

## 🗄️ Banco de Dados

### Tabelas Principais

1. **articles** - Notícias coletadas e processadas
2. **subscribers** - Usuários e seus interesses
3. **conversations** - Sessões de chat ativo
4. **messages** - Histórico de mensagens
5. **audio_digests** - Áudios gerados

Execute o schema: `schema_tindim.sql` no Supabase SQL Editor.

## ⚙️ Configuração

### 1. Variáveis de Ambiente

Copie `.env.example` para `.env` e preencha:

```bash
# Supabase
SUPABASE_URL="https://sua-url.supabase.co"
SUPABASE_KEY="sua-chave"

# Google Gemini
GOOGLE_API_KEY="sua-api-key"

# WhatsApp Cloud API
WHATSAPP_API_TOKEN="seu-token"
WHATSAPP_PHONE_NUMBER_ID="seu-id"
WHATSAPP_VERIFY_TOKEN="token-para-webhook"

# ElevenLabs
ELEVENLABS_API_KEY="sua-api-key"
ELEVENLABS_VOICE_ID="21m00Tcm4TlvDq8ikWAM"
```

### 2. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar Webhook do WhatsApp

1. No Meta for Developers, configure o webhook:
   - URL: `https://seu-dominio.com/api/v1/webhook/whatsapp`
   - Verify Token: o mesmo do `.env`
   - Subscribe to: `messages`

2. Certifique-se de que a API está acessível publicamente (use ngrok para testes)

### 4. Criar Bucket no Supabase Storage

1. Acesse Supabase Dashboard > Storage
2. Crie um bucket chamado `audio-digests`
3. Configure como público (ou ajuste as políticas RLS)

## 🏃 Executar

```bash
uvicorn app.main:app --reload
```

O scheduler iniciará automaticamente:
- **07:00 e 18:00**: Resumos de texto
- **08:00**: Áudios personalizados
- **A cada 2h**: Coleta de notícias

## 📝 Como Usar

### Para Usuários

1. **Inscrição**: Adicione o usuário no banco (via API ou manualmente)
   ```sql
   INSERT INTO subscribers (phone_number, name, interests)
   VALUES ('5511999999999', 'João', '["TECH", "CRYPTO"]');
   ```

2. **Receber Notícias**: Automático nos horários agendados

3. **Chat Interativo**: Responda qualquer mensagem do Tindim para aprofundar

### Para Desenvolvedores

#### Enviar Resumo Manual
```python
from app.services.whatsapp import WhatsAppService
wa = WhatsAppService()
await wa.broadcast_digest()
```

#### Gerar Áudio para Usuário Específico
```python
from app.services.audio_generator import AudioGeneratorService
audio = AudioGeneratorService()
url = await audio.generate_personalized_audio("subscriber-uuid")
```

#### Processar Mensagem de Chat
```python
from app.services.chat_assistant import ChatAssistantService
chat = ChatAssistantService()
response = await chat.process_user_message("5511999999999", "Me explica mais sobre crypto")
```

## 🎯 Próximas Melhorias Sugeridas

1. **Interface Web de Inscrição**
   - Formulário para usuário escolher tópicos
   - Gerenciamento de preferências

2. **Analytics**
   - Dashboard de métricas (mensagens enviadas, taxa de resposta)
   - Tópicos mais populares

3. **Múltiplos Idiomas**
   - Detecção automática de idioma
   - Suporte para inglês, espanhol, etc.

4. **Agendamento Personalizado**
   - Usuário escolhe horários de recebimento
   - Fuso horário individual

5. **Integração com n8n**
   - Fluxos visuais para automação
   - Webhooks customizados

6. **Resumo Semanal**
   - Compilação das principais notícias da semana
   - Enviado aos domingos

## 🐛 Troubleshooting

### Webhook não recebe mensagens
- Verifique se a URL está acessível publicamente
- Confirme que o `WHATSAPP_VERIFY_TOKEN` está correto
- Veja logs do WhatsApp no Meta for Developers

### Áudio não é gerado
- Verifique credenciais do ElevenLabs
- Confirme que o bucket `audio-digests` existe no Supabase
- Veja logs para erros de API

### Notícias não são categorizadas corretamente
- Ajuste o prompt em `app/core/prompts.py`
- Aumente a temperatura do modelo se necessário
- Adicione exemplos ao prompt

## 📄 Licença

MIT

---

**Desenvolvido com ❤️ para o Tindim**
