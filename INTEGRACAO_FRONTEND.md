# 🔗 Integração Frontend + Backend - Tindim

Este guia explica como rodar o frontend (TindimDigest) conectado ao backend (FastAPI).

## 📁 Estrutura do Projeto

```
finance/
├── app/                    # Backend FastAPI
│   ├── api/v1/endpoints/
│   │   ├── auth.py         # Autenticação (signup, login, logout)
│   │   ├── stripe.py       # Pagamentos
│   │   └── ...
│   └── ...
├── TindimDigest/           # Frontend React
│   ├── client/src/
│   │   ├── lib/api.ts      # Configuração da API
│   │   ├── hooks/use-auth.ts
│   │   └── pages/
│   └── ...
└── schema_users.sql        # Schema de usuários web
```

---

## 🚀 Setup Local

### 1. Backend (FastAPI)

```bash
# Na pasta finance/
cd c:\InsightFlow\finance

# Instalar dependências
pip install -r requirements.txt

# Configurar .env (copiar de .env.example)
# Adicionar as variáveis do Stripe

# Rodar o servidor
python -m uvicorn app.main:app --reload --port 8000
```

O backend estará em: `http://localhost:8000`

### 2. Banco de Dados

Execute no Supabase SQL Editor:
1. Primeiro: `schema_tindim.sql` (se ainda não executou)
2. Depois: `schema_users.sql` (novo, para usuários web)

### 3. Frontend (React)

```bash
# Na pasta TindimDigest/
cd c:\InsightFlow\finance\TindimDigest

# Instalar dependências
npm install

# Configurar .env
# VITE_API_URL=http://localhost:8000

# Rodar em desenvolvimento
npm run dev
```

O frontend estará em: `http://localhost:5000`

---

## 🔐 Configurar Stripe

### 1. Criar Conta no Stripe
1. Acesse [dashboard.stripe.com](https://dashboard.stripe.com)
2. Crie uma conta (modo teste)

### 2. Criar Produtos e Preços
No Stripe Dashboard > Products:

**Plano Generalista:**
- Nome: "Tindim Generalista"
- Preço: R$ 9,90/mês (recorrente)
- Copie o `price_id`

**Plano Estrategista:**
- Nome: "Tindim Estrategista"
- Preço: R$ 29,90/mês (recorrente)
- Copie o `price_id`

### 3. Configurar Webhook
No Stripe Dashboard > Developers > Webhooks:
1. Adicionar endpoint: `https://seu-backend.onrender.com/api/v1/stripe/webhook`
2. Selecionar eventos:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_succeeded`
   - `invoice.payment_failed`
3. Copie o `Webhook Secret`

### 4. Adicionar ao .env do Backend
```env
STRIPE_SECRET_KEY="sk_test_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
STRIPE_PRICE_GENERALISTA="price_..."
STRIPE_PRICE_ESTRATEGISTA="price_..."
```

---

## 🌐 Deploy em Produção

### Backend (Render)
O backend já está no Render. Adicione as novas variáveis:
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_GENERALISTA`
- `STRIPE_PRICE_ESTRATEGISTA`
- `FRONTEND_URL` (URL do frontend em produção)
- `PRODUCTION_FRONTEND_URL` (mesma URL)

### Frontend (Vercel ou Netlify)

#### Opção A: Vercel (Recomendado)
```bash
# Instalar Vercel CLI
npm i -g vercel

# Na pasta TindimDigest/
cd TindimDigest
vercel
```

Configure a variável de ambiente no dashboard:
- `VITE_API_URL` = `https://tindim.onrender.com`

#### Opção B: Netlify
1. Conecte o repositório no Netlify
2. Build command: `npm run build`
3. Publish directory: `dist`
4. Variável: `VITE_API_URL` = `https://tindim.onrender.com`

---

## 🔄 Fluxo de Autenticação

1. **Signup (Onboarding)**
   - Usuário preenche email, senha, nome, interesses, plano
   - Frontend chama `POST /api/v1/auth/signup`
   - Backend cria usuário com trial de 5 dias
   - Retorna token JWT
   - Frontend salva token no localStorage

2. **Login**
   - Frontend chama `POST /api/v1/auth/login`
   - Backend verifica credenciais
   - Retorna token JWT

3. **Checkout (Pagamento)**
   - Usuário clica em "Assinar"
   - Frontend chama `POST /api/v1/stripe/create-checkout`
   - Backend cria sessão no Stripe
   - Redireciona para página de pagamento do Stripe
   - Após pagamento, Stripe envia webhook
   - Backend atualiza status da assinatura

4. **Gerenciar Assinatura**
   - Usuário clica em "Gerenciar assinatura"
   - Frontend chama `POST /api/v1/stripe/create-portal`
   - Redireciona para Customer Portal do Stripe

---

## 📱 Vincular WhatsApp

Após o usuário se cadastrar no site, ele pode vincular seu WhatsApp:

1. No perfil, adiciona o número de telefone
2. Backend cria/atualiza registro na tabela `subscribers`
3. Usuário passa a receber os resumos no WhatsApp

---

## 🧪 Testar Localmente

### 1. Iniciar Backend
```bash
cd c:\InsightFlow\finance
python -m uvicorn app.main:app --reload
```

### 2. Iniciar Frontend
```bash
cd c:\InsightFlow\finance\TindimDigest
npm run dev
```

### 3. Acessar
- Frontend: http://localhost:5000
- Backend API: http://localhost:8000/docs

### 4. Testar Fluxo
1. Acesse http://localhost:5000
2. Clique em "Teste grátis"
3. Preencha o onboarding
4. Verifique se o usuário foi criado no Supabase

---

## 🐛 Troubleshooting

### CORS Error
Se aparecer erro de CORS:
1. Verifique se `FRONTEND_URL` está correto no backend
2. Verifique se o frontend está usando a URL correta da API

### Token Inválido
Se o login não funcionar:
1. Limpe o localStorage do navegador
2. Verifique se a tabela `sessions` existe no Supabase

### Stripe Webhook Falha
1. Verifique se o `STRIPE_WEBHOOK_SECRET` está correto
2. Use `stripe listen --forward-to localhost:8000/api/v1/stripe/webhook` para testar localmente

---

## 📋 Checklist de Deploy

- [ ] Backend rodando no Render
- [ ] Variáveis do Stripe configuradas no Render
- [ ] Schema `schema_users.sql` executado no Supabase
- [ ] Frontend deployado (Vercel/Netlify)
- [ ] `VITE_API_URL` configurado no frontend
- [ ] `FRONTEND_URL` configurado no backend
- [ ] Webhook do Stripe apontando para o backend
- [ ] Testar signup completo
- [ ] Testar checkout do Stripe
