"""
Script de teste local para o Tindim
Execute: python test_local.py
"""
import asyncio
import httpx

BASE_URL = "http://localhost:8000/api/v1"

async def test_all():
    async with httpx.AsyncClient(timeout=60.0) as client:
        print("🔍 Testando Tindim localmente...\n")
        
        # 1. Health Check
        print("1️⃣ Health Check...")
        response = await client.get(f"{BASE_URL}/test/health")
        print(f"   Status: {response.status_code}")
        print(f"   Resposta: {response.json()}\n")
        
        # 2. Coletar Notícias
        print("2️⃣ Coletando notícias dos feeds RSS...")
        response = await client.post(f"{BASE_URL}/test/ingest-news")
        result = response.json()
        print(f"   Status: {response.status_code}")
        print(f"   Artigos coletados: {result.get('articles_collected', 0)}\n")
        
        # 3. Processar com IA
        print("3️⃣ Processando artigos com IA (Gemini)...")
        response = await client.post(f"{BASE_URL}/test/process-articles")
        result = response.json()
        print(f"   Status: {response.status_code}")
        print(f"   Artigos processados: {result.get('articles_processed', 0)}\n")
        
        # 4. Testar Chat (simulação)
        print("4️⃣ Testando Chat Assistant...")
        test_message = {
            "phone_number": "5511999999999",
            "message": "Me explica sobre as notícias de tecnologia"
        }
        try:
            response = await client.post(
                f"{BASE_URL}/test/chat-message",
                json=test_message
            )
            result = response.json()
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print(f"   Resposta do assistente: {result.get('response', '')[:100]}...\n")
            else:
                print(f"   Erro: {result}\n")
        except Exception as e:
            print(f"   Erro: {e}\n")
        
        # 5. Enviar Resumo (CUIDADO: vai enviar WhatsApp de verdade!)
        print("5️⃣ Teste de envio de resumo (DESCOMENTE PARA ENVIAR)...")
        print("   ⚠️  ATENÇÃO: Isso vai enviar mensagens de WhatsApp reais!")
        print("   Para testar, descomente as linhas no código.\n")
        
        # Descomente as linhas abaixo para testar o envio real:
        # response = await client.post(f"{BASE_URL}/test/send-digest")
        # result = response.json()
        # print(f"   Status: {response.status_code}")
        # print(f"   Resultado: {result}\n")
        
        print("✅ Testes concluídos!")
        print("\n📋 Próximos passos:")
        print("   1. Adicione um usuário de teste no Supabase (use add_test_user.sql)")
        print("   2. Descomente o teste de envio acima para testar WhatsApp")
        print("   3. Configure o webhook para receber mensagens")
        print("   4. Obtenha uma chave do ElevenLabs para testar áudios")

if __name__ == "__main__":
    asyncio.run(test_all())
