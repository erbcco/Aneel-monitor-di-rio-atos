import asyncio
import traceback
from playwright.async_api import async_playwright
from datetime import datetime
import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

PALAVRAS_CHAVE = ["Portaria"]

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Buscando termo: {termo} para data {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Salve o HTML imediatamente após o goto!
        content = await pagina.content()
        with open("pagina_debug.html", "w", encoding="utf-8") as f:
            f.write(content)

        # COMENTE as linhas abaixo para garantir que o arquivo é salvo mesmo se não encontrar o campo
        # await pagina.wait_for_selector('input[name="ctl00$Conteudo$txtPalavraChave"]', timeout=60000)
        # await pagina.fill('input[name="ctl00$Conteudo$txtPalavraChave"]', termo)
        # await pagina.fill('input[name="ctl00$Conteudo$txtDataInicio"]', data_pesquisa)
        # await pagina.fill('input[name="ctl00$Conteudo$txtDataFim"]', data_pesquisa)
        # await pagina.select_option('select[name="ctl00$Conteudo$ddlCampoPesquisa"]', label='Todos os campos')
        # await pagina.select_option('select[name="ctl00$Conteudo$ddlTipoPesquisa"]', label='avancada')
        # await pagina.click('input#ctl00_Conteudo_btnPesquisar')
        # await pagina.wait_for_selector('table.k-grid-table')
        # content = await pagina.content()
        # with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
        #     f.write(content)

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
            enviar_email(documentos_totais)
        else:
            logger.info("Nenhum documento encontrado, email não será enviado.")
    except Exception:
        logger.error("Erro crítico no scraper:\n" + traceback.format_exc())
        raise

def enviar_email(documentos):
    try:
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
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)
        logger.info("Email enviado com sucesso.")
    except Exception:
        logger.error("Erro ao enviar email:\n" + traceback.format_exc())

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
