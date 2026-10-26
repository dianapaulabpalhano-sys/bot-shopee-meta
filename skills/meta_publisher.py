import os
import time
import requests
import subprocess
import shutil
from config import (
    META_USER_TOKEN,
    INSTAGRAM_ACCOUNT_ID,
    VIDEO_DIR,
    AUDIO_PADRAO
)

def get_ffmpeg_binary() -> str:
    """Detecta o executável do ffmpeg no sistema ou via imageio-ffmpeg."""
    ffmpeg_sys = shutil.which("ffmpeg")
    if ffmpeg_sys:
        return ffmpeg_sys
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def verificar_conexao_meta() -> bool:
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

def gerar_video_reels_com_audio(image_url: str, item_id: str) -> str:
    """
    Baixa a foto oficial do cosmético coreano e compila um vídeo vertical HD (720x1280)
    de 7 segundos JÁ COM ÁUDIO / MÚSICA EMBUTIDA (se disponível em assets/bg_music.mp3).
    Dessa forma, o Reels nasce com som estéreo pronto para tocar no Instagram!
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
        print(f"🎬 [Meta Publisher] Baixando imagem para compilar Reels com som: {item_id}...", flush=True)
        img_resp = requests.get(image_url, timeout=20)
        with open(temp_img_path, "wb") as f:
            f.write(img_resp.content)

        # Verifica se existe trilha sonora embutida
        tem_audio = os.path.exists(AUDIO_PADRAO) and os.path.getsize(AUDIO_PADRAO) > 1000

        if tem_audio:
            print(f"🎵 [Meta Publisher] Embutindo trilha sonora oficial: {AUDIO_PADRAO}", flush=True)
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", temp_img_path,
                "-stream_loop", "-1",
                "-i", AUDIO_PADRAO,
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "128k",
                "-t", "7",
                "-r", "25",
                "-pix_fmt", "yuv420p",
                "-shortest",
                output_path
            ]
        else:
            # Fallback sem arquivo de áudio externo: gera vídeo vertical leve
            cmd = [
                ffmpeg_bin,
                "-y",
                "-loop", "1",
                "-i", temp_img_path,
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-t", "7",
                "-r", "25",
                "-pix_fmt", "yuv420p",
                output_path
            ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
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

def publicar_instagram_feed(image_url: str, caption: str) -> dict:
    """Publica post no Feed do Instagram da Diana (@dianapaulab)."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"📸 [Meta Publisher] Publicando no FEED do Instagram...", flush=True)
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

    print(f"🌟 [Meta Publisher] Publicando nos STORIES do Instagram...", flush=True)
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
    """Publica vídeo com música embutida no REELS do Instagram com compartilhamento no Feed."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"success": False, "error": "Credenciais Meta não configuradas"}

    print(f"🎬 [Meta Publisher] Solicitando container de Reels à Meta (URL: {video_url})...", flush=True)
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
            print(f"🎉 SUCESSO! Reel com música publicado no Instagram. Media ID: {media_id}", flush=True)
            return {"success": True, "media_id": media_id}
        else:
            return {"success": False, "error": pub_data.get("error", {}).get("message", str(pub_data))}
    except Exception as e:
        return {"success": False, "error": str(e)}
