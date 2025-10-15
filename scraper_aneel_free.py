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
import re
from html import unescape

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")
file_handler = logging.FileHandler("scraper.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(file_handler)

PALAVRAS_CHAVE = ["Portaria"]

def extrair_documentos_detalhados(content):
    documentos = []
    content_limpo = re.sub(r'\s+', ' ', content)
    padrao = r'Legislação Esfera:[^L]+?(Texto Integral:\s*(https://[^\s]+))'
    for i, match in enumerate(re.finditer(padrao, content_limpo, re.DOTALL), 1):
        bloco = match.group(0)
        doc = {}
        ma = re.search(r'Assinatura:\s*(\d{2}/\d{2}/\d{4})', bloco)
        if ma: doc['data_assinatura'] = ma.group(1)
        mp = re.search(r'Publicação:\s*(\d{2}/\d{2}/\d{4})', bloco)
        if mp: doc['data_publicacao'] = mp.group(1)
        doc['link_texto_integral'] = match.group(1)
        mn = re.search(r'/([^/]+)\.pdf$', doc['link_texto_integral'])
        if mn: doc['numero_documento'] = mn.group(1)
        me = re.search(r'Publicação:\s*\d{2}/\d{2}/\d{4}\s+(.*?)\s+Assunto:', bloco)
        doc['ementa'] = unescape(re.sub(r'<[^>]+>', '', me.group(1).strip())) if me else "Ementa não disponível"
        mas = re.search(r'Assunto:\s*([^Texto]+)', bloco)
        if mas: doc['assunto'] = mas.group(1).strip()
        mnota = re.search(r'Nota Técnica[^:]*:\s*(https://[^\s]+)', bloco)
        if mnota: doc['link_nota_tecnica'] = mnota.group(1)
        doc['termo_busca'] = 'Portaria'
        documentos.append(doc)
        logger.info(f"Documento {i}: {doc['numero_documento']}")
    logger.info(f"Total extraído: {len(documentos)}")
    return documentos

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Busca: {termo} em {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
        await pagina.wait_for_selector('button:has-text("Legislação"), a:has-text("Legislação")', timeout=10000)
        try: await pagina.click('button:has-text("Legislação")')
        except: await pagina.click('a:has-text("Legislação")')
        await asyncio.sleep(2)
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        logger.info("Campos preenchidos")
        await asyncio.sleep(2)
        await pagina.click('button:has-text("Buscar")')
        await pagina.wait_for_load_state('networkidle')
        await asyncio.sleep(5)
        content = await pagina.content()
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Página resultados salva")
        m = re.search(r'(\d+)\s*registros encontrados', content)
        total = int(m.group(1)) if m else 0
        logger.info(f"Registros: {total}")
        if total == 0 and "Nenhum registro encontrado" in content:
            logger.info("Sem resultados")
            return []
        docs = extrair_documentos_detalhados(content) if total > 0 else []
        for d in docs: d['data_busca'] = data_pesquisa
        return docs
    except Exception as e:
        logger.error(f"Erro busca: {e}\n{traceback.format_exc()}")
        return []

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    resultados = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width":1280,"height":720})
        for termo in PALAVRAS_CHAVE:
            resultados += await buscar_termo(page, termo, data_pesquisa)
        await browser.close()
    with open("resultados_aneel.json", "w", encoding="utf-8") as f:
        json.dump({
            "data_execucao": datetime.now().isoformat(),
            "total_documentos": len(resultados),
            "documentos": resultados
        }, f, ensure_ascii=False, indent=2)
    if resultados:
        enviar_email(resultados)
    else:
        logger.info("Nenhum documento, e-mail não enviado")

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("EMAIL_DESTINATARIO")
    logger.info(f"Tentativa envio e-mail de '{remetente}' para '{destinatario}'")
    if not remetente or not senha or not destinatario:
        logger.error(f"Credenciais inválidas: remetente={remetente}, dest={destinatario}")
        return
    assunto = f"📋 ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} portaria(s)"
    corpo = f"Total: {len(documentos)}\n\n"
    for i, doc in enumerate(documentos,1):
        corpo += f"{i}. {doc.get('ementa','')} - {doc.get('link_texto_integral','')}\n"
    msg = MIMEMultipart()
    msg["From"]=remetente; msg["To"]=destinatario; msg["Subject"]=assunto
    msg.attach(MIMEText(corpo,"plain","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587) as server:
            server.starttls(); server.login(remetente,senha); server.send_message(msg)
        logger.info("E-mail enviado com sucesso!")
    except Exception as e:
        logger.error(f"Falha envio e-mail: {e}\n{traceback.format_exc()}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
