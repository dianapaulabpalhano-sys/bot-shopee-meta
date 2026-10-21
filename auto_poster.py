import os
import sys
import time
import json
import hashlib
import requests
import threading
import subprocess
import shutil
import random
from urllib.parse import urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

# Carrega variáveis de ambiente locais (se houver .env)
load_dotenv()

# Força logs imediatos sem buffer (essencial para o Render)
sys.stdout.reconfigure(line_buffering=True)

# =======================================================================
# CONFIGURAÇÕES E VARIÁVEIS DE AMBIENTE
# =======================================================================
SHOPEE_APP_KEY       = os.getenv("SHOPEE_APP_KEY", "").strip()
SHOPEE_APP_SECRET    = os.getenv("SHOPEE_APP_SECRET", "").strip()
TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "").strip()
META_USER_TOKEN      = os.getenv("META_USER_TOKEN", "").strip()
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()

# URL base pública do Render para servir os vídeos gerados para a Meta API
RENDER_EXTERNAL_URL  = os.getenv("RENDER_EXTERNAL_URL", "https://bot-shopee-meta.onrender.com").rstrip("/")

print(f"🔑 [DEBUG] Shopee App Key: {len(SHOPEE_APP_KEY)} chars | Secret: {len(SHOPEE_APP_SECRET)} chars", flush=True)
print(f"🔑 [DEBUG] Telegram Token: {bool(TELEGRAM_BOT_TOKEN)} | Chat ID: {TELEGRAM_CHAT_ID}", flush=True)
print(f"🔑 [DEBUG] Meta Token: {bool(META_USER_TOKEN)} | Instagram ID: {INSTAGRAM_ACCOUNT_ID}", flush=True)
print(f"🌐 [DEBUG] URL Externa Render: {RENDER_EXTERNAL_URL}", flush=True)

# Diretório para armazenamento dos vídeos gerados para Reels
VIDEO_DIR = os.path.join(os.getcwd(), "temp_videos")
os.makedirs(VIDEO_DIR, exist_ok=True)

# Arquivo para persistência de produtos enviados / descartados (evita repetições pós-restart)
ARQUIVO_HISTORICO = os.path.join(os.getcwd(), "enviados.json")

# Lojas oficiais coreanas aprovadas exclusivamente
LOJAS_APROVADAS = ["glory of seoul", "koksara", "jadoo"]

# Catálogo variado de buscas focadas em Skincare Coreano e nas 3 lojas
BUSCAS_SKINCARE_BASE = [
    # Glory of Seoul
    "Glory of Seoul",
    "Glory of Seoul centella",
    "Glory of Seoul protetor solar",
    "Glory of Seoul anua",
    "Glory of Seoul torriden",
    "Glory of Seoul cosrx",
    "Glory of Seoul skincare coreano",
    # Koksara
    "Koksara",
    "Koksara beauty of joseon",
    "Koksara serum",
    "Koksara retinol",
    "Koksara vitamina c",
    "Koksara round lab",
    "Koksara skincare coreano",
    "Koksara creme hidratante",
    # Jadoo
    "Jadoo skincare",
    "Jadoo seleve pdrn",
    "Jadoo tirtir",
    "Jadoo tonico coreano",
    "Jadoo skincare coreano",
    "Jadoo mediheal",
    "Jadoo dr althea"
]

# Armazenamento em memória dos produtos pendentes para aprovação
PRODUTOS_PENDENTES = {}


# =======================================================================
# PERSISTÊNCIA DE HISTÓRICO (EVITA PRODUTOS REPETIDOS APÓS REINÍCIO)
# =======================================================================
def carregar_produtos_enviados() -> set:
    """Lê do arquivo local os IDs de produtos já enviados ou descartados."""
    if os.path.exists(ARQUIVO_HISTORICO):
        try:
            with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return set(str(i) for i in dados)
        except Exception as e:
            print(f"⚠️ Erro ao ler {ARQUIVO_HISTORICO}: {e}", flush=True)
    return set()


def salvar_produto_enviado(item_id: str):
    """Grava o ID do produto permanentemente no arquivo para nunca repetir."""
    PRODUTOS_ENVIADOS.add(str(item_id))
    try:
        with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
            json.dump(list(PRODUTOS_ENVIADOS), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar {ARQUIVO_HISTORICO}: {e}", flush=True)


PRODUTOS_ENVIADOS = carregar_produtos_enviados()
print(f"📋 Histórico carregado: {len(PRODUTOS_ENVIADOS)} produtos já registrados no banco.", flush=True)


# =======================================================================
# 1. MOTOR DE VÍDEO E CAPTURA DE VÍDEO REAL (FFMPEG + SHOPEE)
# =======================================================================
def get_ffmpeg_binary() -> str:
    """Detecta o binário do ffmpeg instalado no sistema ou imageio-ffmpeg."""
    ffmpeg_sys = shutil.which("ffmpeg")
    if ffmpeg_sys:
        return ffmpeg_sys
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def gerar_video_reels_da_imagem(image_url: str, item_id: str) -> str:
    """Compila vídeo vertical MP4 (1080x1920) de 7s aceito pela Meta para Reels."""
    output_path = os.path.join(VIDEO_DIR, f"{item_id}.mp4")
    temp_img_path = os.path.join(VIDEO_DIR, f"{item_id}_temp.jpg")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return output_path

    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        print("⚠️ FFmpeg não encontrado para gerar vídeo de Reels.", flush=True)
        return None

    try:
        print(f"🎬 Gerando vídeo Reels vertical para o produto {item_id}...", flush=True)
        img_resp = requests.get(image_url, timeout=20)
        with open(temp_img_path, "wb") as f:
            f.write(img_resp.content)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", temp_img_path,
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-t", "7",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Vídeo compilado com sucesso ({os.path.getsize(output_path)} bytes)!", flush=True)
            return output_path
        else:
            print(f"❌ Erro FFmpeg: {result.stderr.decode('utf-8', errors='ignore')[:300]}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Falha ao compilar vídeo para Reels: {e}", flush=True)
        return None


def obter_video_real_shopee(offer_link: str, item_id: str, fallback_image_url: str) -> str:
    """Tenta extrair vídeo nativo do anúncio na Shopee ou usa gerador de vídeo."""
    output_path = os.path.join(VIDEO_DIR, f"{item_id}.mp4")
    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return output_path

    try:
        print(f"🔍 Verificando se o produto {item_id} possui vídeo nativo...", flush=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "pt-BR,pt;q=0.9"
        }
        session = requests.Session()
        resp = session.get(offer_link, headers=headers, allow_redirects=True, timeout=15)
        html_content = resp.text

        import re
        match_video = re.search(r'https?://[^\s<>"]+?\.mp4', html_content)
        if match_video:
            video_url = match_video.group(0)
            print(f"🎬 Vídeo nativo encontrado! Baixando de: {video_url[:60]}...", flush=True)
            vid_resp = session.get(video_url, headers=headers, timeout=25)
            if vid_resp.status_code == 200 and len(vid_resp.content) > 5000:
                with open(output_path, "wb") as f:
                    f.write(vid_resp.content)
                print(f"✅ Vídeo nativo baixado ({os.path.getsize(output_path)} bytes)!", flush=True)
                return output_path
    except Exception as e:
        print(f"⚠️ Erro ao extrair vídeo nativo: {e}", flush=True)

    return gerar_video_reels_da_imagem(fallback_image_url, item_id)


# =======================================================================
# 2. AUTENTICAÇÃO E BUSCA NA SHOPEE (COM PAGINAÇÃO E VARIABILIDADE)
# =======================================================================
def generate_shopee_signature(app_key: str, secret: str, timestamp: int, payload_str: str) -> str:
    """Gera a assinatura oficial SHA-256 (AppId + Timestamp + Payload + Secret)."""
    factor = f"{app_key}{timestamp}{payload_str}{secret}"
    return hashlib.sha256(factor.encode("utf-8")).hexdigest()


def buscar_produtos_shopee(keyword: str, page: int = 1, limit: int = 20, sort_type: int = 2):
    """
    Busca produtos na Shopee com paginação e ordenação variada
    para sempre trazer itens novos e evitar repetições.
    """
    url = "https://open-api.affiliate.shopee.com.br/graphql"
    timestamp = int(time.time())

    query_str = (
        f'{{ productOfferV2(keyword: "{keyword}", page: {page}, limit: {limit}, sortType: {sort_type}) '
        f'{{ nodes {{ itemId productName imageUrl offerLink shopName priceMin }} }} }}'
    )

    body = {"query": query_str}
    payload_str = json.dumps(body, separators=(",", ":"))
    signature = generate_shopee_signature(SHOPEE_APP_KEY, SHOPEE_APP_SECRET, timestamp, payload_str)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_KEY},Timestamp={timestamp},Signature={signature}",
    }

    try:
        resp = requests.post(url, data=payload_str, headers=headers, timeout=15)
        res_json = resp.json()

        if "errors" in res_json:
            print(f"⚠️ Erro Shopee para '{keyword}': {res_json.get('errors')}", flush=True)
            return []

        nodes = res_json.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        return nodes or []
    except Exception as e:
        print(f"❌ Erro de conexão com Shopee para '{keyword}': {e}", flush=True)
        return []


def produto_pertence_lojas_alvo(item: dict, termo_busca: str) -> bool:
    """Verifica se o produto pertence a Glory of Seoul, Koksara ou Jadoo."""
    shop_name = (item.get("shopName") or "").lower()
    product_name = (item.get("productName") or "").lower()
    termo = termo_busca.lower()

    for loja in LOJAS_APROVADAS:
        if loja in shop_name or loja in product_name or loja in termo:
            return True
    return False


# =======================================================================
# 3. INTEGRAÇÃO META GRAPH API (INSTAGRAM FEED, STORIES & REELS)
# =======================================================================
def verificar_conexao_meta():
    """Valida se o token e conta do Instagram estão ativos na Meta Graph API."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        print("⚠️ Meta Graph API não configurada no ambiente.", flush=True)
        return False
    try:
        url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}?fields=username,name&access_token={META_USER_TOKEN}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "username" in data:
            print(f"✅ Conectado ao Instagram @{data.get('username')} (Nome: {data.get('name')})", flush=True)
            return True
        else:
            print(f"⚠️ Meta API retorno: {data}", flush=True)
            return False
    except Exception as e:
        print(f"❌ Falha ao verificar Meta API: {e}", flush=True)
        return False


def publicar_instagram_feed(image_url: str, caption: str) -> dict:
    """Publica post de imagem no Feed do Instagram da Diana (@dianapaulab)."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"📸 Publicando no FEED do Instagram...", flush=True)
    container_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    container_payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": META_USER_TOKEN
    }

    try:
        res = requests.post(container_url, data=container_payload, timeout=30)
        res_data = res.json()
        if "id" not in res_data:
            return {"success": False, "error": res_data.get("error", {}).get("message", str(res_data))}

        creation_id = res_data["id"]
        time.sleep(3)

        publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": META_USER_TOKEN}, timeout=30)
        pub_data = pub_res.json()

        if "id" in pub_data:
            media_id = pub_data["id"]
            print(f"🎉 SUCESSO! Post publicado no Feed. Media ID: {media_id}", flush=True)
            return {"success": True, "media_id": media_id}
        else:
            return {"success": False, "error": pub_data.get("error", {}).get("message", str(pub_data))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def publicar_instagram_story(image_url: str) -> dict:
    """Publica imagem diretamente nos STORIES do Instagram."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"🌟 Publicando nos STORIES do Instagram...", flush=True)
    container_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    container_payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": META_USER_TOKEN
    }

    try:
        res = requests.post(container_url, data=container_payload, timeout=30)
        res_data = res.json()
        if "id" not in res_data:
            return {"success": False, "error": res_data.get("error", {}).get("message", str(res_data))}

        creation_id = res_data["id"]
        time.sleep(3)

        publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": META_USER_TOKEN}, timeout=30)
        pub_data = pub_res.json()

        if "id" in pub_data:
            media_id = pub_data["id"]
            print(f"🎉 SUCESSO! Story publicado no Instagram. Media ID: {media_id}", flush=True)
            return {"success": True, "media_id": media_id}
        else:
            return {"success": False, "error": pub_data.get("error", {}).get("message", str(pub_data))}
    except Exception as e:
        return {"success": False, "error": str(e)}


def publicar_instagram_reel(video_url: str, caption: str) -> dict:
    """Publica vídeo nos REELS do Instagram com compartilhamento opcional no Feed."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"🎬 Iniciando publicação nos REELS via URL: {video_url}...", flush=True)
    container_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    container_payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": META_USER_TOKEN
    }

    try:
        res = requests.post(container_url, data=container_payload, timeout=30)
        res_data = res.json()
        if "id" not in res_data:
            print(f"❌ Erro container Reels: {res_data}", flush=True)
            return {"success": False, "error": res_data.get("error", {}).get("message", str(res_data))}

        creation_id = res_data["id"]
        print(f"📦 Container Reels criado: {creation_id}. Aguardando transcodificação da Meta...", flush=True)

        status_url = f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={META_USER_TOKEN}"
        pronto = False
        for _ in range(15):
            time.sleep(3)
            st_res = requests.get(status_url, timeout=15).json()
            status = st_res.get("status_code")
            if status == "FINISHED":
                pronto = True
                break
            elif status in ["ERROR", "EXPIRED"]:
                return {"success": False, "error": f"Erro no processamento de vídeo da Meta ({status})"}

        if not pronto:
            return {"success": False, "error": "Tempo limite excedido no processamento do vídeo pela Meta."}

        publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": META_USER_TOKEN}, timeout=30)
        pub_data = pub_res.json()

        if "id" in pub_data:
            media_id = pub_data["id"]
            print(f"🎉 SUCESSO! Reel publicado no Instagram. Media ID: {media_id}", flush=True)
            return {"success": True, "media_id": media_id}
        else:
            return {"success": False, "error": pub_data.get("error", {}).get("message", str(pub_data))}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =======================================================================
# 4. INTERAÇÃO TELEGRAM — BOTÕES COMPLETOS E CALLBACKS
# =======================================================================
def enviar_para_aprovacao_telegram(produto: dict) -> bool:
    """Envia produto para o Telegram com botões para Feed, Story, Reels e Todos."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variáveis do Telegram não configuradas.", flush=True)
        return False

    item_id = str(produto["id"])
    PRODUTOS_PENDENTES[item_id] = produto

    url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📸 Postar no Feed",       "callback_data": f"feed_{item_id}"},
                {"text": "🌟 Postar no Story",      "callback_data": f"story_{item_id}"}
            ],
            [
                {"text": "🎬 Postar no Reels",      "callback_data": f"reel_{item_id}"},
                {"text": "🚀 Postar em Todos",      "callback_data": f"all_{item_id}"}
            ],
            [
                {"text": "❌ Descartar",            "callback_data": f"reject_{item_id}"}
            ]
        ]
    }

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": produto["image"],
        "caption": produto["caption"],
        "parse_mode": "HTML",
        "reply_markup": json.dumps(keyboard),
    }

    try:
        resp = requests.post(url_api, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"📱 Produto {item_id} enviado para o Telegram com sucesso!", flush=True)
            salvar_produto_enviado(item_id)
            return True
        else:
            print(f"⚠️ Erro ao enviar para Telegram ({resp.status_code}): {resp.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro de conexão Telegram: {e}", flush=True)

    return False


def processar_acao_telegram(callback_data: str, callback_id: str, chat_id: int):
    """Executa a publicação escolhida pela Diana no Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": "Processando sua escolha..."},
            timeout=10,
        )
    except Exception:
        pass

    partes = callback_data.split("_", 1)
    if len(partes) != 2:
        return

    acao, item_id = partes[0], partes[1]
    produto = PRODUTOS_PENDENTES.get(item_id)

    if acao == "reject":
        print(f"🗑️ Produto {item_id} descartado pela Diana. Marcado como ignorado.", flush=True)
        salvar_produto_enviado(item_id)
        PRODUTOS_PENDENTES.pop(item_id, None)
        enviar_mensagem_telegram(chat_id, f"❌ Produto <b>{item_id}</b> descartado. Não voltará a aparecer!")
        return

    if not produto:
        msg = f"⚠️ Produto <b>{item_id}</b> expirou da memória temporária ou já foi postado."
        enviar_mensagem_telegram(chat_id, msg)
        return

    image_url = produto["image"]
    caption = produto["caption"]
    nome_prod = produto["title"]

    # 1. Postar no Feed
    if acao == "feed":
        res = publicar_instagram_feed(image_url, caption)
        if res.get("success"):
            msg = f"🎉 <b>PUBLICADO NO FEED COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Feed:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)

    # 2. Postar no Story
    elif acao == "story":
        res = publicar_instagram_story(image_url)
        if res.get("success"):
            msg = f"🌟 <b>PUBLICADO NO STORY COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Story:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)

    # 3. Postar no Reels
    elif acao == "reel":
        enviar_mensagem_telegram(chat_id, "🎬 <i>A preparar vídeo de demonstração para o Reels... aguarde instantes!</i>")
        video_local = obter_video_real_shopee(produto["link"], item_id, image_url)
        if not video_local:
            enviar_mensagem_telegram(chat_id, "❌ Não foi possível obter o vídeo para o Reels.")
            return

        video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
        res = publicar_instagram_reel(video_public_url, caption)
        if res.get("success"):
            msg = f"🎬 <b>REELS PUBLICADO COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Reels:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)

    # 4. Postar em Todos (Feed + Story + Reels)
    elif acao == "all":
        enviar_mensagem_telegram(chat_id, "🚀 <i>Publicando em todos os formatos (Feed + Story + Reels)...</i>")
        res_feed = publicar_instagram_feed(image_url, caption)
        time.sleep(2)
        res_story = publicar_instagram_story(image_url)
        time.sleep(2)

        video_local = obter_video_real_shopee(produto["link"], item_id, image_url)
        if video_local:
            video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
            res_reel = publicar_instagram_reel(video_public_url, caption)
            status_reel = "✅ Reels OK" if res_reel.get("success") else f"❌ Reels: {res_reel.get('error')}"
        else:
            status_reel = "⚠️ Reels: Vídeo indisponível"

        status_feed = "✅ Feed OK" if res_feed.get("success") else f"❌ Feed: {res_feed.get('error')}"
        status_story = "✅ Story OK" if res_story.get("success") else f"❌ Story: {res_story.get('error')}"

        msg = (
            f"🚀 <b>PUBLICAÇÃO CONCLUÍDA:</b>\n\n"
            f"🛍️ <b>{nome_prod}</b>\n"
            f"• {status_feed}\n"
            f"• {status_story}\n"
            f"• {status_reel}"
        )
        enviar_mensagem_telegram(chat_id, msg)

    salvar_produto_enviado(item_id)
    PRODUTOS_PENDENTES.pop(item_id, None)


def enviar_mensagem_telegram(chat_id: int, texto: str):
    """Envia mensagem de texto/notificação para o chat do Telegram."""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem de status Telegram: {e}", flush=True)


def telegram_polling_listener():
    """Thread contínua de escuta de botões do Telegram (long polling robusto)."""
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook", timeout=10)
    except Exception:
        pass

    offset = 0
    print("👂 Ouvinte de aprovações do Telegram ATIVO!", flush=True)

    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=20"
            resp = requests.get(url, timeout=25)
            data = resp.json()

            for update in data.get("result", []):
                offset = update["update_id"] + 1

                if "callback_query" in update:
                    cb = update["callback_query"]
                    cb_data = cb.get("data", "")
                    cb_id = cb.get("id")
                    chat_id = cb.get("message", {}).get("chat", {}).get("id")
                    processar_acao_telegram(cb_data, cb_id, chat_id)

        except Exception:
            time.sleep(3)


# =======================================================================
# 5. SERVIDOR HTTP (HEALTH CHECK DO RENDER + SERVIR VÍDEOS DE REELS)
# =======================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/reels/"):
            filename = os.path.basename(parsed.path)
            file_path = os.path.join(VIDEO_DIR, filename)

            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Video nao encontrado")
                return

        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = "✨ <b>Bot Shopee Meta Skincare Coreano (@dianapaulab)</b> ativo com suporte a Feed, Story e Reels!"
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Servidor HTTP ativo na porta {port} (Render + Reels OK)", flush=True)
    server.serve_forever()


# =======================================================================
# 6. ROTINA PRINCIPAL DO BOT DE SKINCARE COREANO (ROTATIVA E INTELIGENTE)
# =======================================================================
def run_autoposter():
    print("\n🌸 ==============================================", flush=True)
    print("🤖 Buscando achadinhos de Skincare Coreano (Glory of Seoul, Koksara, Jadoo)...", flush=True)

    produtos_encontrados_rodada = 0

    # Embaralha a lista de termos para alternar lojas e marcas a cada rodada
    termos_rodada = list(BUSCAS_SKINCARE_BASE)
    random.shuffle(termos_rodada)

    # Escolhe aleatoriamente uma página e ordenação na Shopee para descobrir produtos novos
    pagina_aleatoria = random.randint(1, 5)
    ordenacao_aleatoria = random.choice([1, 2, 5])  # 1=Relevância, 2=Mais Vendidos, 5=Mais Recentes

    for termo in termos_rodada:
        print(f"\n🔍 Buscando na Shopee por: '{termo}' (Pág {pagina_aleatoria}, Ordenação {ordenacao_aleatoria})...", flush=True)
        itens = buscar_produtos_shopee(termo, page=pagina_aleatoria, limit=20, sort_type=ordenacao_aleatoria)

        # Embaralha os produtos retornados da Shopee para nunca pegar sempre o primeiro
        random.shuffle(itens)

        for item in itens:
            item_id = str(item.get("itemId"))
            title = item.get("productName", "")
            img = item.get("imageUrl", "")
            link = item.get("offerLink", "")
            shop = item.get("shopName", "Loja Coreana Oficial")

            # Verifica se já foi enviado anteriormente (histórico persistente)
            if item_id in PRODUTOS_ENVIADOS:
                continue

            if not produto_pertence_lojas_alvo(item, termo):
                continue

            caption = (
                f"💖 <b>{title}</b>\n\n"
                f"✨ Pele de porcelana e glow natural com o melhor do Skincare Coreano original!\n"
                f"🏢 Loja Oficial: <b>{shop}</b>\n\n"
                f"🛍️ <b>Como garantir o seu:</b>\n"
                f"👉 Toque na sacolinha da foto para comprar direto na Shopee!\n"
                f"👉 Ou clique no link da bio do perfil @dianapaulab\n"
                f"🔗 Link direto: {link}\n\n"
                f"#skincarecoreano #kbeauty #kbeautybrasil #gloryofseoul #koksara #jadoo "
                f"#achadinhosshopee #shopeebrasil #rotinadeskincare #dianapaulab"
            )

            produto_dict = {
                "id": item_id,
                "title": title,
                "image": img,
                "link": link,
                "shop": shop,
                "caption": caption
            }

            print(f"📦 [NOVO PRODUTO SELECIONADO] {title} ({shop})", flush=True)
            sucesso = enviar_para_aprovacao_telegram(produto_dict)
            if sucesso:
                produtos_encontrados_rodada += 1
                # Envia um por nicho/loja por rodada para não sobrecarregar o Telegram
                break

        if produtos_encontrados_rodada >= 3:
            break

    print(f"\n✨ Rodada finalizada. {produtos_encontrados_rodada} novos produtos enviados para aprovação no Telegram.", flush=True)


# =======================================================================
# 7. INICIALIZAÇÃO
# =======================================================================
if __name__ == "__main__":
    print("🚀 AutoPoster Shopee + Meta Graph API (Feed, Stories & Reels) iniciando...", flush=True)

    # 1. Valida conexão com Instagram Meta
    verificar_conexao_meta()

    # 2. Inicia servidor HTTP (porta Render + servidor de vídeos de Reels)
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # 3. Inicia ouvinte de cliques do Telegram
    threading.Thread(target=telegram_polling_listener, daemon=True).start()

    # 4. Loop periódico a cada 2 horas (tempo ideal para novos achadinhos)
    while True:
        try:
            run_autoposter()
        except Exception as e:
            print(f"❌ Erro na rodada: {e}", flush=True)

        print("\n⏳ Aguardando 2 horas para a próxima rodada...", flush=True)
        time.sleep(7200)
