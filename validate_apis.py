import os
import time
import hashlib
import json
import requests
from dotenv import load_dotenv

# Carrega as variáveis configuradas no ficheiro .env
load_dotenv()

META_USER_TOKEN = os.getenv("META_USER_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
SHOPEE_APP_KEY = os.getenv("SHOPEE_APP_KEY")
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET")


def validate_meta():
    print("\n--- 1. TESTANDO META GRAPH API (INSTAGRAM) ---")
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        print("❌ Chaves da Meta ausentes no ficheiro .env!")
        return False

    url = f"https://graph.facebook.com/v19.0/me/accounts?access_token={META_USER_TOKEN}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()

        if response.status_code == 200 and "data" in data:
            if len(data["data"]) > 0:
                page_name = data["data"][0].get("name", "N/A")
                page_id = data["data"][0].get("id", "N/A")
                print(f"✅ Página Facebook Encontrada: {page_name} (ID: {page_id})")
                print(f"🎯 Conta Profissional Instagram: ID {INSTAGRAM_ACCOUNT_ID}")
                return True
            else:
                print("⚠️ Nenhuma página associada encontrada para este token.")
        else:
            error_msg = data.get("error", {}).get("message", response.text)
            print(f"❌ Erro na Meta API: {error_msg}")
            print("⚠️ Revise o token ou as permissões do Meta.")
    except Exception as e:
        print(f"❌ Erro de Conexão na Meta API: {e}")
    return False


def validate_shopee():
    print("\n--- 2. TESTANDO SHOPEE AFFILIATE API ---")
    if not SHOPEE_APP_KEY or not SHOPEE_APP_SECRET:
        print("❌ Chaves da Shopee ausentes no ficheiro .env!")
        return False

    url = "https://open-api.affiliate.shopee.com.br/graphql"
    timestamp = int(time.time())

    # Payload GraphQL básico para testar a comunicação
    payload = json.dumps({"query": "{ shopeeOffers { nodes { itemId title } } }"})

    # Assinatura SHA256 exigida pela Shopee
    factor = f"{SHOPEE_APP_KEY}{timestamp}{payload}{SHOPEE_APP_SECRET}"
    signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_KEY}, Timestamp={timestamp}, Signature={signature}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    session = requests.Session()
    try:
        response = session.post(url, data=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            print("✅ Shopee Affiliate API Conectada com Sucesso!")
            return True
        else:
            print(f"⚠️ Resposta da Shopee (Status {response.status_code}): {response.text[:150]}")
    except Exception as e:
        print(f"❌ Erro ao conectar com a Shopee API: {e}")
    return False


if __name__ == "__main__":
    print("🚀 Iniciando Validação de Integrações...")
    meta_ok = validate_meta()
    shopee_ok = validate_shopee()

    print("\n--------------------------------------------------")
    if meta_ok and shopee_ok:
        print("🎉 Validação concluída! Todas as APIs estão ativas e conectadas.")
    else:
        print("⚠️ Validação concluída com avisos. Verifique os erros acima.")