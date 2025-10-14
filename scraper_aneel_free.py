import asyncio
import traceback
from playwright.async_api import async_playwright
from datetime import datetime
import json
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

PALAVRAS_CHAVE = ["Portaria"]

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Buscando termo: {termo} para data {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Clique na aba 'Legislação' se ela não estiver ativa
        await pagina.wait_for_selector('button:has-text("Legislação")', timeout=10000)
        await pagina.click('button:has-text("Legislação")')

        # Aguarde o campo correto aparecer na aba de legislação
        await pagina.wait_for_selector('input[name="LegislacaoPalavraChave"]', timeout=60000)
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)

        # Público alvo: selecionar "Entre" no filtro de publicação e preencher datas
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Entre')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        await pagina.fill('input[name="LegislacaoDataPublicacao2"]', data_pesquisa)

        # Clique no botão Buscar correto da aba Legislação
        await pagina.click('button:has-text("Buscar")', timeout=60000)

        await pagina.wait_for_selector('table', timeout=60000)
        content = await pagina.content()
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(content)

        rows = await pagina.query_selector_all('table tr')
        documentos = []
        for row in rows[1:]:
            cols = await row.query_selector_all("td")
            if len(cols) >= 2:
                titulo = (await cols[1].inner_text()).strip()
                linkElem = await cols[1].query_selector("a")
                url = await linkElem.get_attribute("href") if linkElem else None
                url_completa = url if url and url.startswith("http") else f"https://biblioteca.aneel.gov.br{url}" if url else None
                documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})
        logger.info(f"{len(documentos)} documentos encontrados para termo {termo}")
        return documentos
    except Exception:
        logger.error("Erro ao buscar termo:\n" + traceback.format_exc())
        raise

async def main_async():
    try:
        data_pesquisa = datetime.now().strftime("%d/%m/%Y")
        documentos_totais = []
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()
            for termo in PALAVRAS_CHAVE:
                documentos = await buscar_termo(page, termo, data_pesquisa)
                documentos_totais.extend(documentos)
            await browser.close()
        with open("resultados_aneel.json", "w", encoding="utf-8") as f:
            json.dump({
                "data_execucao": datetime.now().isoformat(),
                "documentos": documentos_totais
            }, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.error("Erro crítico no scraper:\n" + traceback.format_exc())
        raise

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
