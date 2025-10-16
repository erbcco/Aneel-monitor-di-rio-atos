import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import re
import traceback

# Configuração logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")

file_handler = logging.FileHandler("scraper.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(file_handler)

def buscar_portarias(data_pesquisa):
    """
    Busca portarias da ANEEL usando requisição HTTP direta
    """
    logger.info(f"Buscando portarias para data: {data_pesquisa}")
    
    url = "https://biblioteca.aneel.gov.br/Busca/ResultadoBuscaLegislacao"
    
    # Parâmetros da busca
    params = {
        'LegislacaoPalavraChave': 'Portaria',
        'LegislacaoTipoFiltroDataPublicacao': '0',  # Igual a
        'LegislacaoDataPublicacao1': data_pesquisa,
        'Guid': '',
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    try:
        response = requests.post(url, data=params, headers=headers, timeout=30)
        response.raise_for_status()
        
        html_content = response.text
        
        # Salva HTML
        with open("resultado_Portaria.html", "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("Página de resultados salva")
        
        # Extrai documentos
        documentos = extrair_documentos(html_content, data_pesquisa)
        
        return documentos
        
    except Exception as e:
        logger.error(f"Erro na busca: {e}")
        logger.error(traceback.format_exc())
        return []

def extrair_documentos(html_content, data_busca):
    """
    Extrai documentos do HTML usando BeautifulSoup
    """
    logger.info("Extraindo documentos do HTML")
    documentos = []
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Verifica total de registros
        total_elem = soup.find(string=re.compile(r'\d+\s*registros encontrados'))
        if total_elem:
            match = re.search(r'(\d+)\s*registros', str(total_elem))
            if match:
                total = int(match.group(1))
                logger.info(f"Total de registros encontrados: {total}")
        
        # Busca fichas de documentos
        fichas = soup.find_all('div', class_='ficha-acervo-detalhe')
        logger.info(f"Encontradas {len(fichas)} fichas no HTML")
        
        for i, ficha in enumerate(fichas, 1):
            try:
                doc = {}
                
                # Título
                titulo = ficha.find('p', class_='titulo')
                if titulo:
                    doc['titulo'] = titulo.get_text(strip=True)
                
                # Data assinatura
                assinatura = ficha.find('p', class_='assinatura')
                if assinatura:
                    match = re.search(r'(\d{2}/\d{2}/\d{4})', assinatura.get_text())
                    if match:
                        doc['data_assinatura'] = match.group(1)
                
                # Data publicação
                publicacao = ficha.find('p', class_='publicacao')
                if publicacao:
                    match = re.search(r'(\d{2}/\d{2}/\d{4})', publicacao.get_text())
                    if match:
                        doc['data_publicacao'] = match.group(1)
                
                # Ementa
                ementa_div = ficha.find('div', class_='texto-html-container')
                if ementa_div:
                    doc['ementa'] = ementa_div.get_text(strip=True)
                
                # Assunto
                assunto = ficha.find('p', class_='assunto')
                if assunto:
                    doc['assunto'] = assunto.get_text(strip=True).replace('Assunto', '').strip()
                
                # Links
                links = ficha.find_all('p', class_='sites')
                for link_p in links:
                    rotulo = link_p.find('span', class_='rotulo')
                    link_a = link_p.find('a')
                    if rotulo and link_a:
                        rotulo_text = rotulo.get_text(strip=True)
                        href = link_a.get('href', '')
                        if 'Texto Integral' in rotulo_text and href:
                            doc['link_texto_integral'] = href
                        elif ('Nota' in rotulo_text or 'Voto' in rotulo_text) and href:
                            doc['link_nota_tecnica'] = href
                
                doc['data_busca'] = data_busca
                
                if 'link_texto_integral' in doc:
                    documentos.append(doc)
                    logger.info(f"Documento {i} extraído")
                    
            except Exception as e:
                logger.error(f"Erro ao processar ficha {i}: {e}")
                continue
        
        logger.info(f"Total extraído: {len(documentos)}")
        return documentos
        
    except Exception as e:
        logger.error(f"Erro na extração: {e}")
        logger.error(traceback.format_exc())
        return []

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("EMAIL_DESTINATARIO")
    
    logger.info(f"Enviando e-mail de '{remetente}' para '{destinatario}'")
    
    if not remetente or not senha or not destinatario:
        logger.error("Credenciais ausentes")
        return
    
    assunto = f"📋 ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} documento(s)"
    
    corpo = f"🔍 MONITORAMENTO ANEEL - {datetime.now().strftime('%d/%m/%Y')}\n"
    corpo += f"{'=' * 70}\n\n"
    corpo += f"📊 TOTAL: {len(documentos)} documento(s)\n\n"
    
    for i, doc in enumerate(documentos, 1):
        corpo += f"📄 DOCUMENTO {i}\n"
        corpo += f"{'-' * 60}\n"
        
        if 'titulo' in doc:
            corpo += f"📌 {doc['titulo']}\n\n"
        if 'ementa' in doc:
            corpo += f"📝 {doc['ementa']}\n\n"
        if 'assunto' in doc:
            corpo += f"🏷️  ASSUNTO: {doc['assunto']}\n"
        if 'data_assinatura' in doc:
            corpo += f"✍️  ASSINATURA: {doc['data_assinatura']}\n"
        if 'data_publicacao' in doc:
            corpo += f"📅 PUBLICAÇÃO: {doc['data_publicacao']}\n"
        if 'link_texto_integral' in doc:
            corpo += f"🔗 LINK: {doc['link_texto_integral']}\n"
        
        corpo += f"\n{'=' * 70}\n\n"
    
    corpo += f"🤖 E-mail automático\n⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
    
    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))
    
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(remetente, senha)
            server.send_message(msg)
        logger.info("✅ E-mail enviado!")
    except Exception as e:
        logger.error(f"❌ Falha no envio: {e}")
        logger.error(traceback.format_exc())

def main():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    logger.info(f"Iniciando busca para {data_pesquisa}")
    
    documentos = buscar_portarias(data_pesquisa)
    
    # Salva JSON
    with open("resultados_aneel.json", "w", encoding="utf-8") as f:
        json.dump({
            "data_execucao": datetime.now().isoformat(),
            "total_documentos": len(documentos),
            "documentos": documentos
        }, f, ensure_ascii=False, indent=2)
    
    if documentos:
        enviar_email(documentos)
        logger.info(f"✅ Processo concluído: {len(documentos)} documentos")
    else:
        logger.info("⚠️ Nenhum documento encontrado")

if __name__ == "__main__":
    main()
