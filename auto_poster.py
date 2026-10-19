import os
import sys
import time
import json
import hashlib
import requests
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

# Carregar variáveis de ambiente locais (se existirem)
load_dotenv()

# Desativa o buffer do Python para forçar o aparecimento de logs no Render imediatamente
sys.stdout.reconfigure(line_buffering=True)

# --- VARIÁVEIS DE AMBIENTE ---
SHOPEE_APP_KEY    = os.getenv("SHOPEE_APP_KEY", "").strip()
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "").strip()

print(f"🔑 Debug Chaves -> App Key Length: {len(SHOPEE_APP_KEY)} | Secret Length: {len(SHOPEE_APP_SECRET)}", flush=True)

# Configuração de Nichos e Termos de Busca na Shopee
NICHOS = {
    "Skincare":          "skincare serum protetor solar",
    "Universo Feminino": "organizador maquiagem bolsa feminina",
    "Casa":              "utilidades domesticas organizador casa cozinha",
}

# -----------------------------------------------------------------------
# ASSINATURA SHOPEE AFFILIATE — SHA-256 SIMPLES (NÃO HMAC!)
#
# Fórmula oficial:  factor = AppId + Timestamp + Payload + Secret
# Hash:             SHA-256(factor)  →  hex string
# -----------------------------------------------------------------------
def generate_shopee_signature(app_key: str, secret: str, timestamp: int, payload_str: str) -> str:
    """
    Gera a assinatura SHA-256 para a Shopee Affiliate Open API.

    ATENÇÃO: A Shopee Affiliate usa SHA-256 puro (hashlib.sha256),
    NÃO HMAC-SHA256. O Secret é concatenado NO FINAL da string base.
    """
    factor = f"{app_key}{timestamp}{payload_str}{secret}"
    print(f"🔏 Factor = AppKey({len(app_key)}) + Timestamp + Payload({len(payload_str)}) + Secret({len(secret)})", flush=True)
    signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()
    print(f"🔑 Assinatura SHA-256: {signature}", flush=True)
    return signature


def buscar_produto_shopee(keyword: str):
    """Busca produtos na Shopee GraphQL com autenticação SHA-256 validada."""
    url = "https://open-api.affiliate.shopee.com.br/graphql"

    timestamp = int(time.time())

    # Query GraphQL compacta (sem espaços extras)
    query_str = (
        f'{{ productOfferV2(keyword: "{keyword}", limit: 1) '
        f'{{ nodes {{ itemId productName imageUrl offerLink }} }} }}'
    )

    body        = {"query": query_str}
    payload_str = json.dumps(body, separators=(",", ":"))

    print(f"📦 Payload: {payload_str}", flush=True)

    signature = generate_shopee_signature(SHOPEE_APP_KEY, SHOPEE_APP_SECRET, timestamp, payload_str)

    # ✅ Header correto: sem espaços após as vírgulas
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_KEY},Timestamp={timestamp},Signature={signature}",
    }

    try:
        response    = requests.post(url, data=payload_str, headers=headers, timeout=15)
        res_json    = response.json()

        if "errors" in res_json:
            print(f"⚠️ Erro na resposta da API Shopee para '{keyword}': {res_json.get('errors')}", flush=True)

        nodes = res_json.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        if nodes:
            item = nodes[0]
            return {
                "id":    item.get("itemId"),
                "title": item.get("productName"),
                "image": item.get("imageUrl"),
                "link":  item.get("offerLink"),
            }
    except Exception as e:
        print(f"❌ Erro de conexão ao buscar na Shopee para '{keyword}': {e}", flush=True)

    return None


# -----------------------------------------------------------------------
# TELEGRAM — Envio para aprovação
# -----------------------------------------------------------------------
def enviar_para_aprovacao_telegram(image_url: str, caption: str, product_id) -> bool:
    """Envia foto + legenda + botões inline para aprovação no Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variáveis do Telegram não configuradas. Pulando envio de aprovação.", flush=True)
        return False

    url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "✅ Aprovar / Publicar", "callback_data": f"approve_{product_id}"},
                {"text": "❌ Descartar",           "callback_data": f"reject_{product_id}"},
            ]
        ]
    }

    payload = {
        "chat_id":      TELEGRAM_CHAT_ID,
        "photo":        image_url,
        "caption":      caption,
        "parse_mode":   "HTML",
        "reply_markup": json.dumps(keyboard),   # ✅ precisa ser string JSON
    }

    try:
        resp = requests.post(url_api, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"📱 Produto {product_id} enviado com SUCESSO para o Telegram!", flush=True)
            return True
        else:
            print(f"⚠️ Erro no Telegram (Status {resp.status_code}): {resp.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro de conexão com o Telegram: {e}", flush=True)

    return False


# -----------------------------------------------------------------------
# TELEGRAM — Processamento de callback (Aprovar / Rejeitar)
# -----------------------------------------------------------------------
def processar_callback_telegram(callback_query: dict):
    """
    Processa a resposta do usuário aos botões inline do Telegram.
    Chame esta função ao receber um update com `callback_query`.
    """
    data         = callback_query.get("data", "")
    callback_id  = callback_query.get("id")
    chat_id      = callback_query.get("message", {}).get("chat", {}).get("id")

    # Responde o callback para remover o "loading" do botão
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10,
        )
    except Exception:
        pass

    if data.startswith("approve_"):
        product_id = data.replace("approve_", "")
        print(f"✅ APROVADO pelo usuário! Produto ID: {product_id}", flush=True)
        # TODO: Chamar aqui a Meta Graph API para postar no Instagram
        msg = f"✅ Post aprovado! Produto <b>{product_id}</b> será publicado no Instagram em breve."
    elif data.startswith("reject_"):
        product_id = data.replace("reject_", "")
        print(f"❌ REJEITADO pelo usuário! Produto ID: {product_id}", flush=True)
        msg = f"❌ Post descartado. Produto <b>{product_id}</b> ignorado."
    else:
        return

    # Envia mensagem de confirmação ao usuário
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Erro ao confirmar callback Telegram: {e}", flush=True)


# -----------------------------------------------------------------------
# SERVIDOR HTTP — Health check (Render.com) + Webhook Telegram
# -----------------------------------------------------------------------
class BotHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("🤖 Bot AutoPoster Shopee/Meta está ativo no Render!".encode("utf-8"))

    def do_POST(self):
        """Recebe webhooks do Telegram (callbacks dos botões inline)."""
        try:
            length  = int(self.headers.get("Content-Length", 0))
            body    = self.rfile.read(length)
            update  = json.loads(body.decode("utf-8"))

            if "callback_query" in update:
                processar_callback_telegram(update["callback_query"])

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print(f"❌ Erro no webhook POST: {e}", flush=True)
            self.send_response(500)
            self.end_headers()

    def log_message(self, format, *args):
        return  # Silencia logs HTTP


def start_server():
    """Inicia o servidor HTTP em thread separada."""
    port   = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), BotHandler)
    print(f"🌐 Servidor HTTP ativo na porta {port} (Web Service Render OK)", flush=True)
    server.serve_forever()


# -----------------------------------------------------------------------
# ROTINA PRINCIPAL DO AUTOPOSTER
# -----------------------------------------------------------------------
def run_autoposter():
    print("\n🤖 Iniciando Rotina do AutoPoster...\n", flush=True)

    for niche_name, search_term in NICHOS.items():
        print(f"\n🔍 Processando Nicho: {niche_name.upper()} (Busca: '{search_term}')", flush=True)

        produto = buscar_produto_shopee(search_term)

        if produto:
            title   = produto["title"]
            img     = produto["image"]
            link    = produto["link"]
            prod_id = produto["id"]

            hashtag_slug = niche_name.lower().replace(" ", "")

            caption = (
                f"✨ <b>{title}</b>\n\n"
                f"🛒 Confira e garanta o seu pelo link na bio!\n"
                f"🔗 Link: {link}\n\n"
                f"#{hashtag_slug} #achadinhos #shopee #promoção"
            )

            print(f"📦 Encontrado: {title}", flush=True)
            print(f"🖼️ Imagem: {img}", flush=True)

            enviar_para_aprovacao_telegram(img, caption, prod_id)
        else:
            print(f"⚠️ Nenhum produto encontrado para o nicho {niche_name}.", flush=True)


# -----------------------------------------------------------------------
# EXECUÇÃO
# -----------------------------------------------------------------------
if __name__ == "__main__":
    print("🚀 Script auto_poster.py inicializado!", flush=True)

    # 1. Inicia o servidor HTTP em background (porta Render + webhook Telegram)
    threading.Thread(target=start_server, daemon=True).start()

    # 2. Loop a cada 4 horas
    while True:
        print("\n==============================================", flush=True)
        print("🤖 Rodada de busca e envio de postagens iniciada!", flush=True)

        run_autoposter()

        print("\n⏳ Rodada concluída! Aguardando 4 horas para a próxima...", flush=True)
        print("==============================================", flush=True)
        time.sleep(14400)  # 4 horas
