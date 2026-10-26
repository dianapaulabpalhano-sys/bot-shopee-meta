import time
import json
import requests
import threading
from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    RENDER_EXTERNAL_URL,
    salvar_produto_enviado,
    salvar_produto_pendente,
    remover_produto_pendente
)
from skills.meta_publisher import (
    publicar_instagram_feed,
    publicar_instagram_story,
    publicar_instagram_reel,
    gerar_video_reels_com_audio
)

def enviar_mensagem_telegram(chat_id: int, texto: str):
    """Envia mensagem de texto formatada em HTML para o Telegram."""
    if not TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": texto, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem Telegram: {e}", flush=True)

def enviar_para_aprovacao_telegram(produto: dict, produtos_pendentes: dict) -> bool:
    """Envia produto para o Telegram com botões interativos e salva no banco de pendentes."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Variáveis do Telegram não configuradas.", flush=True)
        return False

    item_id = str(produto["id"])
    salvar_produto_pendente(item_id, produto, produtos_pendentes)

    url_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "📸 Postar no Feed",       "callback_data": f"feed_{item_id}"},
                {"text": "🌟 Postar no Story",      "callback_data": f"story_{item_id}"}
            ],
            [
                {"text": "🎬 Postar no Reels 🎵",   "callback_data": f"reel_{item_id}"},
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
            print(f"📱 [Telegram Bot] Produto {item_id} enviado para o chat com sucesso!", flush=True)
            return True
        else:
            print(f"⚠️ Erro ao enviar para Telegram ({resp.status_code}): {resp.text}", flush=True)
    except Exception as e:
        print(f"❌ Erro de conexão Telegram: {e}", flush=True)

    return False

def executar_publicacao_reel_bg(produto: dict, chat_id: int, produtos_pendentes: dict, produtos_enviados: set):
    item_id = str(produto["id"])
    nome_prod = produto["title"]
    image_url = produto["image"]
    caption = produto["caption"]

    video_local = gerar_video_reels_com_audio(image_url, item_id)
    if not video_local:
        enviar_mensagem_telegram(chat_id, f"❌ Não foi possível compilar o vídeo para Reels do produto <b>{item_id}</b>.")
        return

    video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
    res = publicar_instagram_reel(video_public_url, caption)

    if res.get("success"):
        msg = (
            f"🎉 <b>REELS COM MÚSICA PUBLICADO COM SUCESSO!</b> 🎬🎵\n\n"
            f"🛍️ <b>{nome_prod}</b>\n"
            f"📸 ID Instagram: <code>{res.get('media_id')}</code>\n\n"
            f"👉 <i>Confira agora na aba Reels do seu perfil @dianapaulab!</i>"
        )
    else:
        msg = f"❌ <b>Erro ao publicar Reels:</b>\n{res.get('error')}"

    enviar_mensagem_telegram(chat_id, msg)
    salvar_produto_enviado(item_id, produtos_enviados)
    remover_produto_pendente(item_id, produtos_pendentes)

def executar_publicacao_todos_bg(produto: dict, chat_id: int, produtos_pendentes: dict, produtos_enviados: set):
    item_id = str(produto["id"])
    nome_prod = produto["title"]
    image_url = produto["image"]
    caption = produto["caption"]

    res_feed = publicar_instagram_feed(image_url, caption)
    time.sleep(2)
    res_story = publicar_instagram_story(image_url)
    time.sleep(2)

    video_local = gerar_video_reels_com_audio(image_url, item_id)
    if video_local:
        video_public_url = f"{RENDER_EXTERNAL_URL}/reels/{item_id}.mp4"
        res_reel = publicar_instagram_reel(video_public_url, caption)
        status_reel = "✅ Reels OK (com música)" if res_reel.get("success") else f"❌ Reels: {res_reel.get('error')}"
    else:
        status_reel = "⚠️ Reels: Vídeo indisponível"

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
    salvar_produto_enviado(item_id, produtos_enviados)
    remover_produto_pendente(item_id, produtos_pendentes)

def processar_acao_telegram(callback_data: str, callback_id: str, chat_id: int, produtos_pendentes: dict, produtos_enviados: set):
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
    produto = produtos_pendentes.get(item_id)

    if acao == "reject":
        print(f"🗑️ [Telegram Bot] Produto {item_id} descartado pela Diana.", flush=True)
        salvar_produto_enviado(item_id, produtos_enviados)
        remover_produto_pendente(item_id, produtos_pendentes)
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
        salvar_produto_enviado(item_id, produtos_enviados)
        remover_produto_pendente(item_id, produtos_pendentes)

    elif acao == "story":
        res = publicar_instagram_story(image_url)
        if res.get("success"):
            msg = f"🌟 <b>PUBLICADO NO STORY COM SUCESSO!</b>\n\n🛍️ <b>{nome_prod}</b>\n📸 ID Instagram: <code>{res.get('media_id')}</code>"
        else:
            msg = f"❌ <b>Erro no Story:</b> {res.get('error')}"
        enviar_mensagem_telegram(chat_id, msg)
        salvar_produto_enviado(item_id, produtos_enviados)
        remover_produto_pendente(item_id, produtos_pendentes)

    elif acao == "reel":
        enviar_mensagem_telegram(
            chat_id,
            f"🎬 <i>Compilando vídeo HD com música e publicando no <b>Reels</b> para: <b>{nome_prod}</b>...\nAguarde instantes!</i>"
        )
        threading.Thread(
            target=executar_publicacao_reel_bg,
            args=(produto, chat_id, produtos_pendentes, produtos_enviados),
            daemon=True
        ).start()

    elif acao == "all":
        enviar_mensagem_telegram(
            chat_id,
            f"🚀 <i>Publicando em todos os formatos (Feed + Story + Reels com música) para: <b>{nome_prod}</b>...</i>"
        )
        threading.Thread(
            target=executar_publicacao_todos_bg,
            args=(produto, chat_id, produtos_pendentes, produtos_enviados),
            daemon=True
        ).start()

def telegram_polling_listener(produtos_pendentes: dict, produtos_enviados: set):
    """Thread contínua de escuta de botões do Telegram com long polling robusto."""
    if not TELEGRAM_BOT_TOKEN:
        return

    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook", timeout=10)
    except Exception:
        pass

    offset = 0
    print("👂 [Telegram Bot] Ouvinte de aprovações ATIVO e pronto!", flush=True)

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
                    processar_acao_telegram(cb_data, cb_id, chat_id, produtos_pendentes, produtos_enviados)

        except Exception:
            time.sleep(3)
