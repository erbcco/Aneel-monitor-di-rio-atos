import asyncio
from playwright.async_api import async_playwright
from datetime import datetime
import json
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PALAVRAS_CHAVE = ["Portaria"]

async def buscar_termo(pagina, termo, data_pesquisa):
    await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada")
    await pagina.fill('input#ctl00_Conteudo_txtPalavraChave', termo)
    await pagina.fill('input#ctl00_Conteudo_txtDataInicio', data_pesquisa)
    await pagina.fill('input#ctl00_Conteudo_txtDataFim', data_pesquisa)
    await pagina.select_option('select#ctl00_Conteudo_ddlCampoPesquisa', label='Todos os campos')
    await pagina.select_option('select#ctl00_Conteudo_ddlTipoPesquisa', label='avancada')
    await pagina.click('input#ctl00_Conteudo_btnPesquisar')
    await pagina.wait_for_selector('table.k-grid-table')
    content = await pagina.content()
    with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
        f.write(content)
    rows = await pagina.query_selector_all('table.k-grid-table tr')
    documentos = []
    for row in rows[1:]:
        cols = await row.query_selector_all("td")
        if len(cols) >= 2:
            titulo = (await cols[1].inner_text()).strip()
            linkElem = await cols[1].query_selector("a")
            url = await linkElem.get_attribute("href") if linkElem else None
            url_completa = f"https://biblioteca.aneel.gov.br{url}" if url else None
            documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})
    logger.info(f"{len(documentos)} documentos encontrados para termo {termo}")
    return documentos

async def main_async():
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
        enviar_email(documentos_totais)
    else:
        logger.info("Nenhum documento encontrado. Não enviar e-mail.")

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("EMAIL_DESTINATARIO")
    if not (remetente and senha and destinatario):
        logger.error("Variáveis de ambiente para email não configuradas.")
        return
    assunto = f"Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    corpo = "Documentos encontrados:\n\n"
    for doc in documentos:
        corpo += f"- {doc['titulo']}: {doc['url']}\n"
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)
        logger.info("Email enviado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao enviar email: {e}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
