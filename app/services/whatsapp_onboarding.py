"""
Serviço de Onboarding via WhatsApp
Fluxo conversacional: Lead -> Interesses -> Tom -> Resumo -> Pagamento -> Ativo
"""
import os
import logging
import httpx
from datetime import datetime, timezone
from typing import Dict, Optional, List
from enum import Enum

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
    SELECTING_TONE = "selecting_tone"        # Escolhendo tom
    DEMO_SENT = "demo_sent"                  # Resumo demo enviado
    AWAITING_PAYMENT = "awaiting_payment"    # Aguardando pagamento
    ACTIVE = "active"                        # Assinante ativo


# Mapeamento de interesses
INTERESTS_MAP = {
    "tech": {"id": "TECH", "label": "Tecnologia", "emoji": "💻"},
    "finance": {"id": "FINANCE", "label": "Mercado Financeiro", "emoji": "📈"},
    "politics": {"id": "POLITICS", "label": "Política", "emoji": "🏛️"},
    "sports": {"id": "SPORTS", "label": "Esportes", "emoji": "⚽"},
    "health": {"id": "HEALTH", "label": "Saúde", "emoji": "🏥"},
    "entertainment": {"id": "ENTERTAINMENT", "label": "Entretenimento", "emoji": "🎬"},
}

# Mapeamento de tons
TONES_MAP = {
    "formal": {"id": "formal", "label": "Sério e Profissional", "emoji": "📰"},
    "casual": {"id": "casual", "label": "Descontraído e Leve", "emoji": "😊"},
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

        # Verifica se é uma mensagem de início
        is_start_message = any(keyword in message_lower for keyword in start_keywords)
        
        # Busca ou cria lead
        lead = await self._get_or_create_lead(phone_number)
        state = lead.get("onboarding_state", OnboardingState.NEW_LEAD)
        
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
        
        elif state == OnboardingState.SELECTING_TONE:
            await self._handle_tone_selection(phone_number, lead, message)
        
        elif state == OnboardingState.DEMO_SENT:
            await self._handle_post_demo(phone_number, lead, message)
        
        elif state == OnboardingState.AWAITING_PAYMENT:
            await self._handle_awaiting_payment(phone_number, lead, message)
        
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
        
        # Mensagem de boas-vindas
        welcome = (
            "👋 *Olá! Sou o Tindim, sua IA Jornalista.*\n\n"
            "Vou te enviar resumos personalizados das notícias que importam para você, "
            "todo dia no WhatsApp.\n\n"
            "Para começar, *sobre o que você quer ler?*\n"
            "_(Selecione até 3 temas)_"
        )
        
        await self._send_text_message(phone_number, welcome)
        
        # Envia botões de interesses (em grupos de 3, limite do WhatsApp)
        await self._send_interest_buttons(phone_number, page=1)
        
        # Atualiza estado
        await self._update_lead_state(
            phone_number, 
            OnboardingState.SELECTING_INTERESTS,
            {"onboarding_data": {"selected_interests": [], "interests_page": 1}}
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
                    # Confirma e pede mais
                    await self._send_text_message(
                        phone_number,
                        f"✅ *{interest['label']}* adicionado!\n\n"
                        f"Você selecionou {len(selected)} de 3. Quer adicionar mais algum?"
                    )
                    await self._send_interest_buttons(phone_number, page=1, exclude=selected)
                    
                    # Atualiza dados
                    onboarding_data["selected_interests"] = selected
                    await self._update_lead_state(
                        phone_number,
                        OnboardingState.SELECTING_INTERESTS,
                        {"onboarding_data": onboarding_data}
                    )
                else:
                    # 3 interesses selecionados - avança para tom
                    await self._advance_to_tone_selection(phone_number, selected)
            else:
                await self._send_text_message(phone_number, "Você já selecionou esse tema. Escolha outro!")
        
        elif message_lower in ["pronto", "ok", "continuar", "próximo", "proximo"]:
            if len(selected) >= 1:
                await self._advance_to_tone_selection(phone_number, selected)
            else:
                await self._send_text_message(
                    phone_number,
                    "Por favor, selecione pelo menos 1 tema para continuar."
                )
        
        elif message_lower == "mais":
            # Mostra mais opções
            await self._send_interest_buttons(phone_number, page=2, exclude=selected)
        
        else:
            await self._send_text_message(
                phone_number,
                "Não entendi. Por favor, clique em um dos botões ou digite o nome do tema."
            )
            await self._send_interest_buttons(phone_number, page=1, exclude=selected)
    
    async def _advance_to_tone_selection(self, phone_number: str, interests: List[str]) -> None:
        """Avança para seleção de tom"""
        interests_labels = [
            f"{INTERESTS_MAP[k]['emoji']} {INTERESTS_MAP[k]['label']}"
            for k, v in INTERESTS_MAP.items() if v["id"] in interests
        ]
        
        await self._send_text_message(
            phone_number,
            f"Perfeito! Vou focar em:\n" + "\n".join(interests_labels) + "\n\n"
            "Agora me conta: *você prefere um tom mais sério ou descontraído?*"
        )
        
        await self._send_tone_buttons(phone_number)
        
        await self._update_lead_state(
            phone_number,
            OnboardingState.SELECTING_TONE,
            {
                "interests": interests,
                "onboarding_data": {"selected_interests": interests}
            }
        )
    
    async def _handle_tone_selection(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa seleção de tom e envia resumo demo"""
        message_lower = message.lower().strip()
        
        tone = None
        if message_lower in ["formal", "sério", "serio", "profissional"]:
            tone = "formal"
        elif message_lower in ["casual", "descontraído", "descontraido", "leve"]:
            tone = "casual"
        
        if tone:
            # Salva tom e gera resumo demo
            await self._send_text_message(
                phone_number,
                f"{'📰' if tone == 'formal' else '😊'} Entendido! Tom *{TONES_MAP[tone]['label']}*.\n\n"
                "⏳ Aguarde um momento, estou preparando um resumo especial das últimas 12 horas para você testar..."
            )
            
            # Gera e envia resumo demo
            interests = lead.get("interests", ["TECH", "FINANCE"])
            await self._send_demo_digest(phone_number, interests, tone)
            
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
                "Não entendi. Por favor, escolha uma das opções:"
            )
            await self._send_tone_buttons(phone_number)
    
    async def _send_demo_digest(self, phone_number: str, interests: List[str], tone: str) -> None:
        """Gera e envia um resumo demo das últimas 12h"""
        from app.services.ai_processor import AIProcessor
        
        # Busca artigos recentes
        from datetime import timedelta
        twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
        
        articles_response = supabase.table("articles")\
            .select("*")\
            .gte("processed_at", twelve_hours_ago.isoformat())\
            .order("processed_at", desc=True)\
            .limit(10)\
            .execute()
        
        if articles_response.data:
            # Gera resumo com IA
            processor = AIProcessor()
            
            # Agrupa por categoria
            summaries_by_topic = {}
            for article in articles_response.data:
                category = article.get("category", "GENERAL")
                if category in interests or len(interests) == 0:
                    if category not in summaries_by_topic:
                        summaries_by_topic[category] = []
                    
                    summary = article.get("summary_json", {})
                    if summary:
                        summaries_by_topic[category].append({
                            "title": article.get("title", ""),
                            "summary": summary.get("summary", ""),
                            "key_points": summary.get("key_points", [])
                        })
            
            # Formata mensagem
            if summaries_by_topic:
                demo_message = "📰 *SEU RESUMO PERSONALIZADO*\n"
                demo_message += "_Últimas 12 horas_\n\n"
                
                for topic, articles in summaries_by_topic.items():
                    topic_info = next((v for v in INTERESTS_MAP.values() if v["id"] == topic), None)
                    emoji = topic_info["emoji"] if topic_info else "📌"
                    label = topic_info["label"] if topic_info else topic
                    
                    demo_message += f"{emoji} *{label.upper()}*\n"
                    
                    for i, art in enumerate(articles[:2], 1):  # Max 2 por tópico no demo
                        demo_message += f"• {art['title']}\n"
                        if art.get('summary'):
                            # Resumo curto
                            short_summary = art['summary'][:150] + "..." if len(art['summary']) > 150 else art['summary']
                            demo_message += f"  _{short_summary}_\n"
                    
                    demo_message += "\n"
                
                await self._send_text_message(phone_number, demo_message)
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
        
        # Envia oferta
        await self._send_subscription_offer(phone_number)
    
    async def _send_subscription_offer(self, phone_number: str) -> None:
        """Envia oferta de assinatura com link de pagamento"""
        offer_message = (
            "✨ *Gostou do resumo?*\n\n"
            "Posso te enviar isso *todo dia às 07:00 e às 19:00*, "
            "personalizado com os temas que você escolheu.\n\n"
            "💰 *Planos:*\n"
            "• *Generalista* - R$ 9,90/mês\n"
            "  _5 tópicos por dia + Chat com IA_\n\n"
            "• *Estrategista* - R$ 29,90/mês\n"
            "  _10 tópicos + Áudios + Análises profundas_\n\n"
            "🎁 *Teste grátis por 5 dias!*"
        )
        
        await self._send_text_message(phone_number, offer_message)
        
        # Envia botões de plano
        await self._send_plan_buttons(phone_number)
    
    async def _handle_post_demo(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa resposta após demo - escolha de plano"""
        message_lower = message.lower().strip()
        
        if message_lower in ["generalista", "plano 1", "9,90", "básico", "basico"]:
            await self._send_payment_link(phone_number, "generalista")
        
        elif message_lower in ["estrategista", "plano 2", "29,90", "premium", "completo"]:
            await self._send_payment_link(phone_number, "estrategista")
        
        elif message_lower in ["não", "nao", "depois", "cancelar"]:
            await self._send_text_message(
                phone_number,
                "Sem problemas! 😊\n\n"
                "Quando quiser assinar, é só me mandar uma mensagem.\n"
                "Até mais!"
            )
        
        else:
            await self._send_text_message(
                phone_number,
                "Qual plano você prefere? Clique em uma das opções:"
            )
            await self._send_plan_buttons(phone_number)
    
    async def _send_payment_link(self, phone_number: str, plan: str) -> None:
        """Gera e envia link de pagamento do Stripe"""
        import stripe
        
        stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
        
        if not stripe.api_key:
            await self._send_text_message(
                phone_number,
                "⚠️ Sistema de pagamento temporariamente indisponível. "
                "Tente novamente em alguns minutos."
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
                "⚠️ Erro ao gerar link de pagamento. "
                "Por favor, tente novamente ou acesse nosso site."
            )
    
    async def _handle_awaiting_payment(self, phone_number: str, lead: Dict, message: str) -> None:
        """Processa mensagens enquanto aguarda pagamento"""
        message_lower = message.lower().strip()
        
        if message_lower in ["paguei", "pago", "pronto", "feito", "já paguei"]:
            # Verifica status do pagamento
            if lead.get("is_active"):
                await self._send_text_message(
                    phone_number,
                    "✅ *Pagamento confirmado!*\n\n"
                    "Sua assinatura está ativa. Você receberá seu primeiro resumo "
                    "amanhã às 07:00!\n\n"
                    "Enquanto isso, pode me perguntar qualquer coisa sobre as notícias. 😊"
                )
                await self._update_lead_state(phone_number, OnboardingState.ACTIVE)
            else:
                await self._send_text_message(
                    phone_number,
                    "⏳ Ainda não recebi a confirmação do pagamento.\n\n"
                    "Se você já pagou, aguarde alguns segundos e tente novamente.\n"
                    "Se precisar de ajuda, me avise!"
                )
        
        elif message_lower in ["trocar", "mudar plano", "outro plano"]:
            await self._send_plan_buttons(phone_number)
        
        else:
            await self._send_text_message(
                phone_number,
                "Estou aguardando a confirmação do seu pagamento. 😊\n\n"
                "Se precisar de um novo link, é só pedir!"
            )
    
    async def confirm_payment(self, phone_number: str, plan: str) -> None:
        """Chamado pelo webhook do Stripe quando pagamento é confirmado"""
        await self._send_text_message(
            phone_number,
            "🎉 *Pagamento confirmado!*\n\n"
            f"Bem-vindo ao Tindim *{plan.title()}*!\n\n"
            "📅 Você receberá seus resumos:\n"
            "• Às *07:00* - Para começar o dia informado\n"
            "• Às *19:00* - Para fechar o dia atualizado\n\n"
            "💬 E pode me perguntar qualquer coisa sobre as notícias a qualquer momento!\n\n"
            "Até amanhã às 07:00! 🌅"
        )
        
        await self._update_lead_state(
            phone_number,
            OnboardingState.ACTIVE,
            {"is_active": True, "plan": plan}
        )
    
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
    
    async def _send_interest_buttons(self, phone_number: str, page: int = 1, exclude: List[str] = None) -> bool:
        """Envia botões de seleção de interesses"""
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
