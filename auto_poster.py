import os
import sys
import time
import json
import requests
import hashlib
import hmac
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# Carregar variáveis de ambiente locais (se existirem)
load_dotenv()

# Desativa o buffer do Python para forçar o aparecimento de logs no Render imediatamente
sys.stdout.reconfigure(line_buffering=True)

# --- SERVIDOR WEBSERVICE DUMMY (PARA ENVIAR PORTA HTTP AO RENDER FREE) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("🤖 Bot AutoPoster Shopee/Meta está ativo e rodando no Render!".encode("utf-8"))

    def log_message(self, format, *args):
        return

def start_dummy_server():
    """Inicia um servidor HTTP em thread separada para satisfazer a checagem de porta do Render."""
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Servidor HTTP ativo na porta {port} (Web Service Render OK)", flush=True)
    server.serve_forever()

# --- VARIÁVEIS DE AMBIENTE ---
SHOPEE_APP_KEY = os.getenv("SHOPEE_APP_KEY")
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET")
META_USER_TOKEN = os.getenv("META_USER_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuração de Nichos e Termos de Busca na Shopee
NICHOS = {
    "Skincare": "skincare serum protetor solar",
    "Universo Feminino": "organizador maquiagem bolsa feminina",
    "Casa": "utilidades domesticas organizador casa cozinha"
}

# --- FUNÇÕES DA SHOPEE API (CORRIGIDO PARA HMAC-SHA256) ---
def generate_shopee_signature(timestamp, payload_str):
    message = f"{SHOPEE_APP_KEY}{timestamp}{payload_str}"
    return hmac.new(
        SHOPEE_APP_SECRET.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

def buscar_produto_shopee(keyword):
    """Busca produtos na Shopee GraphQL e retorna o primeiro item com imagem e link de afiliado."""
    url = "https://open-api.affiliate.shopee.com.br/graphql"
    timestamp = int(time.time())
    
    query = f"""
    query {{
        productOfferV2(keyword: "{keyword}", limit: 1) {{
            nodes {{
                itemId
                productName
                imageUrl
                offerLink
            }}
        }}
    }}
    """
    
    # Monta o corpo da requisição e gera a string JSON exata para a assinatura
    body = {"query": query.strip()}
    payload_str = json.dumps(body, separators=(',', ':'))
    
    signature = generate_shopee_signature(timestamp, payload_str)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_KEY}, Timestamp={timestamp}, Signature={signature}"
    }

    try:
        response = requests.post(url, data=payload_str, headers=headers, timeout=15)
        res_json = response.json()
        
        if "errors" in res_json:
            print(f"⚠️ Erro na resposta da API Shopee: {res_json.get('errors')}", flush=True)

        nodes = res_json.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        if nodes:
            item = nodes[0]
            return {
                "id": item.get("itemId"),
                "title": item.get("productName"),
                "image": item.get("imageUrl"),
                "link": item.get("offerLink")
            }
    except Exception as e:
        print(f"❌ Erro ao buscar na Shopee para '{keyword}': {e}", flush=True)
    
    return None

# --- FUNÇÃO DE ENVIO PARA O TELEGRAM (APROVAÇÃO) ---
def enviar_para_aprovacao_telegram(image_url, caption, product_id):
    """Envia a imagem, legenda e botões inline para aprovação no Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variáveis do Telegram não configuradas. Pulando envio de aprovação.", flush=True)
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Aprovar / Publicar", "callback_data": f"approve_{product_id}"},
                {"text": "❌ Descartar", "callback_data": f"reject_{product_id}"}
            ]
        ]
    }
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": image_url,
        "caption": caption,
        "reply_markup": keyboard
    }
    
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"📲 Produto {product_id} enviado com SUCESSO para o Telegram (Chat ID: {TELEGRAM_CHAT_ID})!", flush=True)
            return True
        else:
            print(f"⚠️ Erro no Telegram (Status {resp.status_code}): {resp.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro de conexão com o Telegram: {e}", flush=True)
    
    return False

# --- ROTINA PRINCIPAL DO AUTOPOSTER ---
def run_autoposter():
    print("\n🤖 Iniciando Rotina do AutoPoster...", flush=True)
    
    for niche_name, search_term in NICHOS.items():
        print(f"\n🔍 Processando Nicho: {niche_name.upper()} (Busca: '{search_term}')", flush=True)
        produto = buscar_produto_shopee(search_term)
        
        if produto:
            title = produto["title"]
            img = produto["image"]
            link = produto["link"]
            prod_id = produto["id"]
            
            caption = (
                f"✨ {title}\n\n"
                f"🛍 Confira e garanta o seu pelo link na bio!\n"
                f"🔗 Link: {link}\n\n"
                f"#{niche_name.lower().replace(' ', '')} #achadinhos #shopee #promoção"
            )
            
            print(f"📌 Encontrado: {title}", flush=True)
            print(f"🖼 Imagem: {img}", flush=True)
            
            # Envia para revisar e aprovar no Telegram
            enviar_para_aprovacao_telegram(img, caption, prod_id)
        else:
            print(f"⚠️ Nenhum produto encontrado para o nicho {niche_name}.", flush=True)

# --- EXECUÇÃO DO WEB SERVICE E LOOP ---
if __name__ == "__main__":
    print("🚀 Script auto_poster.py inicializado!", flush=True)
    
    # 1. Inicia o servidor HTTP fictício em segundo plano
    threading.Thread(target=start_dummy_server, daemon=True).start()
    
    # 2. Executa o loop contínuo a cada 4 horas
    while True:
        print("\n==============================================", flush=True)
        print("🤖 Rodada de busca e envio de postagens iniciada!", flush=True)
        
        run_autoposter()
        
        print("\n⏳ Rodada concluída! Aguardando 4 horas para a próxima...", flush=True)
        print("==============================================", flush=True)
        time.sleep(14400)  # 14400 segundos = 4 horas