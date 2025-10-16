import asyncio
import traceback
import json
import os
import smtplib
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")
fh = logging.FileHandler("scraper.log", encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(fh)

PALAVRA = "Portaria"

async def buscar_portarias(data_pesquisa):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        logger.info(f"Buscando {PALAVRA} em {data_pesquisa}")
        await page.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
        await page.fill('input[name="LegislacaoPalavraChave"]', PALAVRA)
        await page.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label="Igual a")
        await page.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        logger.info("Campos preenchidos")
        await page.click('button:has-text("Buscar")')
        await page.wait_for_selector('div.ficha-acervo-detalhe', timeout=20000)
        await page.wait_for_timeout(2000)
        content = await page.content()
        with open("resultado_Portaria.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("HTML de resultados salvo")
        await browser.close()
        return content

def extrair_documentos(html, data_busca):
    logger.info("Extraindo documentos")
    soup = BeautifulSoup(html, "html.parser")
    fichas = soup.select("div.ficha-acervo-detalhe")
    logger.info(f"{len(fichas)} registros encontrados")
    docs = []
    for idx, f in enumerate(fichas, 1):
        doc = {}
        t = f.select_one("p.titulo")
        if t: doc["titulo"] = t.get_text(strip=True)
        a = f.select_one("p.assinatura")
        if a:
            m = re.search(r"\d{2}/\d{2}/\d{4}", a.get_text())
            if m: doc["data_assinatura"] = m.group(0)
        p = f.select_one("p.publicacao")
        if p:
            m = re.search(r"\d{2}/\d{2}/\d{4}", p.get_text())
            if m: doc["data_publicacao"] = m.group(0)
        e = f.select_one("div.texto-html-container")
        if e: doc["ementa"] = e.get_text(strip=True)
        s = f.select_one("p.assunto")
        if s: doc["assunto"] = s.get_text(strip=True).replace("Assunto","").strip()
        for sp in f.select("p.sites"):
            rot = sp.select_one("span.rotulo")
            a2 = sp.select_one("a")
            if rot and a2:
                txt = rot.get_text(strip=True)
                href = a2["href"]
                if "Texto Integral" in txt: doc["link_texto_integral"] = href
                if ("Nota Técnica" in txt or "Voto" in txt): doc["link_nota_tecnica"] = href
        doc["data_busca"] = data_busca
        if "link_texto_integral" in doc:
            docs.append(doc)
            logger.info(f"Documento {idx} extraído")
    return docs

def enviar_email(docs):
    user = os.getenv("GMAIL_USER")
    pwd  = os.getenv("GMAIL_APP_PASSWORD")
    dest = os.getenv("EMAIL_DESTINATARIO")
    if not user or not pwd or not dest:
        logger.error("Credenciais faltando")
        return
    subj = f"ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(docs)} doc(s)"
    body = f"Total: {len(docs)}\n\n"
    for i,d in enumerate(docs,1):
        body += f"{i}. {d.get('titulo','')} - {d.get('link_texto_integral','')}\n"
    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"]   = dest
    msg["Subject"] = subj
    msg.attach(MIMEText(body,"plain","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587) as s:
            s.starttls()
            s.login(user,pwd)
            s.send_message(msg)
        logger.info("✅ E-mail enviado")
    except Exception as e:
        logger.error(f"❌ Falha envio: {e}\n{traceback.format_exc()}")

async def main_async():
    data = datetime.now().strftime("%d/%m/%Y")
    html = await buscar_portarias(data)
    docs = extrair_documentos(html, data)
    with open("resultados_aneel.json","w",encoding="utf-8") as f:
        json.dump({"data_exec":data,"total":len(docs),"docs":docs},f,ensure_ascii=False,indent=2)
    if docs:
        enviar_email(docs)
    else:
        logger.info("Nenhum documento para enviar")

def main():
    asyncio.run(main_async())

if __name__=="__main__":
    main()
