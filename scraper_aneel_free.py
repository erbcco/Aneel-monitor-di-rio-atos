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
    """
    Extrai documentos com informações detalhadas: ementa, assunto, datas, links
    """
    documentos = []
    content_limpo = re.sub(r'\s+', ' ', content)
    padrao = r'Legislação Esfera:[^L]+?(Texto Integral:\s*(https://[^\s]+))'
    for i, match in enumerate(re.finditer(padrao, content_limpo, re.DOTALL), 1):
        bloco = match.group(0)
        doc = {}
        # Datas
        m1 = re.search(r'Assinatura:\s*(\d{2}/\d{2}/\d{4})', bloco)
        if m1: doc['data_assinatura'] = m1.group(1)
        m2 = re.search(r'Publicação:\s*(\d{2}/\d{2}/\d{4})', bloco)
        if m2: doc['data_publicacao'] = m2.group(1)
        # Link texto integral
        doc['link_texto_integral'] = match.group(1)
        # Número do documento
        mnum = re.search(r'/([^/]+)\.pdf$', doc['link_texto_integral'])
        if mnum: doc['numero_documento'] = mnum.group(1)
        # Ementa
        mementa = re.search(r'Publicação:\s*\d{2}/\d{2}/\d{4}\s+(.*?)\s+Assunto:', bloco)
        if mementa:
            e = unescape(mementa.group(1).strip())
            doc['ementa'] = re.sub(r'<[^>]+>', '', e)
        else:
            doc['ementa'] = "Ementa não disponível"
        # Assunto
        massunto = re.search(r'Assunto:\s*([^Texto]+)', bloco)
        if massunto: doc['assunto'] = massunto.group(1).strip()
        # Nota técnica
        mnota = re.search(r'Nota Técnica[^:]*:\s*(https://[^\s]+)', bloco)
        if mnota: doc['link_nota_tecnica'] = mnota.group(1)
        doc['termo_busca'] = 'Portaria'
        documentos.append(doc)
        logger.info(f"Documento {i} extraído: {doc.get('numero_documento','n/a')}")
    logger.info(f"Total de documentos extraídos: {len(documentos)}")
    return documentos

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Iniciando busca: {termo} em {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
        await pagina.wait_for_selector('button:has-text("Legislação"), a:has-text("Legislação")', timeout=10000)
        try: await pagina.click('button:has-text("Legislação")')
        except: await pagina.click('a:has-text("Legislação")')
        await asyncio.sleep(2)
        # Preencher
        await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
        await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
        logger.info("Campos preenchidos")
        await asyncio.sleep(2)
        await pagina.click('button:has-text("Buscar")')
        await pagina.wait_for_load_state('networkidle')
        await asyncio.sleep(5)
        content = await pagina.content()
        with open(f"resultado_{termo}.html","w",encoding="utf-8") as f: f.write(content)
        # Verifica registros
        m = re.search(r'(\d+)\s*registros encontrados', content)
        total = int(m.group(1)) if m else 0
        logger.info(f"Registros encontrados: {total}")
        if total==0:
            if "Nenhum registro encontrado" in content:
                logger.info("Sem resultados")
            return []
        # Extrai
        documentos = extrair_documentos_detalhados(content)
        for doc in documentos: doc['data_busca'] = data_pesquisa
        return documentos
    except Exception as e:
        logger.error(f"Erro na busca: {e}\n{traceback.format_exc()}")
        return []

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    documentos_totais = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width":1280,"height":720})
        for termo in PALAVRAS_CHAVE:
            documentos_totais += await buscar_termo(page, termo, data_pesquisa)
        await browser.close()
    with open("resultados_aneel.json","w",encoding="utf-8") as f:
        json.dump({"data_execucao":datetime.now().isoformat(),
                   "total_documentos":len(documentos_totais),
                   "documentos":documentos_totais},
                  f,ensure_ascii=False,indent=2)
    if documentos_totais:
        enviar_email(documentos_totais)
    else:
        logger.info("Nenhum documento, e-mail não enviado")

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("EMAIL_DESTINATARIO")
    logger.info(f"Tentando enviar e-mail de {remetente} para {destinatario}")
    if not remetente or not senha or not destinatario:
        logger.error(f"Credenciais inválidas: remetente={remetente}, dest={destinatario}")
        return
    # Monta e-mail
    assunto = f"📋 ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} portaria(s)"
    corpo = f"Total: {len(documentos)}\n\n"
    for i, doc in enumerate(documentos,1):
        corpo += f"{i}. {doc.get('ementa','')} - {doc.get('link_texto_integral','')}\n"
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo,"plain","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587) as server:
            server.starttls()
            server.login(remetente,senha)
            server.send_message(msg)
        logger.info("E-mail enviado com sucesso!")
    except Exception as e:
        logger.error(f"Falha no envio de e-mail: {e}\n{traceback.format_exc()}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
