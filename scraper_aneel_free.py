import asyncio
import traceback
import time
from playwright.async_api import async_playwright
from datetime import datetime
import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuração de logging (console + arquivo)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")

file_handler = logging.FileHandler("scraper.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(file_handler)

PALAVRAS_CHAVE = ["Portaria"]

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Iniciando busca pelo termo: {termo} - Data: {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Alterna para a aba "Legislação"
        await pagina.wait_for_selector('button:has-text("Legislação"), a:has-text("Legislação")', timeout=10000)
        try:
            await pagina.click('button:has-text("Legislação")')
        except:
            await pagina.click('a:has-text("Legislação")')

        # Salva página inicial para debug
        with open("pagina_debug.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())

        # Preenche campos
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        logger.info("Campos de busca preenchidos com sucesso")

        # Executa pesquisa
        await asyncio.sleep(2)
        await pagina.click('button:has-text("Buscar")')
        await pagina.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        logger.info("Busca executada e página carregada")

        # Verifica resultados
        documentos = []
        try:
            await pagina.wait_for_selector('table', timeout=60000)
        except:
            nome_html = f"pagina_sem_resultados_{termo}_{int(time.time())}.html"
            with open(nome_html, "w", encoding="utf-8") as f:
                f.write(await pagina.content())
            logger.warning(f"Sem tabela de resultados. Página salva: {nome_html}")
            return documentos

        # Extrai resultados
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())

        rows = await pagina.query_selector_all('table tr')
        for i, row in enumerate(rows[1:], 1):
            cols = await row.query_selector_all("td")
            if len(cols) >= 2:
                titulo = (await cols[1].inner_text()).strip()
                link_elem = await cols[1].query_selector("a")
                url = await link_elem.get_attribute("href") if link_elem else None
                url_completa = url if url and url.startswith("http") else f"https://biblioteca.aneel.gov.br{url}" if url else None
                documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})
        logger.info(f"Total de documentos encontrados: {len(documentos)}")
        return documentos

    except Exception as e:
        logger.error(f"Erro ao buscar termo '{termo}': {e}")
        with open(f"erro_{termo}.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())
        return []

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    documentos_totais = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        for termo in PALAVRAS_CHAVE:
            documentos = await buscar_termo(page, termo, data_pesquisa)
            documentos_totais.extend(documentos)

        await browser.close()

    # Salva resultados
    with open("resultados_aneel.json", "w", encoding="utf-8") as f:
        json.dump({
            "data_execucao": datetime.now().isoformat(),
            "total_documentos": len(documentos_totais),
            "documentos": documentos_totais
        }, f, ensure_ascii=False, indent=2)

    if documentos_totais:
        enviar_email(documentos_totais)
    else:
        logger.info("Nenhum documento encontrado, e-mail não será enviado")

def enviar_email(documentos):
    try:
        remetente = os.getenv("GMAIL_USER")
        senha = os.getenv("GMAIL_APP_PASSWORD")
        destinatario = os.getenv("EMAIL_DESTINATARIO")

        if not (remetente and senha and destinatario):
            logger.warning("Variáveis de e-mail não configuradas")
            return

        assunto = f"Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        corpo = f"Foram encontrados {len(documentos)} documentos:\n\n"
        for doc in documentos:
            corpo += f"- {doc['titulo']}: {doc['url']}\n"

        msg = MIMEMultipart()
        msg["From"] = remetente
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "plain"))

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)

        logger.info("E-mail enviado com sucesso!")
    except Exception:
        logger.error("Erro ao enviar e-mail:")
        logger.error(traceback.format_exc())

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
