import asyncio
from playwright.async_api import async_playwright

async def buscar_termo(pagina):
    await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
    # Salve HTML imediatamente após o goto
    content = await pagina.content()
    with open("pagina_debug_goto.html", "w", encoding="utf-8") as f:
        f.write(content)

    # Tente clicar na aba Legislação usando todos os possíveis formatos
    erro = None
    try:
        await pagina.wait_for_selector('button:has-text("Legislação")', timeout=5000)
        await pagina.click('button:has-text("Legislação")')
    except Exception as e:
        erro = e
        try:
            await pagina.click('a:has-text("Legislação")')
        except Exception as e2:
            erro = e2
            try:
                await pagina.click('.btn:has-text("Legislação")')
            except Exception as e3:
                erro = e3
    # Salve HTML após tentativas de clique
    content = await pagina.content()
    with open("pagina_debug_legislacao.html", "w", encoding="utf-8") as f:
        f.write(content)
    print("Erro ao clicar na Legislação:", erro)

async def main_async():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await buscar_termo(page)
        await browser.close()

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
