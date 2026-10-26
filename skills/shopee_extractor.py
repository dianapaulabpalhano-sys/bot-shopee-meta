import time
import json
import hashlib
import requests
import random
from config import (
    SHOPEE_APP_KEY,
    SHOPEE_APP_SECRET,
    LOJAS_APROVADAS,
    BUSCAS_SKINCARE_BASE
)

def generate_shopee_signature(app_key: str, secret: str, timestamp: int, payload_str: str) -> str:
    """Gera a assinatura oficial SHA-256 (AppId + Timestamp + Payload + Secret)."""
    factor = f"{app_key}{timestamp}{payload_str}{secret}"
    return hashlib.sha256(factor.encode("utf-8")).hexdigest()

def buscar_produtos_shopee(keyword: str, page: int = 1, limit: int = 20, sort_type: int = 2) -> list:
    """
    Busca produtos na API GraphQL da Shopee Affiliate.
    Usa páginas seguras (1 e 2) e ordenações rotativas para sempre trazer novidades.
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
    """Valida se o produto pertence a Glory of Seoul, Koksara ou Jadoo."""
    shop_name = (item.get("shopName") or "").lower()
    product_name = (item.get("productName") or "").lower()
    termo = termo_busca.lower()

    for loja in LOJAS_APROVADAS:
        if loja in shop_name or loja in product_name or loja in termo:
            return True
    return False

def extrair_achadinho_rodada(produtos_enviados: set) -> dict:
    """
    Percorre termos aleatórios de Skincare Coreano e retorna um produto
    100% elegível que ainda não foi enviado anteriormente.
    """
    termos_rodada = list(BUSCAS_SKINCARE_BASE)
    random.shuffle(termos_rodada)

    # Páginas seguras para evitar resultados vazios
    pagina = random.choice([1, 2])
    ordenacao = random.choice([2, 5])  # 2=Mais Vendidos, 5=Lançamentos

    for termo in termos_rodada:
        print(f"🔍 [Shopee Extractor] Buscando por: '{termo}' (Pág {pagina})...", flush=True)
        itens = buscar_produtos_shopee(termo, page=pagina, limit=20, sort_type=ordenacao)
        random.shuffle(itens)

        for item in itens:
            item_id = str(item.get("itemId"))
            title = item.get("productName", "")
            img = item.get("imageUrl", "")
            link = item.get("offerLink", "")
            shop = item.get("shopName", "Loja Coreana Oficial")

            if not item_id or not title or not img or not link:
                continue

            if item_id in produtos_enviados:
                continue

            if not produto_pertence_lojas_alvo(item, termo):
                continue

            # Legenda de alta conversão para o Instagram @dianapaulab
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

            return {
                "id": item_id,
                "title": title,
                "image": img,
                "link": link,
                "shop": shop,
                "caption": caption
            }

    return None
