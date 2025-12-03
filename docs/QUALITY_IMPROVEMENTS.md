# Melhorias na Qualidade de Agregação de Notícias do Tindim

## Resumo das Implementações

Este documento descreve as melhorias implementadas no sistema de agregação e processamento de notícias do Tindim para aumentar a qualidade do conteúdo entregue aos usuários.

---

## 1. Filtros de Qualidade na Ingestão (`ingestion.py`)

### Padrões de Exclusão por Título
- **Loteria/Jogos de azar**: Quina, Lotofácil, Mega-Sena, sorteios
- **Horóscopo/Astrologia**: previsões astrológicas, signos
- **Clickbait**: "Não vai acreditar", "Chocante", "Impressionante"
- **Obituários**: falecimentos, velórios, enterros

### Padrões de Exclusão por Conteúdo
- Dezenas sorteadas
- Apostas em lotéricas
- Prêmios acumulados
- Sorteios da Caixa Econômica

### Limites de Tamanho
- **Título mínimo**: 15 caracteres
- **Conteúdo mínimo**: 200 caracteres (após remoção de HTML)

---

## 2. Deduplicação de Artigos (`ai_processor.py`)

### Algoritmo
- Usa `SequenceMatcher` para calcular similaridade entre textos
- Compara título + headline de artigos
- **Threshold de similaridade**: 75%

### Cache de Deduplicação
- Carrega headlines processados nas últimas 24h
- Evita enviar notícias duplicadas ou muito similares
- Artigos duplicados são marcados com `{"error": "duplicate"}`

---

## 3. Validação de Qualidade do Resumo

### Campos Obrigatórios
- `headline` (mínimo 20 caracteres)
- `bullet_points` (mínimo 2 pontos)
- `sentiment` (POSITIVO, NEUTRO, NEGATIVO)
- `category` (uma das 12 categorias válidas)

### Tratamento de Erros
- Artigos bloqueados pela IA: `{"error": "blocked_by_safety"}`
- Respostas inválidas: `{"error": "invalid_response"}`
- Falha na validação: `{"error": "quality_check_failed: [motivo]"}`
- Erro de JSON: `{"error": "json_parse_error"}`

---

## 4. Score de Relevância (0-100)

### Critérios de Pontuação
| Critério | Pontos |
|----------|--------|
| Base | +50 |
| 3+ bullet points | +10 |
| Notícia < 6 horas | +15 |
| Notícia < 12 horas | +10 |
| Sentimento definido | +5 |
| Fonte premium (InfoMoney, Brazil Journal) | +15 |
| Conteúdo curto (< 500 chars) | -20 |

### Uso
- Artigos são ordenados por score antes do envio
- Artigos mais relevantes aparecem primeiro em cada categoria

---

## 5. Novas Categorias

### Categorias Adicionadas
- **WORLD** 🌍: Notícias internacionais, geopolítica, conflitos
- **LIFESTYLE** 🍷: Gastronomia, viagens, cultura, vinhos, moda

### Lista Completa de Categorias
| Categoria | Emoji | Descrição |
|-----------|-------|-----------|
| TECH | 💻 | Tecnologia, startups, apps, IA |
| AGRO | 🌾 | Agronegócio, commodities agrícolas |
| CRYPTO | ₿ | Criptomoedas, blockchain, web3 |
| FINANCE | 💰 | Mercado financeiro, investimentos |
| BUSINESS | 📊 | Negócios em geral, empresas |
| POLITICS | 🏛️ | Política nacional e internacional |
| SPORTS | ⚽ | Esportes, futebol, F1 |
| ENTERTAINMENT | 🎬 | Cinema, música, TV |
| HEALTH | 🏥 | Saúde, medicina, bem-estar |
| SCIENCE | 🔬 | Ciência, pesquisa, descobertas |
| WORLD | 🌍 | Notícias internacionais |
| LIFESTYLE | 🍷 | Gastronomia, viagens, cultura |

---

## 6. Melhorias no Prompt da IA

### Regras de Qualidade
1. Headline mínimo de 25 caracteres
2. Exatamente 3 bullet points substantivos
3. Cada bullet point com mínimo 50 caracteres
4. Dados concretos (números, nomes, datas)
5. Rejeição de conteúdo de baixa relevância

### Regras de Estilo
1. Português do Brasil
2. Tom profissional mas acessível
3. Emojis relevantes ao conteúdo
4. Evitar clickbait

---

## Arquivos Modificados

1. `app/services/ingestion.py` - Filtros de qualidade na ingestão
2. `app/services/ai_processor.py` - Deduplicação, validação, score
3. `app/core/prompts.py` - Prompt melhorado com regras de qualidade
4. `app/services/whatsapp.py` - Novas categorias e ordenação por relevância

---

## Métricas de Log

O sistema agora registra:
- Artigos rejeitados na ingestão (com motivo)
- Artigos duplicados detectados
- Artigos rejeitados por qualidade
- Score de relevância de cada artigo processado

Exemplo de log:
```
INFO: Cache de deduplicação: 45 artigos recentes
INFO: Artigo processado (score=75): Flamengo conquista Libertadores...
INFO: Artigo duplicado detectado: Flamengo vence Palmeiras...
WARNING: Resumo rejeitado (headline muito curto): Fim de ano...
INFO: Processamento finalizado: 12 processados, 3 duplicados, 2 rejeitados por qualidade
```
