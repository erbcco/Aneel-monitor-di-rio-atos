import asyncio
import traceback
from playwright.async_api import async_playwright
from datetime import datetime
import json

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Salve debug da tela inicial (Acervo)
        content = await pagina.content()
        with open("pagina_debug_inicial.html", "w", encoding="utf-8") as f:
            f.write(content)

        # Clique na aba Legislação
        await pagina.wait_for_selector('button:has-text("Legislação")', timeout=10000)
        await pagina.click('button:has-text("Legislação")')

        # Salve debug após Legislação estar ativa
        content = await pagina.content()
        with open("pagina_debug_legislacao.html", "w", encoding="utf-8") as f:
            f.write(content)

        # Preencha campos SÓ após Legislação estar ativa
        await pagina.wait_for_selector('input[name="LegislacaoPalavraChave"]', timeout=60000)
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)

        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Entre')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        await pagina.fill('input[name="LegislacaoDataPublicacao2"]', data_pesquisa)

        # Clique em Buscar
        await pagina.click('button:has-text("Buscar")', timeout=60000)

        await pagina.wait_for_selector('table', timeout=60000)
        content = await pagina.content()
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(content)

        # Continue processamento conforme resultado exibido
    except Exception:
        with open("pagina_debug_error.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())
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
