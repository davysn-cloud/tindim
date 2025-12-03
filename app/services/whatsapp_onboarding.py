"""
Serviço de Onboarding via WhatsApp
Fluxo conversacional: Lead -> Interesses -> Tom -> Resumo -> Pagamento -> Ativo
"""
import os
import logging
import httpx
import unicodedata
from datetime import datetime, timezone
from typing import Dict, Optional, List
from enum import Enum


def normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas"""
    # Normaliza unicode (NFD decompõe acentos)
    normalized = unicodedata.normalize('NFD', text)
    # Remove caracteres de acento (categoria 'Mn' = Mark, Nonspacing)
    without_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
    return without_accents.lower().strip()

from app.db.client import supabase

logger = logging.getLogger(__name__)

# Configurações WhatsApp
WHATSAPP_API_URL = "https://graph.facebook.com/v18.0"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_API_TOKEN")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")


class OnboardingState(str, Enum):
    """Estados do fluxo de onboarding"""
    NEW_LEAD = "new_lead"                    # Primeiro contato
    SELECTING_INTERESTS = "selecting_interests"  # Escolhendo interesses
    SELECTING_PROFILE = "selecting_profile"  # Micro-profiling (curioso/profissional/investidor)
    SELECTING_TONE = "selecting_tone"        # Escolhendo tom
    DEMO_SENT = "demo_sent"                  # Resumo demo enviado
    AWAITING_PAYMENT = "awaiting_payment"    # Aguardando pagamento
    ACTIVE = "active"                        # Assinante ativo
    CONFIGURING = "configuring"              # Alterando configurações
    CONFIG_SCHEDULE = "config_schedule"      # Alterando horários
    CONFIG_INTERESTS = "config_interests"    # Alterando tópicos


# Mapeamento de interesses
INTERESTS_MAP = {
    "tech": {"id": "TECH", "label": "Tecnologia", "emoji": "💻"},
    "finance": {"id": "FINANCE", "label": "Mercado Financeiro", "emoji": "📈"},
    "crypto": {"id": "CRYPTO", "label": "Criptomoedas", "emoji": "₿"},
    "politics": {"id": "POLITICS", "label": "Política", "emoji": "🏛️"},
    "sports": {"id": "SPORTS", "label": "Esportes", "emoji": "⚽"},
    "health": {"id": "HEALTH", "label": "Saúde", "emoji": "🏥"},
    "entertainment": {"id": "ENTERTAINMENT", "label": "Entretenimento", "emoji": "🎬"},
    "business": {"id": "BUSINESS", "label": "Negócios", "emoji": "💼"},
    "world": {"id": "WORLD", "label": "Mundo", "emoji": "🌍"},
    "lifestyle": {"id": "LIFESTYLE", "label": "Lifestyle", "emoji": "🍷"},
}

# Horários disponíveis para escolha
AVAILABLE_TIMES = [
    "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00",
    "13:00", "14:00", "15:00", "16:00", "17:00", "18:00", "19:00",
    "20:00", "21:00", "22:00"
]

# Mapeamento de tons
TONES_MAP = {
    "formal": {"id": "formal", "label": "Sério e Profissional", "emoji": "📰"},
    "casual": {"id": "casual", "label": "Descontraído e Leve", "emoji": "😊"},
}

# Mapeamento de perfis (Micro-Profiling)
PROFILES_MAP = {
    "curioso": {
        "id": "curioso", 
        "label": "Curioso", 
        "emoji": "🧐",
        "description": "Explico termos técnicos de forma simples"
    },
    "profissional": {
        "id": "profissional", 
        "label": "Trabalho na área", 
        "emoji": "👨‍💻",
        "description": "Vou direto ao ponto, sem enrolação"
    },
    "investidor": {
        "id": "investidor", 
        "label": "Sou Investidor", 
        "emoji": "💰",
        "description": "Foco em impactos de mercado e oportunidades"
    },
}


class WhatsAppOnboarding:
    """Gerencia o fluxo de onboarding via WhatsApp"""
    
    def __init__(self):
        self.api_url = f"{WHATSAPP_API_URL}/{WHATSAPP_PHONE_ID}/messages"
        self.headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
    
    async def process_message(self, phone_number: str, message: str, message_type: str = "text") -> None:
        """
        Processa mensagem recebida e responde de acordo com o estado do lead
        """
        logger.info(f"Processando mensagem de {phone_number}: {message} (tipo: {message_type})")
        
        # Palavras-chave que indicam início ou reinício do fluxo
        message_lower = message.lower().strip()
        start_keywords = [
            "olá", "ola", "oi", "tindim", "start", "início", "inicio", 
            "começar", "comecar", "teste", "quero testar", "menu"
        ]
        
        # Comandos de debug/teste
        if message_lower in ["reset", "reiniciar", "debug_reset"]:
            logger.info(f"Comando de reset recebido de {phone_number}")
            await self._update_lead_state(
                phone_number, 
                OnboardingState.NEW_LEAD,
                {"is_active": False, "onboarding_data": {}, "plan": "generalista"}
            )
            await self._send_text_message(phone_number, "🔄 Estado reiniciado para testes. Envie 'Olá' para começar.")
            return

        # Busca ou cria lead
        lead = await self._get_or_create_lead(phone_number)
        state = lead.get("onboarding_state", OnboardingState.NEW_LEAD)
        
        # === COMANDO DE CONFIGURAÇÕES (disponível para assinantes ativos) ===
        # Normaliza a mensagem (remove acentos) para comparação mais robusta
        message_normalized = normalize_text(message)
        
        config_keywords = [
            "configuracao", "configuracoes", "config", "ajustes", 
            "settings", "preferencias", "opcoes"
        ]
        
        # Verifica se a mensagem contém alguma keyword de configuração
        is_config_command = any(kw in message_normalized for kw in config_keywords)
        is_active = lead.get("is_active", False)
        
        logger.info(f"Config check: normalized='{message_normalized}', is_config={is_config_command}, is_active={is_active}")
        
        if is_config_command and is_active:
            logger.info(f"Abrindo configurações para {phone_number}")
            await self._handle_open_config(phone_number, lead)
            return

        # Verifica se é uma mensagem de início
        is_start_message = any(keyword in message_lower for keyword in start_keywords)
        
        # Se for mensagem de início, força o reinício do onboarding (se não for assinante ativo)
        if is_start_message and state != OnboardingState.ACTIVE:
            logger.info(f"Reiniciando onboarding para {phone_number} (Gatilho: {message})")
            await self._handle_new_lead(phone_number, lead)
            return

        logger.info(f"Lead {phone_number} está no estado: {state}")
        
        # Processa de acordo com o estado
        if state == OnboardingState.NEW_LEAD:
            await self._handle_new_lead(phone_number, lead)
        
        elif state == OnboardingState.SELECTING_INTERESTS:
            await self._handle_interest_selection(phone_number, lead, message)
        
        elif state == OnboardingState.SELECTING_PROFILE:
            await self._handle_profile_selection(phone_number, lead, message)
        
        elif state == OnboardingState.SELECTING_TONE:
            await self._handle_tone_selection(phone_number, lead, message)
        
        elif state == OnboardingState.DEMO_SENT:
            await self._handle_post_demo(phone_number, lead, message)
        
        elif state == OnboardingState.AWAITING_PAYMENT:
            await self._handle_awaiting_payment(phone_number, lead, message)
        
        elif state == OnboardingState.CONFIGURING:
            await self._handle_config_menu(phone_number, lead, message)
        
        elif state == OnboardingState.CONFIG_SCHEDULE:
            await self._handle_config_schedule(phone_number, lead, message)
        
        elif state == OnboardingState.CONFIG_INTERESTS:
            await self._handle_config_interests(phone_number, lead, message)
        
        elif state == OnboardingState.ACTIVE:
            # Usuário ativo - passa para o chat assistant normal
            from app.services.chat_assistant import ChatAssistantService
            assistant = ChatAssistantService()
            response = await assistant.process_user_message(phone_number, message)
            await self._send_text_message(phone_number, response)
    
    async def _get_or_create_lead(self, phone_number: str) -> Dict:
        """Busca ou cria um lead no banco"""
        # Busca subscriber existente
        response = supabase.table("subscribers")\
            .select("*")\
            .eq("phone_number", phone_number)\
            .execute()
        
        if response.data:
            return response.data[0]
        
        # Cria novo lead
        new_lead = {
            "phone_number": phone_number,
            "name": "Lead",
            "is_active": False,  # Só ativa após pagamento
            "interests": [],
            "onboarding_state": OnboardingState.NEW_LEAD,
            "onboarding_data": {},
            "plan": "generalista"
        }
        
        result = supabase.table("subscribers").insert(new_lead).execute()
        logger.info(f"Novo lead criado: {phone_number}")
        return result.data[0]
    
    async def _update_lead_state(self, phone_number: str, state: str, extra_data: Dict = None) -> None:
        """Atualiza o estado do lead"""
        update_data = {"onboarding_state": state}
        if extra_data:
            update_data.update(extra_data)
        
        supabase.table("subscribers")\
            .update(update_data)\
            .eq("phone_number", phone_number)\
            .execute()
        
        logger.info(f"Lead {phone_number} atualizado para estado: {state}")
    
    # ==================== HANDLERS DE ESTADO ====================
    
    async def _handle_new_lead(self, phone_number: str, lead: Dict) -> None:
        """Primeiro contato - envia boas-vindas e botões de interesses"""
        
        # Mensagem de boas-vindas - Tom witty e tagline
        welcome = (
            "👋 E aí! Sou o *Tindim* — seu amigo que lê 500 notícias por dia pra você não precisar 😅\n\n"
            "*O mundo cabe na sua conversa.* 🌍\n\n"
            "Vou te contar só o que importa, sem enrolação, todo dia no WhatsApp.\n\n"
            "Bora lá? *Sobre o que você quer ficar por dentro?*\n"
            "_(Escolhe até 3 temas)_"
        )
        
        await self._send_text_message(phone_number, welcome)
        
        # Envia lista de interesses (todos de uma vez)
        await self._send_interests_list(phone_number)
        
        # Atualiza estado
        await self._update_lead_state(
            phone_number, 
            OnboardingState.SELECTING_INTERESTS,
            {"onboarding_data": {"selected_interests": []}}
        )
    
    async def _handle_interest_selection(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa seleção de interesses"""
        onboarding_data = lead.get("onboarding_data", {})
        selected = onboarding_data.get("selected_interests", [])
        
        message_lower = message.lower().strip()
        
        # Verifica se é um interesse válido
        if message_lower in INTERESTS_MAP:
            interest = INTERESTS_MAP[message_lower]
            if interest["id"] not in selected:
                selected.append(interest["id"])
                
                if len(selected) < 3:
                    # Confirma e pergunta se quer mais
                    await self._send_text_message(
                        phone_number,
                        f"✅ *{interest['label']}* anotado! ({len(selected)}/3)"
                    )
                    
                    # Mostra botões rápidos: mais temas ou continuar
                    await self._send_continue_or_more_buttons(phone_number, len(selected))
                    
                    # Atualiza dados
                    onboarding_data["selected_interests"] = selected
                    await self._update_lead_state(
                        phone_number,
                        OnboardingState.SELECTING_INTERESTS,
                        {"onboarding_data": onboarding_data}
                    )
                else:
                    # 3 interesses selecionados - avança para micro-profiling
                    await self._advance_to_profile_selection(phone_number, selected)
            else:
                await self._send_text_message(phone_number, "Esse você já escolheu! 😄 Bora de outro?")
        
        elif message_lower in ["pronto", "ok", "continuar", "próximo", "proximo", "gerar", "resumo"]:
            if len(selected) >= 1:
                await self._advance_to_profile_selection(phone_number, selected)
            else:
                await self._send_text_message(
                    phone_number,
                    "Por favor, selecione pelo menos 1 tema para continuar."
                )
                await self._send_interests_list(phone_number)
        
        elif message_lower == "mais":
            # Mostra lista completa novamente
            await self._send_interests_list(phone_number, exclude=selected)
        
        else:
            await self._send_text_message(
                phone_number,
                "Opa, não peguei essa 😅 Escolhe da lista aí!"
            )
            await self._send_interests_list(phone_number, exclude=selected)
    
    async def _advance_to_profile_selection(self, phone_number: str, interests: List[str]) -> None:
        """Avança para micro-profiling após seleção de interesses"""
        interests_labels = [
            f"{INTERESTS_MAP[k]['emoji']} {INTERESTS_MAP[k]['label']}"
            for k, v in INTERESTS_MAP.items() if v["id"] in interests
        ]
        
        # Determina qual pergunta de perfil fazer baseado nos interesses
        main_interest = interests[0] if interests else "TECH"
        
        if main_interest in ["TECH", "CRYPTO"]:
            profile_question = "Show, Tech! 👨‍💻 Me conta: você curte por curiosidade ou trampa na área?"
        elif main_interest in ["FINANCE"]:
            profile_question = "Boa, Mercado Financeiro! 📈 Você acompanha por curiosidade, trabalha com isso ou investe?"
        elif main_interest in ["POLITICS"]:
            profile_question = "Política, né? 🏛️ Curte acompanhar ou atua na área?"
        else:
            profile_question = "Massa! Me conta: você lê por curiosidade ou é da área?"
        
        await self._send_text_message(
            phone_number,
            f"Fechou! 🎯 Vou focar em:\n" + "\n".join(interests_labels) + "\n\n" + profile_question
        )
        
        await self._send_profile_buttons(phone_number)
        
        await self._update_lead_state(
            phone_number,
            OnboardingState.SELECTING_PROFILE,
            {
                "interests": interests,
                "onboarding_data": {"selected_interests": interests}
            }
        )
    
    async def _handle_profile_selection(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa seleção de perfil (micro-profiling)"""
        message_lower = message.lower().strip()
        
        profile = None
        if message_lower in ["curioso", "curiosidade", "interesse"]:
            profile = "curioso"
        elif message_lower in ["profissional", "trabalho", "area", "área"]:
            profile = "profissional"
        elif message_lower in ["investidor", "invisto", "investimento"]:
            profile = "investidor"
        
        if profile:
            profile_info = PROFILES_MAP[profile]
            
            await self._send_text_message(
                phone_number,
                f"{profile_info['emoji']} Saquei! *{profile_info['description']}*.\n\n"
                "Última pergunta: *prefere papo mais sério ou descontraído?*"
            )
            
            await self._send_tone_buttons(phone_number)
            
            # Salva perfil e avança para tom
            onboarding_data = lead.get("onboarding_data", {})
            onboarding_data["profile"] = profile
            
            await self._update_lead_state(
                phone_number,
                OnboardingState.SELECTING_TONE,
                {"onboarding_data": onboarding_data}
            )
        else:
            await self._send_text_message(
                phone_number,
                "Hmm, não entendi 🤔 Clica numa das opções aí!"
            )
            await self._send_profile_buttons(phone_number)
    
    async def _handle_tone_selection(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa seleção de tom e envia resumo demo"""
        message_lower = message.lower().strip()
        
        tone = None
        if message_lower in ["formal", "sério", "serio", "profissional"]:
            tone = "formal"
        elif message_lower in ["casual", "descontraído", "descontraido", "leve"]:
            tone = "casual"
        
        if tone:
            # Salva tom e gera resumo demo - Tom witty
            await self._send_text_message(
                phone_number,
                f"{'📰' if tone == 'formal' else '😊'} Perfeito! Tom *{TONES_MAP[tone]['label']}*.\n\n"
                "Deixa eu preparar um resumo especial pra você... ☕"
            )
            
            # Gera e envia resumo demo
            interests = lead.get("interests", ["TECH", "FINANCE"])
            await self._send_demo_digest(phone_number, interests, tone, lead)
            
            # Atualiza estado
            onboarding_data = lead.get("onboarding_data", {})
            onboarding_data["tone"] = tone
            await self._update_lead_state(
                phone_number,
                OnboardingState.DEMO_SENT,
                {"onboarding_data": onboarding_data}
            )
        else:
            await self._send_text_message(
                phone_number,
                "Opa, não peguei 😅 Clica numa das opções!"
            )
            await self._send_tone_buttons(phone_number)
    
    async def _send_demo_digest(self, phone_number: str, interests: List[str], tone: str, lead: Dict = None) -> None:
        """Gera e envia um resumo demo das últimas 12h com efeito Magic Box"""
        import asyncio
        
        # === EFEITO MAGIC BOX ===
        # Mensagens de status que mostram o trabalho da IA
        await self._send_text_message(
            phone_number,
            "🔍 *Lendo mais de 500 artigos sobre seus temas...*"
        )
        await asyncio.sleep(1.5)
        
        await self._send_text_message(
            phone_number,
            "🧹 *Filtrando clickbaits e fake news...*"
        )
        await asyncio.sleep(1.5)
        
        await self._send_text_message(
            phone_number,
            "✍️ *Resumindo o que importa para você...*"
        )
        await asyncio.sleep(1)
        
        # Busca artigos recentes (últimas 48h para garantir conteúdo)
        from datetime import timedelta
        time_threshold = datetime.now(timezone.utc) - timedelta(hours=48)
        
        articles_response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", time_threshold.isoformat())\
            .order("processed_at", desc=True)\
            .limit(15)\
            .execute()
        
        # Fallback: se não houver artigos recentes, pega os mais recentes disponíveis
        if not articles_response.data:
            logger.info("Nenhum artigo nas últimas 48h, buscando mais recentes...")
            articles_response = supabase.table("articles")\
                .select("*")\
                .not_.is_("summary_json", "null")\
                .order("processed_at", desc=True)\
                .limit(10)\
                .execute()
        
        # Obtém perfil do usuário para personalizar
        profile = "curioso"
        if lead:
            onboarding_data = lead.get("onboarding_data", {})
            profile = onboarding_data.get("profile", "curioso")
        
        sources_used = set()
        
        if articles_response.data:
            # Agrupa por categoria
            summaries_by_topic = {}
            for article in articles_response.data:
                category = article.get("category", "GENERAL")
                if category in interests or len(interests) == 0:
                    if category not in summaries_by_topic:
                        summaries_by_topic[category] = []
                    
                    summary = article.get("summary_json", {})
                    source = article.get("source", "")
                    if source:
                        sources_used.add(source)
                    
                    if summary:
                        summaries_by_topic[category].append({
                            "title": article.get("title", ""),
                            "summary": summary.get("summary", ""),
                            "key_points": summary.get("key_points", []),
                            "source": source,
                            "url": article.get("url", "")
                        })
            
            # Formata mensagem
            if summaries_by_topic:
                demo_message = "📰 *SEU RESUMO PERSONALIZADO*\n"
                demo_message += "_Notícias mais recentes_\n\n"
                
                for topic, articles in summaries_by_topic.items():
                    topic_info = next((v for v in INTERESTS_MAP.values() if v["id"] == topic), None)
                    emoji = topic_info["emoji"] if topic_info else "📌"
                    label = topic_info["label"] if topic_info else topic
                    
                    demo_message += f"{emoji} *{label.upper()}*\n"
                    
                    for i, art in enumerate(articles[:2], 1):  # Max 2 por tópico no demo
                        demo_message += f"• {art['title']}\n"
                        if art.get('summary'):
                            # Adapta resumo baseado no perfil
                            summary_text = art['summary']
                            if profile == "curioso":
                                # Versão mais explicativa
                                short_summary = summary_text[:180] + "..." if len(summary_text) > 180 else summary_text
                            elif profile == "investidor":
                                # Foco em impacto de mercado
                                short_summary = summary_text[:150] + "..." if len(summary_text) > 150 else summary_text
                            else:
                                # Profissional - direto ao ponto
                                short_summary = summary_text[:120] + "..." if len(summary_text) > 120 else summary_text
                            
                            demo_message += f"  _{short_summary}_\n"
                    
                    demo_message += "\n"
                
                # === FONTE TRANSPARENTE (Credibilidade) ===
                if sources_used:
                    sources_list = ", ".join(list(sources_used)[:5])
                    demo_message += f"_📚 Fontes: {sources_list}_\n"
                
                await self._send_text_message(phone_number, demo_message)
                
                # === DEEP DIVE - Botão para aprofundar ===
                await self._send_deep_dive_button(phone_number)
                
                # === DEMO DE ÁUDIO (desabilitado temporariamente - ElevenLabs bloqueado) ===
                # await self._send_audio_demo(phone_number, summaries_by_topic)
                
            else:
                await self._send_text_message(
                    phone_number,
                    "📰 *Ainda não tenho notícias recentes sobre seus temas.*\n\n"
                    "Mas não se preocupe! Assim que você assinar, vou monitorar as fontes "
                    "e te enviar tudo fresquinho todo dia às 07:00 e 19:00."
                )
        else:
            await self._send_text_message(
                phone_number,
                "📰 *Estou coletando as notícias mais recentes...*\n\n"
                "Assim que você assinar, vou te enviar resumos personalizados "
                "todo dia às 07:00 e 19:00!"
            )
        
        # Envia oferta com copy melhorada
        await self._send_subscription_offer(phone_number, lead)
    
    async def _send_subscription_offer(self, phone_number: str, lead: Dict = None) -> None:
        """Envia oferta de assinatura com copy otimizada (FOMO + Redução de Risco)"""
        
        import asyncio
        
        # === CONFIRMAÇÃO POSITIVA (Gamification) ===
        await self._send_text_message(
            phone_number,
            "E aí, mandei bem? 🎯"
        )
        
        await asyncio.sleep(2)
        
        # === FOMO - Fear of Missing Out ===
        offer_message = (
            "✨ *Curtiu o resumo?*\n\n"
            "Imagina receber isso *todo dia às 07:00* pra começar o dia ligado, "
            "e às *19:00* pra fechar atualizado.\n\n"
            "⏱️ *Você acabou de economizar uns 40 minutos* que gastaria lendo dezenas de sites.\n\n"
            "💰 *Planos:*\n"
            "• *Generalista* - R$ 9,90/mês\n"
            "  _Resumos diários + Papo com IA_\n\n"
            "• *Estrategista* - R$ 29,90/mês\n"
            "  _Tudo do Generalista + Áudios narrados + Análises profundas_\n\n"
        )
        
        # === REDUÇÃO DE RISCO ===
        offer_message += (
            "🎁 *Teste GRÁTIS por 5 dias!*\n"
            "_Te aviso um dia antes de cobrar. Sem surpresas._ 🤝"
        )
        
        await self._send_text_message(phone_number, offer_message)
        
        # === CELEBRAÇÃO ===
        await self._send_text_message(
            phone_number,
            "🎩 Bora entrar pro clube dos bem informados?"
        )
        
        # Envia botões de plano com copy melhorada
        await self._send_plan_buttons(phone_number)
    
    async def _handle_post_demo(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa resposta após demo - escolha de plano ou deep dive"""
        message_lower = message.lower().strip()
        
        # === DEEP DIVE - Aprofundamento ===
        if message_lower in ["deep_dive", "explique", "mais detalhes", "aprofundar"]:
            await self._send_deep_dive_response(phone_number, lead)
        
        # === ADOREI - Confirmação positiva ===
        elif message_lower in ["adorei", "gostei", "legal", "top", "show", "massa", "demais"]:
            await self._send_text_message(
                phone_number,
                "🎉 Que bom que curtiu!\n\n"
                "Sabia que no plano *Estrategista* eu também *leio as notícias pra você*? "
                "Perfeito pra ouvir no carro ou na academia! 🎧"
            )
            await self._send_plan_buttons(phone_number)
        
        elif message_lower in ["generalista", "plano 1", "9,90", "básico", "basico"]:
            await self._send_payment_link(phone_number, "generalista")
        
        elif message_lower in ["estrategista", "plano 2", "29,90", "premium", "completo"]:
            await self._send_payment_link(phone_number, "estrategista")
        
        elif message_lower in ["não", "nao", "depois", "cancelar"]:
            await self._send_text_message(
                phone_number,
                "Tranquilo! 😊\n\n"
                "Quando quiser voltar, é só mandar um 'oi'.\n"
                "Falou! 👋"
            )
        
        else:
            await self._send_text_message(
                phone_number,
                "Qual plano te interessa? Clica aí 👇"
            )
            await self._send_plan_buttons(phone_number)
    
    async def _send_audio_demo(self, phone_number: str, summaries_by_topic: Dict) -> None:
        """Envia um áudio demo curto para demonstrar o plano Estrategista"""
        import asyncio
        
        try:
            # Pega a primeira manchete disponível
            headline = None
            for topic, articles in summaries_by_topic.items():
                if articles:
                    headline = articles[0].get("title", "")
                    break
            
            if not headline:
                return
            
            # Mensagem de introdução
            await self._send_text_message(
                phone_number,
                "🎧 *Sabia que eu também falo?*\n\n"
                "No plano Estrategista, eu leio as notícias para você. "
                "Perfeito para ouvir no carro ou na academia!\n\n"
                "Ouça um exemplo 👇"
            )
            
            await asyncio.sleep(1)
            
            # Tenta gerar e enviar áudio demo
            from app.services.audio_generator import AudioGeneratorService
            audio_service = AudioGeneratorService()
            
            audio_url = await audio_service.generate_demo_audio(headline)
            
            if audio_url:
                await self._send_audio_message(phone_number, audio_url)
            else:
                # Fallback: mensagem de texto simulando o áudio
                await self._send_text_message(
                    phone_number,
                    f"🔊 _\"Bom dia! Aqui é o Tindim, sua IA jornalista. "
                    f"A manchete do momento: {headline[:100]}...\"_\n\n"
                    "_(Áudio demo indisponível no momento)_"
                )
                
        except Exception as e:
            logger.warning(f"Erro ao enviar áudio demo: {e}")
            # Não interrompe o fluxo se o áudio falhar
    
    async def _send_audio_message(self, phone_number: str, audio_url: str) -> bool:
        """Envia mensagem de áudio via WhatsApp"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "audio",
            "audio": {"link": audio_url}
        }
        
        return await self._send_message(payload)
    
    async def _send_deep_dive_response(self, phone_number: str, lead: Dict) -> None:
        """Envia uma explicação mais profunda sobre a última notícia"""
        from datetime import timedelta
        
        # Busca último artigo enviado
        interests = lead.get("interests", ["TECH", "FINANCE"])
        twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
        
        articles_response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", twelve_hours_ago.isoformat())\
            .in_("category", interests)\
            .order("processed_at", desc=True)\
            .limit(1)\
            .execute()
        
        if articles_response.data:
            article = articles_response.data[0]
            summary = article.get("summary_json", {})
            
            deep_dive_text = f"🔍 *Aprofundando: {article.get('title', 'Notícia')}*\n\n"
            
            # Adiciona pontos-chave
            key_points = summary.get("key_points", [])
            if key_points:
                deep_dive_text += "*Pontos importantes:*\n"
                for point in key_points[:4]:
                    deep_dive_text += f"• {point}\n"
                deep_dive_text += "\n"
            
            # Adiciona contexto/análise
            analysis = summary.get("analysis", summary.get("summary", ""))
            if analysis:
                deep_dive_text += f"*Contexto:*\n_{analysis}_\n\n"
            
            # Adiciona fonte
            source = article.get("source", "")
            url = article.get("url", "")
            if source:
                deep_dive_text += f"📚 _Fonte: {source}_"
                if url:
                    deep_dive_text += f"\n🔗 {url}"
            
            await self._send_text_message(phone_number, deep_dive_text)
        else:
            await self._send_text_message(
                phone_number,
                "🔍 No momento não tenho mais detalhes sobre essa notícia.\n\n"
                "Mas quando você assinar, poderá me perguntar qualquer coisa sobre as notícias do dia!"
            )
        
        # Volta para oferta
        await self._send_text_message(
            phone_number,
            "Gostou dessa análise mais profunda? 📊\n\n"
            "No plano *Estrategista* você tem acesso a análises como essa todos os dias!"
        )
        await self._send_plan_buttons(phone_number)
    
    async def _send_payment_link(self, phone_number: str, plan: str) -> None:
        """Gera e envia link de pagamento do Stripe"""
        import stripe
        
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        
        if not stripe.api_key:
            await self._send_text_message(
                phone_number,
                "⚠️ Xiii, deu um probleminha no pagamento. "
                "Tenta de novo daqui a pouquinho?"
            )
            return
        
        try:
            # Busca ou cria Price ID
            price_id = os.getenv(f"STRIPE_PRICE_{plan.upper()}")
            
            if not price_id or not price_id.startswith("price_"):
                # Cria Payment Link genérico
                logger.warning(f"Price ID não configurado para {plan}, usando fallback")
                await self._send_text_message(
                    phone_number,
                    f"💳 Para assinar o plano *{plan.title()}*, acesse:\n\n"
                    f"https://tindim.onrender.com/onboarding\n\n"
                    "Ou entre em contato conosco para finalizar sua assinatura!"
                )
                return
            
            # Cria Checkout Session
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{
                    "price": price_id,
                    "quantity": 1
                }],
                mode="subscription",
                success_url=f"https://tindim.onrender.com/?checkout=success&phone={phone_number}",
                cancel_url=f"https://tindim.onrender.com/?checkout=canceled",
                subscription_data={
                    "trial_period_days": 5,
                    "metadata": {
                        "phone_number": phone_number,
                        "plan": plan
                    }
                },
                metadata={
                    "phone_number": phone_number,
                    "plan": plan
                }
            )
            
            await self._send_text_message(
                phone_number,
                f"🔒 *Link seguro de pagamento:*\n\n"
                f"{session.url}\n\n"
                f"_Plano {plan.title()} - 5 dias grátis!_\n"
                "_Você pode cancelar a qualquer momento._"
            )
            
            await self._update_lead_state(
                phone_number,
                OnboardingState.AWAITING_PAYMENT,
                {"plan": plan}
            )
            
        except Exception as e:
            logger.error(f"Erro ao criar checkout: {e}")
            await self._send_text_message(
                phone_number,
                "⚠️ Opa, deu ruim aqui. "
                "Tenta de novo ou acessa nosso site direto!"
            )
    
    async def _handle_awaiting_payment(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa mensagens enquanto aguarda pagamento"""
        message_lower = message.lower().strip()
        
        if message_lower in ["paguei", "pago", "pronto", "feito", "já paguei"]:
            # Verifica status do pagamento
            if lead.get("is_active"):
                await self._send_text_message(
                    phone_number,
                    "✅ *Show, pagamento confirmado!*\n\n"
                    "Sua assinatura tá ativa. Seu primeiro resumo chega amanhã às 07:00!\n\n"
                    "Enquanto isso, pode me perguntar qualquer coisa. 😊"
                )
                await self._update_lead_state(phone_number, OnboardingState.ACTIVE)
            else:
                await self._send_text_message(
                    phone_number,
                    "⏳ Hmm, ainda não chegou a confirmação aqui...\n\n"
                    "Se já pagou, espera uns segundinhos e tenta de novo.\n"
                    "Qualquer coisa, me chama!"
                )
        
        elif message_lower in ["trocar", "mudar plano", "outro plano"]:
            await self._send_plan_buttons(phone_number)
        
        else:
            await self._send_text_message(
                phone_number,
                "Tô aqui esperando a confirmação do pagamento. 😊\n\n"
                "Quer um novo link? É só pedir!"
            )
    
    async def confirm_payment(self, phone_number: str, plan: str) -> None:
        """Chamado pelo webhook do Stripe quando pagamento é confirmado"""
        import asyncio
        
        # === CELEBRAÇÃO DE BOAS-VINDAS ===
        await self._send_text_message(
            phone_number,
            "🎉 *Fechou!* Pagamento confirmado!"
        )
        
        await asyncio.sleep(1)
        
        # Mensagem personalizada por plano - Tom witty
        if plan == "estrategista":
            await self._send_text_message(
                phone_number,
                f"🎩 *Bem-vindo ao clube VIP, Estrategista!*\n\n"
                "Você desbloqueou:\n"
                "✅ Resumos diários sob medida\n"
                "✅ Áudios narrados pra ouvir onde quiser\n"
                "✅ Análises profundas quando pedir\n"
                "✅ Papo ilimitado comigo\n\n"
                "📅 *Seus resumos chegam:*\n"
                "• *07:00* - Pra começar o dia ligado ☕\n"
                "• *19:00* - Pra fechar atualizado 🌙\n\n"
                "💬 Me chama qualquer hora pra trocar ideia sobre as notícias!"
            )
        else:
            await self._send_text_message(
                phone_number,
                f"🎩 *Bem-vindo ao Tindim!*\n\n"
                "Você desbloqueou:\n"
                "✅ Resumos diários sob medida\n"
                "✅ Papo comigo sobre as notícias\n\n"
                "📅 *Seus resumos chegam:*\n"
                "• *07:00* - Pra começar o dia ligado ☕\n"
                "• *19:00* - Pra fechar atualizado 🌙\n\n"
                "💬 Me chama quando quiser!"
            )
        
        await asyncio.sleep(1)
        
        await self._send_text_message(
            phone_number,
            "🎁 *Surpresa!* Já que é sua estreia, bora de resumo agora!\n\n"
            "_Só um segundo..._"
        )
        
        await self._update_lead_state(
            phone_number,
            OnboardingState.ACTIVE,
            {"is_active": True, "plan": plan}
        )
        
        # === ENVIO IMEDIATO DO PRIMEIRO RESUMO (para testes e wow moment) ===
        await asyncio.sleep(2)
        
        try:
            from app.services.whatsapp import WhatsAppService
            wa_service = WhatsAppService()
            await wa_service.send_immediate_digest(phone_number)
        except Exception as e:
            logger.error(f"Erro ao enviar resumo imediato: {e}")
            await self._send_text_message(
                phone_number,
                "📰 Seu primeiro resumo chegará em breve!\n\n"
                "_Dica: você pode alterar preferências digitando 'configurações'._"
            )
    
    # ==================== CONFIGURAÇÕES ====================
    
    async def _handle_open_config(self, phone_number: str, lead: Dict) -> None:
        """Abre o menu de configurações para assinantes ativos"""
        plan = lead.get("plan", "generalista")
        interests = lead.get("interests", [])
        preferred_times = lead.get("preferred_times", ["07:00", "19:00"])
        
        # Formata interesses atuais
        interests_text = ", ".join([
            f"{INTERESTS_MAP.get(i.lower(), {}).get('emoji', '📌')} {i}"
            for i in interests
        ]) if interests else "Nenhum selecionado"
        
        # Formata horários atuais
        if plan == "estrategista":
            times_text = f"*{preferred_times[0]}* e *{preferred_times[1]}*" if len(preferred_times) >= 2 else f"*{preferred_times[0]}*"
        else:
            times_text = f"*{preferred_times[0]}*" if preferred_times else "*07:00*"
        
        config_msg = (
            "⚙️ *Configurações do Tindim*\n\n"
            f"📋 *Plano:* {plan.title()}\n"
            f"📰 *Tópicos:* {interests_text}\n"
            f"⏰ *Horários:* {times_text}\n\n"
            "O que você quer alterar?"
        )
        
        await self._send_text_message(phone_number, config_msg)
        await self._send_config_menu_buttons(phone_number)
        
        await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
    
    async def _handle_config_menu(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa seleção no menu de configurações"""
        message_lower = message.lower().strip()
        
        if message_lower in ["horario", "horário", "horarios", "horários", "schedule"]:
            await self._start_schedule_config(phone_number, lead)
        
        elif message_lower in ["topicos", "tópicos", "temas", "interesses", "interests"]:
            await self._start_interests_config(phone_number, lead)
        
        elif message_lower in ["voltar", "sair", "cancelar", "pronto"]:
            await self._send_text_message(
                phone_number,
                "✅ Configurações salvas! Qualquer coisa, é só digitar *configurações*. 😊"
            )
            await self._update_lead_state(phone_number, OnboardingState.ACTIVE)
        
        else:
            await self._send_text_message(
                phone_number,
                "Não entendi 🤔 Clica numa das opções aí!"
            )
            await self._send_config_menu_buttons(phone_number)
    
    async def _start_schedule_config(self, phone_number: str, lead: Dict) -> None:
        """Inicia configuração de horários"""
        plan = lead.get("plan", "generalista")
        preferred_times = lead.get("preferred_times", ["07:00", "19:00"])
        
        if plan == "estrategista":
            msg = (
                "⏰ *Configurar Horários*\n\n"
                f"Horários atuais: *{preferred_times[0]}* e *{preferred_times[1]}*\n\n"
                "Como Estrategista, você recebe *2 resumos por dia*.\n\n"
                "Primeiro, escolha o *horário da manhã*:"
            )
        else:
            msg = (
                "⏰ *Configurar Horário*\n\n"
                f"Horário atual: *{preferred_times[0]}*\n\n"
                "Como Generalista, você recebe *1 resumo por dia*.\n\n"
                "Escolha seu horário preferido:"
            )
        
        await self._send_text_message(phone_number, msg)
        await self._send_time_buttons(phone_number, period="morning")
        
        # Salva que estamos configurando o primeiro horário
        onboarding_data = lead.get("onboarding_data", {})
        onboarding_data["config_step"] = "time_1"
        
        await self._update_lead_state(
            phone_number, 
            OnboardingState.CONFIG_SCHEDULE,
            {"onboarding_data": onboarding_data}
        )
    
    async def _handle_config_schedule(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa configuração de horários"""
        message_lower = message.lower().strip()
        onboarding_data = lead.get("onboarding_data", {})
        config_step = onboarding_data.get("config_step", "time_1")
        plan = lead.get("plan", "generalista")
        
        # Verifica se é um horário válido
        if message_lower in AVAILABLE_TIMES or message_lower.replace(":", "") in [t.replace(":", "") for t in AVAILABLE_TIMES]:
            # Normaliza o horário
            time_value = message_lower if ":" in message_lower else f"{message_lower[:2]}:{message_lower[2:]}"
            
            if config_step == "time_1":
                # Salvando primeiro horário
                onboarding_data["new_time_1"] = time_value
                
                if plan == "estrategista":
                    # Estrategista: pedir segundo horário
                    onboarding_data["config_step"] = "time_2"
                    await self._send_text_message(
                        phone_number,
                        f"✅ Primeiro horário: *{time_value}*\n\n"
                        "Agora escolha o *horário da tarde/noite*:"
                    )
                    await self._send_time_buttons(phone_number, period="evening")
                    await self._update_lead_state(
                        phone_number,
                        OnboardingState.CONFIG_SCHEDULE,
                        {"onboarding_data": onboarding_data}
                    )
                else:
                    # Generalista: salvar e finalizar
                    new_times = [time_value, "19:00"]  # Mantém segundo horário como fallback
                    await self._save_schedule(phone_number, new_times)
                    await self._send_text_message(
                        phone_number,
                        f"✅ Pronto! Seu resumo agora chega às *{time_value}*.\n\n"
                        "Quer alterar mais alguma coisa?"
                    )
                    await self._send_config_menu_buttons(phone_number)
                    await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
            
            elif config_step == "time_2":
                # Salvando segundo horário (só Estrategista)
                time_1 = onboarding_data.get("new_time_1", "07:00")
                new_times = [time_1, time_value]
                
                await self._save_schedule(phone_number, new_times)
                await self._send_text_message(
                    phone_number,
                    f"✅ Perfeito! Seus resumos agora chegam às *{time_1}* e *{time_value}*.\n\n"
                    "Quer alterar mais alguma coisa?"
                )
                await self._send_config_menu_buttons(phone_number)
                await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
        
        elif message_lower in ["voltar", "cancelar"]:
            await self._send_text_message(phone_number, "Ok, voltando ao menu...")
            await self._send_config_menu_buttons(phone_number)
            await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
        
        else:
            await self._send_text_message(
                phone_number,
                "Hmm, não reconheci esse horário 🤔\n"
                "Escolhe um dos botões ou digita no formato *HH:MM* (ex: 08:00)"
            )
            period = "morning" if config_step == "time_1" else "evening"
            await self._send_time_buttons(phone_number, period=period)
    
    async def _save_schedule(self, phone_number: str, times: List[str]) -> None:
        """Salva os horários preferidos no Supabase"""
        supabase.table("subscribers")\
            .update({"preferred_times": times})\
            .eq("phone_number", phone_number)\
            .execute()
        logger.info(f"Horários atualizados para {phone_number}: {times}")
    
    async def _start_interests_config(self, phone_number: str, lead: Dict) -> None:
        """Inicia configuração de tópicos"""
        interests = lead.get("interests", [])
        
        interests_text = "\n".join([
            f"  {INTERESTS_MAP.get(i.lower(), {}).get('emoji', '📌')} {i}"
            for i in interests
        ]) if interests else "  Nenhum selecionado"
        
        msg = (
            "📰 *Configurar Tópicos*\n\n"
            f"Seus tópicos atuais:\n{interests_text}\n\n"
            "Você pode ter até *3 tópicos*.\n\n"
            "Escolha uma opção:"
        )
        
        await self._send_text_message(phone_number, msg)
        await self._send_interests_config_buttons(phone_number)
        
        # Salva interesses atuais para edição
        onboarding_data = lead.get("onboarding_data", {})
        onboarding_data["editing_interests"] = interests.copy() if interests else []
        
        await self._update_lead_state(
            phone_number,
            OnboardingState.CONFIG_INTERESTS,
            {"onboarding_data": onboarding_data}
        )
    
    async def _handle_config_interests(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa configuração de tópicos"""
        message_lower = message.lower().strip()
        onboarding_data = lead.get("onboarding_data", {})
        editing_interests = onboarding_data.get("editing_interests", [])
        
        # Adicionar novo tópico
        if message_lower in INTERESTS_MAP:
            interest_id = INTERESTS_MAP[message_lower]["id"]
            interest_label = INTERESTS_MAP[message_lower]["label"]
            
            if interest_id in editing_interests:
                # Remover se já existe
                editing_interests.remove(interest_id)
                await self._send_text_message(
                    phone_number,
                    f"❌ *{interest_label}* removido!\n\n"
                    f"Tópicos atuais: {len(editing_interests)}/3"
                )
            elif len(editing_interests) >= 3:
                await self._send_text_message(
                    phone_number,
                    "⚠️ Você já tem 3 tópicos! Remove um antes de adicionar outro."
                )
            else:
                editing_interests.append(interest_id)
                await self._send_text_message(
                    phone_number,
                    f"✅ *{interest_label}* adicionado!\n\n"
                    f"Tópicos atuais: {len(editing_interests)}/3"
                )
            
            onboarding_data["editing_interests"] = editing_interests
            await self._update_lead_state(
                phone_number,
                OnboardingState.CONFIG_INTERESTS,
                {"onboarding_data": onboarding_data}
            )
            await self._send_interests_config_buttons(phone_number, exclude=editing_interests)
        
        elif message_lower in ["limpar", "resetar", "zerar"]:
            onboarding_data["editing_interests"] = []
            await self._send_text_message(phone_number, "🗑️ Tópicos limpos! Escolha novos:")
            await self._update_lead_state(
                phone_number,
                OnboardingState.CONFIG_INTERESTS,
                {"onboarding_data": onboarding_data}
            )
            await self._send_interests_config_buttons(phone_number)
        
        elif message_lower in ["salvar", "pronto", "ok", "confirmar"]:
            if len(editing_interests) == 0:
                await self._send_text_message(
                    phone_number,
                    "⚠️ Selecione pelo menos 1 tópico antes de salvar!"
                )
                await self._send_interests_config_buttons(phone_number)
            else:
                await self._save_interests(phone_number, editing_interests)
                interests_text = ", ".join(editing_interests)
                await self._send_text_message(
                    phone_number,
                    f"✅ Tópicos salvos: *{interests_text}*\n\n"
                    "Quer alterar mais alguma coisa?"
                )
                await self._send_config_menu_buttons(phone_number)
                await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
        
        elif message_lower in ["voltar", "cancelar"]:
            await self._send_text_message(phone_number, "Ok, alterações descartadas. Voltando ao menu...")
            await self._send_config_menu_buttons(phone_number)
            await self._update_lead_state(phone_number, OnboardingState.CONFIGURING)
        
        else:
            await self._send_text_message(
                phone_number,
                "Não entendi 🤔 Clica num tópico pra adicionar/remover, ou em *Salvar* pra confirmar."
            )
            await self._send_interests_config_buttons(phone_number, exclude=editing_interests)
    
    async def _save_interests(self, phone_number: str, interests: List[str]) -> None:
        """Salva os interesses no Supabase"""
        supabase.table("subscribers")\
            .update({"interests": interests})\
            .eq("phone_number", phone_number)\
            .execute()
        logger.info(f"Interesses atualizados para {phone_number}: {interests}")
    
    # ==================== BOTÕES DE CONFIGURAÇÃO ====================
    
    async def _send_config_menu_buttons(self, phone_number: str) -> bool:
        """Envia botões do menu de configurações"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Escolha o que alterar:"},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "horario", "title": "⏰ Horários"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "topicos", "title": "📰 Tópicos"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "voltar", "title": "✅ Pronto"}
                        }
                    ]
                }
            }
        }
        return await self._send_message(payload)
    
    async def _send_time_buttons(self, phone_number: str, period: str = "morning") -> bool:
        """Envia botões de seleção de horário"""
        if period == "morning":
            times = ["06:00", "07:00", "08:00"]
        else:
            times = ["18:00", "19:00", "20:00"]
        
        buttons = [
            {
                "type": "reply",
                "reply": {"id": t, "title": f"🕐 {t}"}
            }
            for t in times
        ]
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": f"Horários populares ({period == 'morning' and 'manhã' or 'tarde/noite'}):\n\n_Ou digite outro horário (ex: 09:00)_"},
                "action": {"buttons": buttons}
            }
        }
        return await self._send_message(payload)
    
    async def _send_interests_config_buttons(self, phone_number: str, exclude: List[str] = None) -> bool:
        """Envia botões para configurar interesses"""
        exclude = exclude or []
        
        # Pega 2 interesses não selecionados
        available = [
            (k, v) for k, v in INTERESTS_MAP.items()
            if v["id"] not in exclude
        ][:2]
        
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": k,
                    "title": f"{v['emoji']} {v['label']}"[:20]
                }
            }
            for k, v in available
        ]
        
        # Adiciona botão de salvar
        buttons.append({
            "type": "reply",
            "reply": {"id": "salvar", "title": "💾 Salvar"}
        })
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Clique pra adicionar/remover tópicos:"},
                "action": {"buttons": buttons[:3]}
            }
        }
        return await self._send_message(payload)
    
    # ==================== ENVIO DE MENSAGENS ====================
    
    async def _send_text_message(self, phone_number: str, text: str) -> bool:
        """Envia mensagem de texto simples"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "text",
            "text": {"body": text}
        }
        
        return await self._send_message(payload)
    
    async def _send_interests_list(self, phone_number: str, exclude: List[str] = None) -> bool:
        """
        Envia List Message com todos os temas disponíveis.
        Permite seleção rápida sem múltiplas mensagens.
        """
        exclude = exclude or []
        
        # Agrupa interesses por categoria
        rows = []
        for key, value in INTERESTS_MAP.items():
            if value["id"] not in exclude:
                rows.append({
                    "id": key,
                    "title": f"{value['emoji']} {value['label']}"[:24],  # Limite de 24 chars
                    "description": self._get_interest_description(key)[:72]  # Limite de 72 chars
                })
        
        if not rows:
            await self._send_text_message(
                phone_number,
                "Você já selecionou todos os temas disponíveis! Digite *pronto* para continuar."
            )
            return True
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "header": {
                    "type": "text",
                    "text": "📰 Escolha seus temas"
                },
                "body": {
                    "text": "Toque no botão abaixo para ver todos os temas disponíveis e escolher os que te interessam."
                },
                "footer": {
                    "text": "Máximo 3 temas • Você pode mudar depois"
                },
                "action": {
                    "button": "Ver Temas",
                    "sections": [
                        {
                            "title": "Temas Disponíveis",
                            "rows": rows[:10]  # Limite de 10 itens por seção
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    def _get_interest_description(self, interest_key: str) -> str:
        """Retorna descrição curta para cada interesse"""
        descriptions = {
            "tech": "Startups, apps, gadgets e inovação",
            "finance": "Bolsa, investimentos e economia",
            "crypto": "Bitcoin, altcoins e blockchain",
            "politics": "Governo, eleições e políticas públicas",
            "sports": "Futebol, NBA, F1 e mais",
            "health": "Medicina, bem-estar e ciência",
            "entertainment": "Filmes, séries, música e cultura",
            "business": "Empresas, empreendedorismo e gestão",
            "world": "Notícias internacionais",
            "lifestyle": "Tendências, viagens e gastronomia"
        }
        return descriptions.get(interest_key, "Notícias e atualizações")
    
    async def _send_continue_or_more_buttons(self, phone_number: str, selected_count: int) -> bool:
        """Envia botões para continuar ou adicionar mais temas"""
        remaining = 3 - selected_count
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {
                    "text": f"Quer adicionar mais {remaining} tema{'s' if remaining > 1 else ''} ou tá bom assim?"
                },
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "mais", "title": f"➕ Mais temas"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "pronto", "title": "🚀 Tá ótimo!"}
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_interest_buttons(self, phone_number: str, page: int = 1, exclude: List[str] = None) -> bool:
        """Envia botões de seleção de interesses (fallback para List Message)"""
        exclude = exclude or []
        
        # Filtra interesses não selecionados
        available = [
            (k, v) for k, v in INTERESTS_MAP.items() 
            if v["id"] not in exclude
        ]
        
        # Pagina (3 botões por vez - limite do WhatsApp)
        start = (page - 1) * 3
        interests_page = available[start:start + 3]
        
        if not interests_page:
            # Sem mais opções
            await self._send_text_message(
                phone_number,
                "Você já viu todas as opções! Digite *pronto* para continuar."
            )
            return True
        
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": k,
                    "title": f"{v['emoji']} {v['label']}"[:20]  # Limite de 20 chars
                }
            }
            for k, v in interests_page
        ]
        
        # Adiciona botão "Mais" se houver mais opções
        if len(available) > start + 3:
            buttons.append({
                "type": "reply",
                "reply": {"id": "mais", "title": "➡️ Ver mais"}
            })
        
        # Adiciona botão "Pronto" se já selecionou algo
        if exclude:
            buttons.append({
                "type": "reply",
                "reply": {"id": "pronto", "title": "✅ Pronto"}
            })
        
        # Limita a 3 botões (limite do WhatsApp)
        buttons = buttons[:3]
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Escolha um tema:"},
                "action": {"buttons": buttons}
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_tone_buttons(self, phone_number: str) -> bool:
        """Envia botões de seleção de tom"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Qual tom você prefere?"},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "formal", "title": "📰 Sério"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "casual", "title": "😊 Descontraído"}
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_plan_buttons(self, phone_number: str) -> bool:
        """Envia botões de seleção de plano"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Escolha seu plano:"},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "generalista", "title": "💼 R$ 9,90/mês"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "estrategista", "title": "🚀 R$ 29,90/mês"}
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_profile_buttons(self, phone_number: str) -> bool:
        """Envia botões de seleção de perfil (micro-profiling)"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Qual é o seu perfil?"},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "curioso", "title": "🧐 Curioso"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "profissional", "title": "👨‍💻 Trabalho na área"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "investidor", "title": "💰 Sou Investidor"}
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_interest_buttons_with_generate(self, phone_number: str, exclude: List[str] = None) -> bool:
        """Envia botões de interesses com opção de gerar resumo"""
        exclude = exclude or []
        
        # Filtra interesses não selecionados
        available = [
            (k, v) for k, v in INTERESTS_MAP.items() 
            if v["id"] not in exclude
        ][:2]  # Máximo 2 temas + botão gerar
        
        buttons = [
            {
                "type": "reply",
                "reply": {
                    "id": k,
                    "title": f"{v['emoji']} {v['label']}"[:20]
                }
            }
            for k, v in available
        ]
        
        # Adiciona botão principal de gerar resumo
        buttons.append({
            "type": "reply",
            "reply": {"id": "gerar", "title": "🚀 Gerar Resumo!"}
        })
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Adicione mais temas ou gere seu resumo:"},
                "action": {"buttons": buttons[:3]}  # Limite de 3 botões
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_deep_dive_button(self, phone_number: str) -> bool:
        """Envia botão para aprofundar em uma notícia (Deep Dive)"""
        payload = {
            "messaging_product": "whatsapp",
            "to": phone_number,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Quer saber mais sobre alguma notícia?"},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": "deep_dive", "title": "🔍 Me explique melhor"}
                        },
                        {
                            "type": "reply",
                            "reply": {"id": "adorei", "title": "😍 Adorei!"}
                        }
                    ]
                }
            }
        }
        
        return await self._send_message(payload)
    
    async def _send_message(self, payload: Dict) -> bool:
        """Envia mensagem para a API do WhatsApp"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    headers=self.headers,
                    json=payload,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info(f"Mensagem enviada com sucesso")
                    return True
                else:
                    logger.error(f"Erro ao enviar mensagem: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem: {e}")
            return False


# Instância global
whatsapp_onboarding = WhatsAppOnboarding()
