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

        # Salve sempre o HTML após o goto!
        content = await pagina.content()
        with open("pagina_debug.html", "w", encoding="utf-8") as f:
            f.write(content)

        await pagina.wait_for_selector('input[name="TextoBuscaBooleana1"]', timeout=60000)
        await pagina.fill('input[name="TextoBuscaBooleana1"]', termo)

        # Não tente selecionar "Entre" até saber o nome do campo.
        # await pagina.select_option(...)

        # Não tente preencher a data até saber o nome dos campos.
        # await pagina.fill(...)

        # Não tente clicar ainda.
        # await pagina.click(...)

        documentos = []
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
        if documentos_totais:
            logger.info("Documentos encontrados.")
        else:
            logger.info("Nenhum documento encontrado.")
    except Exception:
        logger.error("Erro crítico no scraper:\n" + traceback.format_exc())
        raise

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
