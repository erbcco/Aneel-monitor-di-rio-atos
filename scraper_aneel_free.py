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

async def salvar_debug(pagina, nome_arquivo):
    try:
        content = await pagina.content()
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"Debug salvo: {nome_arquivo}")
    except Exception as e:
        logger.error(f"Erro ao salvar debug {nome_arquivo}: {e}")

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Buscando termo: {termo} para data {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Salvar debug logo após goto
        await salvar_debug(pagina, "pagina_debug_goto.html")

        # Tentativa robusta para clicar na aba Legislação
        try:
            await pagina.wait_for_selector('button:has-text("Legislação"), a:has-text("Legislação"), .btn:has-text("Legislação")', timeout=10000)
            try:
                await pagina.click('button:has-text("Legislação")')
            except:
                try:
                    await pagina.click('a:has-text("Legislação")')
                except:
                    await pagina.click('.btn:has-text("Legislação")')
        except Exception as e:
            logger.error(f"Falha ao tentar clicar na aba Legislação: {e}")

        # Salvar debug após tentar clicar em Legislação
        await salvar_debug(pagina, "pagina_debug_legislacao.html")

        # Agora aguarde os campos da aba Legislação
        await pagina.wait_for_selector('input[name="LegislacaoPalavraChave"]', timeout=60000)
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Entre')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        await pagina.fill('input[name="LegislacaoDataPublicacao2"]', data_pesquisa)

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

    except Exception as e:
        logger.error("Erro ao buscar termo:\n" + traceback.format_exc())
        # Salve debug em caso de erro
        await salvar_debug(pagina, "pagina_debug_error.html")
        raise

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await buscar_termo(page, "Portaria", data_pesquisa)
        await browser.close()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
