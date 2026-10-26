import os
import sys
import time
import threading
from urllib.parse import urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# Importa as configurações do sistema
from config import (
    RENDER_EXTERNAL_URL,
    VIDEO_DIR,
    obter_hora_brasilia,
    esta_na_janela_de_envio,
    carregar_produtos_enviados,
    carregar_produtos_pendentes,
    HORA_INICIO_DISPARO,
    HORA_FIM_DISPARO
)

# Importa as habilidades (Skills) modulares do projeto
from skills.shopee_extractor import extrair_achadinho_rodada
from skills.meta_publisher import verificar_conexao_meta
from skills.telegram_bot import (
    enviar_para_aprovacao_telegram,
    telegram_polling_listener
)

# Inicializa os conjuntos em memória com base nos arquivos persistentes
PRODUTOS_ENVIADOS = carregar_produtos_enviados()
PRODUTOS_PENDENTES = carregar_produtos_pendentes()


# =======================================================================
# SERVIDOR HTTP (RENDER HEALTH CHECK + SERVIR VÍDEOS DE REELS)
# =======================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        # Rota para a Meta Graph API baixar o MP4 com música para o Reels
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

        # Rota padrão de Health Check do Render
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        hora_bsb = obter_hora_brasilia().strftime("%H:%M:%S")
        html = (
            f"✨ <b>Bot Shopee Meta Skincare Coreano (@dianapaulab)</b> ativo!<br>"
            f"Horário de Brasília: {hora_bsb} | Janela de envios: {HORA_INICIO_DISPARO}:00 às {HORA_FIM_DISPARO}:00"
        )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_dummy_server():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🌐 Servidor HTTP ativo na porta {port} (Render + Reels OK)", flush=True)
    server.serve_forever()


# =======================================================================
# AUTO-PING KEEP-ALIVE (IMPEDE O RENDER DE DORMIR DURANTE O DIA)
# =======================================================================
def keep_alive_ping():
    """Faz um ping periódico a cada 9 minutos na URL pública."""
    time.sleep(60)
    while True:
        try:
            requests.get(RENDER_EXTERNAL_URL, timeout=15)
            print("🏓 [Keep-Alive] Ping de atividade realizado no Render.", flush=True)
        except Exception:
            pass
        time.sleep(540)  # 9 minutos


# =======================================================================
# ROTINA PRINCIPAL DO AUTOR (COM JANELA 12:00 ÀS 19:00 BRASÍLIA)
# =======================================================================
def run_autoposter():
    agora_bsb = obter_hora_brasilia()
    hora_atual = agora_bsb.hour
    hora_str = agora_bsb.strftime("%H:%M")

    # Verificação estrita da janela de horário solicitada pela Diana
    if not esta_na_janela_de_envio():
        print(
            f"⏰ [FORA DO HORÁRIO] Hora atual em Brasília: {hora_str}. "
            f"Envios permitidos apenas entre {HORA_INICIO_DISPARO}:00 e {HORA_FIM_DISPARO}:00. "
            f"Pulando rodada...",
            flush=True
        )
        return

    print("\n🌸 ============================================================", flush=True)
    print(f"🤖 [AutoPoster] Horário de Brasília: {hora_str}. Buscando achadinhos (Glory of Seoul, Koksara, Jadoo)...", flush=True)

    produtos_enviados_rodada = 0

    # Busca até 2 achadinhos qualificados por rodada
    for _ in range(2):
        produto = extrair_achadinho_rodada(PRODUTOS_ENVIADOS)
        if produto:
            print(f"📦 [SELECIONADO] {produto['title']} ({produto['shop']})", flush=True)
            sucesso = enviar_para_aprovacao_telegram(produto, PRODUTOS_PENDENTES)
            if sucesso:
                produtos_enviados_rodada += 1
                time.sleep(2)

    print(f"✨ Rodada finalizada. {produtos_enviados_rodada} novos produtos enviados para o Telegram.", flush=True)


# =======================================================================
# INICIALIZAÇÃO
# =======================================================================
if __name__ == "__main__":
    print("🚀 AutoPoster Shopee + Meta Graph API (Reels com Som + Skills Modulares) iniciando...", flush=True)

    # 1. Valida conexão com Instagram Meta
    verificar_conexao_meta()

    # 2. Inicia servidor HTTP (porta do Render + servidor de vídeos de Reels)
    threading.Thread(target=start_dummy_server, daemon=True).start()

    # 3. Inicia keep-alive interno anti-hibernação
    threading.Thread(target=keep_alive_ping, daemon=True).start()

    # 4. Inicia ouvinte de cliques e botões do Telegram
    threading.Thread(
        target=telegram_polling_listener,
        args=(PRODUTOS_PENDENTES, PRODUTOS_ENVIADOS),
        daemon=True
    ).start()

    # 5. Loop de orquestração: checa a cada 30 minutos a 1 hora
    # Aproveita a janela de 12:00 até 19:00 rodando nos horários-chave
    while True:
        try:
            run_autoposter()
        except Exception as e:
            print(f"❌ Erro na rodada: {e}", flush=True)

        print("\n⏳ Aguardando 1 hora para a próxima verificação...", flush=True)
        time.sleep(3600)  # Checa a cada 1 hora
