"""
🔬 DIAGNÓSTICO LOCAL — Shopee Affiliate Open API
================================================
Execute este script no seu computador (não no Render) com o seu .env real.
Ele testa 3 variações da query para descobrir qual o formato exato que a API aceita.

Uso:
  1. Coloque suas credenciais reais em .env (na pasta bot-shopee-meta)
  2. pip install requests python-dotenv
  3. python diagnose_shopee.py
"""

import hashlib
import json
import time
import requests
import os
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("SHOPEE_APP_KEY", "").strip()
SECRET  = os.getenv("SHOPEE_APP_SECRET", "").strip()
URL     = "https://open-api.affiliate.shopee.com.br/graphql"

print("=" * 60)
print(f"🔑 App ID  : {APP_ID}")
print(f"🔒 Secret  : {SECRET[:4]}{'*' * (len(SECRET)-4)} ({len(SECRET)} chars)")
print("=" * 60)

if not APP_ID or not SECRET:
    print("❌ ERRO: SHOPEE_APP_KEY ou SHOPEE_APP_SECRET não encontrados no .env!")
    exit(1)


def fazer_request(label: str, payload_str: str):
    """Testa um payload específico e imprime o resultado completo."""
    timestamp = int(time.time())
    factor    = f"{APP_ID}{timestamp}{payload_str}{SECRET}"
    signature = hashlib.sha256(factor.encode("utf-8")).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={APP_ID},Timestamp={timestamp},Signature={signature}",
    }

    print(f"\n{'─'*60}")
    print(f"🧪 TESTE: {label}")
    print(f"📦 Payload ({len(payload_str)} chars): {payload_str[:120]}...")
    print(f"🔑 Signature: {signature}")
    print(f"📋 Auth Header: SHA256 Credential={APP_ID},Timestamp={timestamp},Signature={signature[:20]}...")

    try:
        resp = requests.post(URL, data=payload_str, headers=headers, timeout=15)
        print(f"📡 HTTP Status: {resp.status_code}")
        try:
            rj = resp.json()
            print(f"📨 Resposta JSON: {json.dumps(rj, indent=2, ensure_ascii=False)[:500]}")
        except Exception:
            print(f"📨 Resposta texto: {resp.text[:500]}")
    except Exception as e:
        print(f"❌ Erro de conexão: {e}")


# ─── TESTE 1: Query com keyword (formato atual do bot) ───────────────────────
q1_body = {"query": '{ productOfferV2(keyword: "skincare", limit: 1) { nodes { itemId productName imageUrl offerLink } } }'}
fazer_request("Query keyword inline (formato atual)", json.dumps(q1_body, separators=(",", ":")))

# ─── TESTE 2: Query com listType e page (sem keyword) ────────────────────────
q2_body = {"query": "{ productOfferV2(listType: 0, sortType: 2, page: 0, limit: 1) { nodes { itemId productName imageUrl offerLink } } }"}
fazer_request("Query listType sem keyword", json.dumps(q2_body, separators=(",", ":")))

# ─── TESTE 3: Format documentação oficial (com variáveis) ────────────────────
q3_data = {
    "query": "query Fetch($page: Int) { productOfferV2(listType: 0, sortType: 2, page: $page, limit: 1) { nodes { commissionRate commission price productLink offerLink } } }",
    "variables": {"page": 0}
}
fazer_request("Query com variables (doc oficial)", json.dumps(q3_data, separators=(",", ":")))

# ─── TESTE 4: Payload como string literal (sem json.dumps) ───────────────────
q4_raw = '{"query":"{ productOfferV2(listType: 0, page: 0, limit: 1) { nodes { itemId productName offerLink } } }"}'
fazer_request("Payload raw string (sem json.dumps)", q4_raw)

print(f"\n{'='*60}")
print("🏁 Diagnóstico concluído!")
print("Se TODOS os 4 testes retornarem 10020, o problema é nas CREDENCIAIS.")
print("Verifique em: https://affiliate.shopee.com.br/open_api")
print("  → O status do seu App deve ser 'Aprovado' / 'Ativo'")
print("  → Copie o App ID e Secret Key EXATAMENTE do painel")
print("=" * 60)
