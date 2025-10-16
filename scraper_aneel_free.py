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
import re
from html import unescape
from bs4 import BeautifulSoup

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")
file_handler = logging.FileHandler("scraper.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(file_handler)

PALAVRAS_CHAVE = ["Portaria"]

async def buscar_termo(page, termo, data_pesquisa):
    logger.info(f"Busca: {termo} | Data: {data_pesquisa}")
    await page.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
    await page.wait_for_selector('input[name="LegislacaoPalavraChave"]')

    await page.fill('input[name="LegislacaoPalavraChave"]', termo)
    await page.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
    await page.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
    logger.info("Campos preenchidos")

    # Clica em Buscar e espera pela lista de resultados
    await page.click('button:has-text("Buscar")')
    await page.wait_for_selector('div.ficha-acervo-detalhe', timeout=20000)
    await page.wait_for_timeout(2000)

    content = await page.content()
    with open("resultado_Portaria.html", "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Resultado salvo em resultado_Portaria.html")

    return content

def extrair_documentos(content, data_busca):
    logger.info("Extraindo documentos")
    soup = BeautifulSoup(content, 'html.parser')
    fichas = soup.select('div.ficha-acervo-detalhe')
    documentos = []

    logger.info(f"Total de fichas encontradas: {len(fichas)}")
    for idx, ficha in enumerate(fichas, 1):
        doc = {}
        titulo = ficha.select_one('p.titulo')
        if titulo: doc['titulo'] = titulo.get_text(strip=True)
        assin = ficha.select_one('p.assinatura')
        if assin:
            m = re.search(r'(\d{2}/\d{2}/\d{4})', assin.get_text())
            if m: doc['data_assinatura'] = m.group(1)
        pub = ficha.select_one('p.publicacao')
        if pub:
            m = re.search(r'(\d{2}/\d{2}/\d{4})', pub.get_text())
            if m: doc['data_publicacao'] = m.group(1)
        ement = ficha.select_one('div.texto-html-container')
        if ement: doc['ementa'] = re.sub(r'\s+', ' ', ement.get_text(strip=True))
        assunto = ficha.select_one('p.assunto')
        if assunto: doc['assunto'] = assunto.get_text(strip=True).replace('Assunto','').strip()
        for link_p in ficha.select('p.sites'):
            rotulo = link_p.select_one('span.rotulo')
            a = link_p.select_one('a')
            if rotulo and a:
                text = rotulo.get_text(strip=True)
                href = a['href']
                if 'Texto Integral' in text: doc['link_texto_integral'] = href
                if 'Nota Técnica' in text or 'Voto' in text: doc['link_nota_tecnica'] = href
        doc['data_busca'] = data_busca
        if 'link_texto_integral' in doc:
            documentos.append(doc)
            logger.info(f"Documento {idx} extraído")
    return documentos

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    dest = os.getenv("EMAIL_DESTINATARIO")
    logger.info(f"Enviando e-mail de {remetente} para {dest}")
    if not remetente or not senha or not dest:
        logger.error("Credenciais ausentes")
        return
    assunto = f"📋 ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} doc"
    corpo = f"Total: {len(documentos)}\n\n"
    for i, d in enumerate(documentos,1):
        corpo += f"{i}. {d.get('titulo','')} - {d.get('link_texto_integral','')}\n"
    msg = MIMEMultipart(); msg["From"]=remetente; msg["To"]=dest; msg["Subject"]=assunto
    msg.attach(MIMEText(corpo,"plain","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587) as s:
            s.starttls(); s.login(remetente,senha); s.send_message(msg)
        logger.info("E-mail enviado com sucesso!")
    except Exception as e:
        logger.error(f"Falha no envio: {e}")

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    content = None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        content = await buscar_termo(page, "Portaria", data_pesquisa)
        await browser.close()
    docs = extrair_documentos(content, data_pesquisa)
    with open("resultados_aneel.json","w",encoding="utf-8") as f:
        json.dump({"data_exec":datetime.now().isoformat(),"total":len(docs),"docs":docs},f,ensure_ascii=False,indent=2)
    if docs: enviar_email(docs)

def main():
    asyncio.run(main_async())

if __name__=="__main__":
    main()
