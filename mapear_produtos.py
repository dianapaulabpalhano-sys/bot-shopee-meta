from curl_cffi import requests
from bs4 import BeautifulSoup
import json

def mapear_glory_of_seoul():
    shop_id = 920292999
    # URL pública do catálogo da loja
    url = f"https://shopee.com.br/shop/{shop_id}/search"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Referer": "https://shopee.com.br/"
    }

    try:
        # Usa o curl_cffi para passar pela proteção do Cloudflare
        response = requests.get(url, headers=headers, impersonate="chrome120")
        
        if response.status_code != 200:
            print(f"❌ Erro na requisição: Status {response.status_code}")
            return []

        # Usamos a API do endpoint de busca para garantir a extração dos dados
        api_url = f"https://shopee.com.br/api/v4/shop/get_shop_base?shopid={shop_id}"
        resp_api = requests.get(api_url, headers=headers, impersonate="chrome120")
        
        # Teste de endpoint direto
        search_url = f"https://shopee.com.br/api/v4/search/search_items?by=pop&limit=30&match_id={shop_id}&newest=0&order=desc&page_type=shop&scenario=PAGE_SHOP_SEARCH&version=2"
        res = requests.get(search_url, headers=headers, impersonate="chrome120")
        
        data = res.json()
        items = data.get("items", [])
        
        produtos_sem_video = []

        for item in items:
            item_data = item.get("item_basic", {})
            if not item_data:
                continue
                
            nome = item_data.get("name")
            item_id = item_data.get("itemid")
            preco = item_data.get("price", 0) / 100000
            
            # Verifica se o produto tem vídeo cadastrado
            video_info = item_data.get("video_info_list")

            if not video_info:  # Sem vídeo no anúncio
                link_produto = f"https://shopee.com.br/product/{shop_id}/{item_id}"
                produtos_sem_video.append({
                    "nome": nome,
                    "preco": preco,
                    "item_id": item_id,
                    "link": link_produto
                })

        return produtos_sem_video

    except Exception as e:
        print(f"❌ Erro ao rodar a busca: {e}")
        return []

if __name__ == "__main__":
    print("🔎 Mapeando produtos da Glory of Seoul via curl_cffi...\n")
    lista_produtos = mapear_glory_of_seoul()

    print(f"==================================================")
    print(f"🎯 ENCONTRADOS: {len(lista_produtos)} produtos sem vídeo oficial")
    print(f"==================================================\n")

    for idx, p in enumerate(lista_produtos, 1):
        print(f"{idx}. {p['nome']}")
        print(f"   💰 Preço: R$ {p['preco']:.2f}")
        print(f"   🔗 Link: {p['link']}\n")