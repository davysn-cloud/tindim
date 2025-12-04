# 🧪 Plano de Beta Testing - Tindim

## Visão Geral

Este documento descreve o sistema de feedback, analytics, rate limiting e beta testing implementado no Tindim.

---

## 1. 📊 Sistema de Analytics

### Tabela: `user_events`
Rastreia todos os eventos do usuário para análise de comportamento.

**Tipos de eventos:**
- `message_sent` - Usuário enviou mensagem
- `message_received` - Usuário recebeu mensagem
- `button_clicked` - Clicou em botão interativo
- `onboarding_step` - Avançou no onboarding
- `digest_opened` - Abriu/leu resumo
- `audio_played` - Ouviu áudio
- `feedback_given` - Deu feedback
- `bug_reported` - Reportou bug
- `feature_requested` - Sugeriu feature
- `config_changed` - Alterou configurações

### Uso
```python
from app.services.analytics import analytics

# Tracking de evento
await analytics.track_event(subscriber_id, "button_clicked", {"button_id": "tech"})

# Métricas de atividade
activity = await analytics.get_user_activity(subscriber_id, days=7)
```

---

## 2. 💬 Sistema de Feedback

### 2.1 Feedback Implícito (Inatividade)
Após 3 dias sem atividade, o sistema envia automaticamente:

```
👋 Oi! Percebi que você sumiu...

Falei demais? Ou as notícias estavam chatas? 🤔

Me ajuda a melhorar:
• Digite 1 para 'Muitas mensagens'
• Digite 2 para 'Conteúdo irrelevante'
• Digite 3 para 'Tudo certo, só ocupado'
```

### 2.2 NPS (Sexta-feira)
Toda sexta-feira às 18h, usuários elegíveis recebem:

```
🎉 Sextou!

Rapidinho: de 0 a 10, qual a chance de você me indicar pra um amigo?

E se quiser, conta: o que falta pra ser um 10? 🚀
```

### 2.3 Comandos de Feedback

| Comando | Descrição |
|---------|-----------|
| `/bug <descrição>` | Reporta um bug |
| `!erro <descrição>` | Reporta um bug (alternativo) |
| `/ideia <descrição>` | Sugere uma feature |
| `!sugestao <descrição>` | Sugere uma feature (alternativo) |

**Exemplo:**
```
/bug A mensagem de boas-vindas não apareceu
/ideia Quero receber notícias sobre esportes
```

---

## 3. 🚦 Rate Limiting

### Limites por Plano

| Plano | Mensagens/dia | Interações IA/dia |
|-------|---------------|-------------------|
| Generalista | 100 | 10 |
| Estrategista | 300 | 30 |
| Beta Tester | 500 | 50 |

### Uso
```python
from app.services.rate_limiter import rate_limiter

# Verificar limite
allowed, message = await rate_limiter.check_limit(subscriber_id, "ai")

# Incrementar contador
await rate_limiter.increment_counter(subscriber_id, "ai")

# Estatísticas de uso
stats = await rate_limiter.get_usage_stats(subscriber_id)
```

---

## 4. 📅 Jobs Agendados

| Job | Horário | Descrição |
|-----|---------|-----------|
| `run_daily_cycle` | 07:00, 18:00 | Coleta, processa e envia resumos |
| `run_audio_broadcast` | 08:00 | Gera e envia áudios |
| `run_feedback_jobs` | 18:00 (21:00 UTC) | Verifica inativos + NPS (sexta) |
| `run_daily_reset` | 00:05 UTC | Reseta contadores diários |
| Ingestão | A cada 2h | Coleta novas notícias |

---

## 5. 🏷️ Beta Testers

### Campos no Subscriber
- `is_beta_tester` - Flag de beta tester
- `beta_joined_at` - Data de entrada no beta
- `beta_features` - Features específicas habilitadas

### Benefícios
- Limites expandidos (500 msgs, 50 IA/dia)
- Acesso antecipado a features
- Canal direto para feedback

### Adicionar Beta Tester (SQL)
```sql
UPDATE subscribers 
SET is_beta_tester = true, 
    beta_joined_at = now() 
WHERE phone_number = '5521999999999';
```

---

## 6. 📋 Migration SQL

Execute no Supabase SQL Editor:
```
migration_beta_testing.sql
```

Isso cria:
- Tabela `user_events`
- Tabela `feedback`
- Campos adicionais em `subscribers`
- Funções de rate limiting
- Views de métricas

---

## 7. 🎯 Métricas a Acompanhar

### Engajamento
- **DAU/MAU** - Usuários ativos diários/mensais
- **Retention D1/D7/D30** - Retenção por período
- **Messages per User** - Média de mensagens

### Qualidade
- **NPS Score** - Net Promoter Score médio
- **Bug Reports** - Quantidade de bugs reportados
- **Response Time** - Tempo médio de resposta

### Conversão
- **Trial to Paid** - Taxa de conversão
- **Churn Rate** - Taxa de cancelamento
- **Upgrade Rate** - Generalista → Estrategista

---

## 8. 📁 Arquivos Implementados

```
app/services/
├── analytics.py      # Tracking de eventos
├── feedback.py       # Coleta de feedback
├── rate_limiter.py   # Controle de limites
└── scheduler.py      # Jobs agendados (atualizado)

app/services/whatsapp_onboarding.py  # Handlers de /bug e /ideia

migrations/
└── migration_beta_testing.sql  # Schema do banco
```

---

## 9. 🚀 Próximos Passos

1. **Rodar migration** no Supabase
2. **Deploy** da aplicação
3. **Recrutar 10-20 beta testers**
4. **Monitorar métricas** por 2 semanas
5. **Iterar** baseado no feedback

---

*Documento criado em: Dezembro 2024*
