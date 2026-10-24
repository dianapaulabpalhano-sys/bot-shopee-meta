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

# Garante a biblioteca imageio-ffmpeg instalada dinamicamente se necessário
try:
    import imageio_ffmpeg
except ImportError:
    try:
        print("📦 Instalando dependência imageio-ffmpeg dinamicamente...", flush=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "imageio-ffmpeg"], check=False)
        import imageio_ffmpeg
    except Exception as e:
        print(f"⚠️ Não foi possível instalar imageio-ffmpeg: {e}", flush=True)

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

# Arquivos de persistência permanente (evita perda de dados em reinicializações do Render)
ARQUIVO_HISTORICO = os.path.join(os.getcwd(), "enviados.json")
ARQUIVO_PENDENTES = os.path.join(os.getcwd(), "pendentes.json")

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


# =======================================================================
# PERSISTÊNCIA EM DISCO (HISTÓRICO E PRODUTOS PENDENTES)
# =======================================================================
def carregar_produtos_enviados() -> set:
    if os.path.exists(ARQUIVO_HISTORICO):
        try:
            with open(ARQUIVO_HISTORICO, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return set(str(i) for i in dados)
        except Exception:
            pass
    return set()


def salvar_produto_enviado(item_id: str):
    PRODUTOS_ENVIADOS.add(str(item_id))
    try:
        with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
            json.dump(list(PRODUTOS_ENVIADOS), f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar {ARQUIVO_HISTORICO}: {e}", flush=True)


def carregar_produtos_pendentes() -> dict:
    if os.path.exists(ARQUIVO_PENDENTES):
        try:
            with open(ARQUIVO_PENDENTES, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def salvar_produto_pendente(item_id: str, produto: dict):
    PRODUTOS_PENDENTES[str(item_id)] = produto
    try:
        with open(ARQUIVO_PENDENTES, "w", encoding="utf-8") as f:
            json.dump(PRODUTOS_PENDENTES, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar {ARQUIVO_PENDENTES}: {e}", flush=True)


def remover_produto_pendente(item_id: str):
    PRODUTOS_PENDENTES.pop(str(item_id), None)
    try:
        with open(ARQUIVO_PENDENTES, "w", encoding="utf-8") as f:
            json.dump(PRODUTOS_PENDENTES, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao atualizar {ARQUIVO_PENDENTES}: {e}", flush=True)


PRODUTOS_ENVIADOS = carregar_produtos_enviados()
PRODUTOS_PENDENTES = carregar_produtos_pendentes()
print(f"📋 Banco inicializado: {len(PRODUTOS_ENVIADOS)} no histórico e {len(PRODUTOS_PENDENTES)} pendentes.", flush=True)


# =======================================================================
# 1. MOTOR DE VÍDEO ULTRA RÁPIDO PARA REELS (FFMPEG LEVE)
# =======================================================================
def get_ffmpeg_binary() -> str:
    """Detecta binário FFmpeg no sistema ou via imageio-ffmpeg."""
    ffmpeg_sys = shutil.which("ffmpeg")
    if ffmpeg_sys:
        return ffmpeg_sys
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def gerar_video_reels_da_imagem(image_url: str, item_id: str) -> str:
    """
    Compila vídeo vertical HD (720x1280) ultra leve de 6s compatível com
    os requisitos oficiais do Instagram Reels, consumindo quase zero de RAM.
    """
    output_path = os.path.join(VIDEO_DIR, f"{item_id}.mp4")
    temp_img_path = os.path.join(VIDEO_DIR, f"{item_id}_temp.jpg")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        return output_path

    ffmpeg_bin = get_ffmpeg_binary()
    if not ffmpeg_bin:
        print("❌ FFmpeg não encontrado para gerar vídeo de Reels.", flush=True)
        return None

    try:
        print(f"🎬 Compilando vídeo Reels HD leve para produto {item_id}...", flush=True)
        img_resp = requests.get(image_url, timeout=20)
        with open(temp_img_path, "wb") as f:
            f.write(img_resp.content)

        # 720x1280 (9:16), 6 segundos, preset ultrafast, leve (<400KB)
        cmd = [
            ffmpeg_bin,
            "-y",
            "-loop", "1",
            "-i", temp_img_path,
            "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "stillimage",
            "-t", "6",
            "-r", "25",
            "-pix_fmt", "yuv420p",
            output_path
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"✅ Vídeo Reels compilado com sucesso ({os.path.getsize(output_path)} bytes)!", flush=True)
            return output_path
        else:
            print(f"❌ Erro FFmpeg: {result.stderr.decode('utf-8', errors='ignore')[:300]}", flush=True)
            return None
    except Exception as e:
        print(f"❌ Falha ao compilar vídeo para Reels: {e}", flush=True)
        return None


# =======================================================================
# 2. AUTENTICAÇÃO E BUSCA NA SHOPEE (INFALÍVEL: PÁGINAS 1 E 2)
# =======================================================================
def generate_shopee_signature(app_key: str, secret: str, timestamp: int, payload_str: str) -> str:
    factor = f"{app_key}{timestamp}{payload_str}{secret}"
    return hashlib.sha256(factor.encode("utf-8")).hexdigest()


def buscar_produtos_shopee(keyword: str, page: int = 1, limit: int = 20, sort_type: int = 2):
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
    """Publica vídeo nos REELS do Instagram com compartilhamento no Feed."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"🎬 Solicitando container de Reels à Meta (URL: {video_url})...", flush=True)
    container_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    container_payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": META_USER_TOKEN
    }

    try:
        res = requests.post(container_url, data=container_payload, timeout=35)
        res_data = res.json()
        if "id" not in res_data:
            print(f"❌ Erro container Reels da Meta: {res_data}", flush=True)
            return {"success": False, "error": res_data.get("error", {}).get("message", str(res_data))}

        creation_id = res_data["id"]
        print(f"📦 Container Reels criado: {creation_id}. Monitorando transcodificação...", flush=True)

        status_url = f"https://graph.facebook.com/v19.0/{creation_id}?fields=status_code&access_token={META_USER_TOKEN}"
        pronto = False
        for tentativa in range(20):
            time.sleep(3)
            st_res = requests.get(status_url, timeout=15).json()
            status = st_res.get("status_code")
            print(f"   ⏱️ Status Reels ({tentativa+1}/20): {status}", flush=True)
            if status == "FINISHED":
                pronto = True
                break
            elif status in ["ERROR", "EXPIRED"]:
                return {"success": False, "error": f"Erro de processamento da Meta ({status})"}

        if not pronto:
            return {"success": False, "error": "Tempo limite excedido no processamento do vídeo pela Meta."}

        publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        pub_res = requests.post(publish_url, data={"creation_id": creation_id, "access_token": META_USER_TOKEN}, timeout=30)
        pub_data = pub_res.json()

        if "id" in pub_data:
            media_id = pub_data["id"]
            print(f"🎉 SUCESSO ABSOLUTO! Reel publicado no Instagram. Media ID: {media_id}", flush=True)
            return {"success": True, "media_id": media_id}
        else:
            return {"success": False, "error": pub_data.get("error", {}).get("message", str(pub_data))}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =======================================================================
# 4. EXECUÇÃO EM BACKGROUND PARA NÃO BLOQUEAR TELEGRAM
# =======================================================================
def executar_publicacao_reel_background(produto: dict, chat_id: int):
    item_id = str(produto["id"])
    nome_prod = produto["title"]
    image_url = produto["image"]
    caption = produto["caption"]

    video_local = gerar_video_reels_da_imagem(image_url, item_id)
    if not video_local:
        enviar_mensagem_telegram(chat_id, f"❌ Não foi possível compilar o vídeo para Reels do produto <b>{item_id}</b>.")
        return

    video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
    res = publicar_instagram_reel(video_public_url, caption)

    if res.get("success"):
        msg = (
            f"🎉 <b>REELS PUBLICADO COM SUCESSO NO INSTAGRAM!</b> 🎬✨\n\n"
            f"🛍️ <b>{nome_prod}</b>\n"
            f"📸 ID Instagram: <code>{res.get('media_id')}</code>\n\n"
            f"👉 <i>Confira agora na aba Reels do seu @dianapaulab!</i>"
        )
    else:
        msg = f"❌ <b>Erro ao publicar Reels:</b>\n{res.get('error')}"

    enviar_mensagem_telegram(chat_id, msg)
    salvar_produto_enviado(item_id)
    remover_produto_pendente(item_id)


def executar_publicacao_todos_background(produto: dict, chat_id: int):
    item_id = str(produto["id"])
    nome_prod = produto["title"]
    image_url = produto["image"]
    caption = produto["caption"]

    res_feed = publicar_instagram_feed(image_url, caption)
    time.sleep(2)
    res_story = publicar_instagram_story(image_url)
    time.sleep(2)

    video_local = gerar_video_reels_da_imagem(image_url, item_id)
    if video_local:
        video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
        res_reel = publicar_instagram_reel(video_public_url, caption)
        status_reel = "✅ Reels OK" if res_reel.get("success") else f"❌ Reels: {res_reel.get('error')}"
    else:
        status_reel = "⚠️ Reels: Falha ao compilar vídeo"

    status_feed = "✅ Feed OK" if res_feed.get("success") else f"❌ Feed: {res_feed.get('error')}"
    status_story = "✅ Story OK" if res_story.get("success") else f"❌ Story: {res_story.get('error')}"

    msg = (
        f"🚀 <b>PUBLICAÇÃO COMPLETA CONCLUÍDA!</b>\n\n"
        f"🛍️ <b>{nome_prod}</b>\n"
        f"• {status_feed}\n"
        f"• {status_story}\n"
        f"• {status_reel}"
    )
    enviar_mensagem_telegram(chat_id, msg)
    salvar_produto_enviado(item_id)
    remover_produto_pendente(item_id)


# =======================================================================
# 5. INTERAÇÃO TELEGRAM — BOTÕES COMPLETOS E RESPOSTA ASSÍNCRONA
# =======================================================================
def enviar_para_aprovacao_telegram(produto: dict) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variáveis do Telegram não configuradas.", flush=True)
        return False

    item_id = str(produto["id"])
    salvar_produto_pendente(item_id, produto)

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
            return True
        else:
            print(f"⚠️ Erro ao enviar para Telegram ({resp.status_code}): {resp.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro de conexão Telegram: {e}", flush=True)

    return False


def processar_acao_telegram(callback_data: str, callback_id: str, chat_id: int):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
            json={"callback_query_id": callback_id, "text": "Recebido! Processando postagem..."},
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
        print(f"🗑️ Produto {item_id} descartado pela Diana.", flush=True)
        salvar_produto_enviado(item_id)
        remover_produto_pendente(item_id)
        enviar_mensagem_telegram(chat_id, f"❌ Produto <b>{item_id}</b> descartado. Não voltará a aparecer!")
        return

    if not produto:
        msg = f"⚠️ Produto <b>{item_id}</b> expirou do arquivo temporário ou já foi postado."
        enviar_mensagem_telegram(chat_id, msg)
        return

    image_url = produto["image"]
    caption = produto["caption"]
    nome_prod = produto["title"]

    if acao == "feed":
        res = publicar_instagram_feed(image_url, caption)
        if res.get("success"):
            msg = f"🎉 <b>PUBLICADO NO FEED COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Feed:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)
        salvar_produto_enviado(item_id)
        remover_produto_pendente(item_id)

    elif acao == "story":
        res = publicar_instagram_story(image_url)
        if res.get("success"):
            msg = f"🌟 <b>PUBLICADO NO STORY COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Story:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)
        salvar_produto_enviado(item_id)
        remover_produto_pendente(item_id)

    elif acao == "reel":
        enviar_mensagem_telegram(
            chat_id,
            f"🎬 <i>Compilando vídeo HD e publicando no <b>Reels</b> do Instagram para: <b>{nome_prod}</b>...\nAguarde a confirmação em instantes!</i>"
        )
        threading.Thread(target=executar_publicacao_reel_background, args=(produto, chat_id), daemon=True).start()

    elif acao == "all":
        enviar_mensagem_telegram(
            chat_id,
            f"🚀 <i>Publicando em todos os formatos (Feed + Story + Reels) para: <b>{nome_prod}</b>...</i>"
        )
        threading.Thread(target=executar_publicacao_todos_background, args=(produto, chat_id), daemon=True).start()


def enviar_mensagem_telegram(chat_id: int, texto: str):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem Telegram: {e}", flush=True)


def telegram_polling_listener():
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
# 6. SERVIDOR HTTP (HEALTH CHECK DO RENDER + SERVIR VÍDEOS DE REELS)
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
        html = "✨ <b>Bot Shopee Meta Skincare Coreano (@dianapaulab)</b> ativo e saudável!"
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Servidor HTTP ativo na porta {port} (Render + Reels OK)", flush=True)
    server.serve_forever()


# =======================================================================
# 7. AUTO-PING KEEP-ALIVE (IMPEDE O RENDER FREE DE DORMIR)
# =======================================================================
def keep_alive_ping():
    """Faz requisição periódica a cada 9 minutos para manter o Render acordado."""
    time.sleep(60)
    while True:
        try:
            requests.get(RENDER_EXTERNAL_URL, timeout=15)
            print("🏓 [KEEP-ALIVE] Ping de atividade realizado com sucesso no Render.", flush=True)
        except Exception:
            pass
        time.sleep(540)  # 9 minutos


# =======================================================================
# 8. ROTINA PRINCIPAL DO BOT DE SKINCARE COREANO (GARANTIA DE PRODUTOS)
# =======================================================================
def run_autoposter():
    print("\n🌸 ==============================================", flush=True)
    print("🤖 Buscando achadinhos de Skincare Coreano (Glory of Seoul, Koksara, Jadoo)...", flush=True)

    produtos_encontrados_rodada = 0

    termos_rodada = list(BUSCAS_SKINCARE_BASE)
    random.shuffle(termos_rodada)

    # Páginas seguras (1 e 2) para nunca vir vazio
    pagina = random.choice([1, 2])
    ordenacao = random.choice([2, 5])  # 2=Mais Vendidos, 5=Lançamentos

    for termo in termos_rodada:
        print(f"\n🔍 Buscando na Shopee por: '{termo}' (Pág {pagina})...", flush=True)
        itens = buscar_produtos_shopee(termo, page=pagina, limit=20, sort_type=ordenacao)

        random.shuffle(itens)

        for item in itens:
            item_id = str(item.get("itemId"))
            title = item.get("productName", "")
            img = item.get("imageUrl", "")
            link = item.get("offerLink", "")
            shop = item.get("shopName", "Loja Coreana Oficial")

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
                break

        if produtos_encontrados_rodada >= 2:
            break

    print(f"\n✨ Rodada finalizada. {produtos_encontrados_rodada} produtos enviados para o Telegram.", flush=True)


# =======================================================================
# 9. INICIALIZAÇÃO
# =======================================================================
if __name__ == "__main__":
    print("🚀 AutoPoster Shopee + Meta Graph API iniciando...", flush=True)

    # 1. Valida conexão com Instagram Meta
    verificar_conexao_meta()

    # 2. Inicia servidor HTTP (Render + Reels)
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # 3. Inicia keep-alive interno para não dormir
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    # 4. Inicia ouvinte de cliques do Telegram
    threading.Thread(target=telegram_polling_listener, daemon=True).start()

    # 5. Loop periódico a cada 30 minutos (frequência ideal)
    while True:
        try:
            run_autoposter()
        except Exception as e:
            print(f"❌ Erro na rodada: {e}", flush=True)

        print("\n⏳ Aguardando 30 minutos para a próxima rodada...", flush=True)
        time.sleep(1800)
