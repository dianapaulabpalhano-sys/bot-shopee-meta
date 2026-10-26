import os
import sys
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Carrega variáveis de ambiente locais (se houver .env)
load_dotenv()

# Força logs imediatos sem buffer (essencial para o Render)
sys.stdout.reconfigure(line_buffering=True)

# =======================================================================
# CREDENCIAIS E CHAVES DE API
# =======================================================================
SHOPEE_APP_KEY       = os.getenv("SHOPEE_APP_KEY", "").strip()
SHOPEE_APP_SECRET    = os.getenv("SHOPEE_APP_SECRET", "").strip()
TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "").strip()
META_USER_TOKEN      = os.getenv("META_USER_TOKEN", "").strip()
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()

# URL pública do Render para servir os vídeos gerados para a Meta API
RENDER_EXTERNAL_URL  = os.getenv("RENDER_EXTERNAL_URL", "https://bot-shopee-meta.onrender.com").rstrip("/")

# =======================================================================
# DIRETÓRIOS E ARQUIVOS DE PERSISTÊNCIA
# =======================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VIDEO_DIR = os.path.join(BASE_DIR, "temp_videos")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(VIDEO_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)

# Trilha sonora padrão para os Reels
AUDIO_PADRAO = os.path.join(ASSETS_DIR, "bg_music.mp3")

# Arquivos de persistência permanente
ARQUIVO_HISTORICO = os.path.join(BASE_DIR, "enviados.json")
ARQUIVO_PENDENTES = os.path.join(BASE_DIR, "pendentes.json")

# =======================================================================
# CONFIGURAÇÃO DE FUSO HORÁRIO E JANELA DE DISPARO (12:00 ÀS 19:00 BRASÍLIA)
# =======================================================================
# O servidor Render roda em UTC. Brasília é UTC-3.
FUSO_BRASILIA = timezone(timedelta(hours=-3))
HORA_INICIO_DISPARO = 12  # 12:00
HORA_FIM_DISPARO    = 19  # 19:00 (não envia após 19:00)

def obter_hora_brasilia() -> datetime:
    """Retorna o datetime atual no fuso horário oficial de Brasília."""
    return datetime.now(FUSO_BRASILIA)

def esta_na_janela_de_envio() -> bool:
    """Verifica se o momento atual está dentro da janela de 12:00 até as 19:00 (Brasília)."""
    agora = obter_hora_brasilia()
    return HORA_INICIO_DISPARO <= agora.hour < HORA_FIM_DISPARO

# =======================================================================
# LOJAS E TERMOS DE BUSCA DE SKINCARE COREANO
# =======================================================================
LOJAS_APROVADAS = ["glory of seoul", "koksara", "jadoo"]

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
# FUNÇÕES DE BANCO DE DADOS EM ARQUIVO (PERSISTÊNCIA)
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

def salvar_produto_enviado(item_id: str, conjunto_memoria: set):
    conjunto_memoria.add(str(item_id))
    try:
        with open(ARQUIVO_HISTORICO, "w", encoding="utf-8") as f:
            json.dump(list(conjunto_memoria), f, ensure_ascii=False, indent=2)
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

def salvar_produto_pendente(item_id: str, produto: dict, dict_memoria: dict):
    dict_memoria[str(item_id)] = produto
    try:
        with open(ARQUIVO_PENDENTES, "w", encoding="utf-8") as f:
            json.dump(dict_memoria, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao salvar {ARQUIVO_PENDENTES}: {e}", flush=True)

def remover_produto_pendente(item_id: str, dict_memoria: dict):
    dict_memoria.pop(str(item_id), None)
    try:
        with open(ARQUIVO_PENDENTES, "w", encoding="utf-8") as f:
            json.dump(dict_memoria, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ Erro ao atualizar {ARQUIVO_PENDENTES}: {e}", flush=True)
