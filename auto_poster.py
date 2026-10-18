import os
import time
import hashlib
import json
import requests
from dotenv import load_dotenv

load_dotenv()

# Configurações de Ambiente
META_USER_TOKEN = os.getenv("META_USER_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
SHOPEE_APP_KEY = os.getenv("SHOPEE_APP_KEY")
SHOPEE_APP_SECRET = os.getenv("SHOPEE_APP_SECRET")

# Definição dos Nichos e Palavras-chave de Busca
NICHES = {
    "skincare": ["sérum facial", "protetor solar", "creme hidratante", "skincare"],
    "feminino": ["bolsa feminina", "maquiagem", "vestido", "acessórios femininos"],
    "casa": ["organizador de casa", "decoração", "cozinha prática", "luminária led"]
}

def get_shopee_products(keyword, limit=5):
    """Busca produtos na API de Afiliados da Shopee baseados em palavra-chave."""
    url = "https://open-api.affiliate.shopee.com.br/graphql"
    timestamp = int(time.time())

    query = """
    query {
        shopeeOffers(keyword: "%s", limit: %d) {
            nodes {
                itemId
                title
                imageUrl
                offerLink
                price
                commissionRate
            }
        }
    }
    """ % (keyword, limit)

    payload = json.dumps({"query": query})
    factor = f"{SHOPEE_APP_KEY}{timestamp}{payload}{SHOPEE_APP_SECRET}"
    signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={SHOPEE_APP_KEY}, Timestamp={timestamp}, Signature={signature}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("data", {}).get("shopeeOffers", {}).get("nodes", [])
            return nodes
        else:
            print(f"⚠️ Erro ao consultar Shopee para '{keyword}': Status {response.status_code}")
    except Exception as e:
        print(f"❌ Exceção ao buscar na Shopee: {e}")
    return []

def post_to_instagram(image_url, caption):
    """Publica uma imagem com legenda no Instagram via Graph API."""
    if not META_USER_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        print("❌ Credenciais do Meta não encontradas.")
        return False

    # 1. Criar Container de Mídia
    container_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media"
    payload_container = {
        "image_url": image_url,
        "caption": caption,
        "access_token": META_USER_TOKEN
    }
    
    res_container = requests.post(container_url, data=payload_container)
    if res_container.status_code != 200:
        print(f"❌ Erro ao criar container de imagem no IG: {res_container.text}")
        return False

    creation_id = res_container.json().get("id")

    # 2. Publicar Container
    publish_url = f"https://graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    payload_publish = {
        "creation_id": creation_id,
        "access_token": META_USER_TOKEN
    }

    res_publish = requests.post(publish_url, data=payload_publish)
    if res_publish.status_code == 200:
        print("🚀 Post publicado no Instagram com sucesso!")
        return True
    else:
        print(f"❌ Erro ao publicar no IG: {res_publish.text}")
        return False

def run_autoposter():
    print("🤖 Iniciando Rotina do AutoPoster...")
    for niche_name, keywords in NICHES.items():
        print(f"\n🔍 Processando Nicho: {niche_name.upper()}")
        for kw in keywords:
            products = get_shopee_products(kw, limit=1)
            if products:
                prod = products[0]
                title = prod.get("title", "Achadinho Shopee")
                link = prod.get("offerLink", "")
                img = prod.get("imageUrl", "")

                caption = f"✨ {title}\n\n🛍️ Confira e garanta o seu pelo link na bio!\n🔗 Link: {link}\n\n#{niche_name} #achadinhos #shopee #promoção"
                
                print(f"📌 Encontrado: {title}")
                print(f"🖼️ Imagem: {img}")
                # Exemplo de chamada para postagem (Descomente quando quiser enviar ao vivo):
                # post_to_instagram(img, caption)
                break

if __name__ == "__main__":
    run_autoposter()