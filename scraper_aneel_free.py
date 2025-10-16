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
    Extrai documentos com informações detalhadas usando BeautifulSoup
    """
    documentos = []
    logger.info("Iniciando extração de documentos detalhados")
    
    try:
        soup = BeautifulSoup(content, 'html.parser')
        
        # Busca todas as fichas de detalhe
        fichas = soup.find_all('div', class_='ficha-acervo-detalhe')
        
        logger.info(f"Encontradas {len(fichas)} fichas de detalhe no HTML")
        
        for i, ficha in enumerate(fichas, 1):
            try:
                documento = {}
                
                # Extrai título (contém número da portaria/despacho)
                titulo = ficha.find('p', class_='titulo')
                if titulo:
                    titulo_text = titulo.get_text(strip=True)
                    documento['titulo'] = re.sub(r'\s+', ' ', titulo_text)
                
                # Extrai data de assinatura
                assinatura = ficha.find('p', class_='assinatura')
                if assinatura:
                    data_match = re.search(r'(\d{2}/\d{2}/\d{4})', assinatura.get_text())
                    if data_match:
                        documento['data_assinatura'] = data_match.group(1)
                
                # Extrai data de publicação
                publicacao = ficha.find('p', class_='publicacao')
                if publicacao:
                    data_match = re.search(r'(\d{2}/\d{2}/\d{4})', publicacao.get_text())
                    if data_match:
                        documento['data_publicacao'] = data_match.group(1)
                
                # Extrai ementa
                ementa_div = ficha.find('div', class_='texto-html-container')
                if ementa_div:
                    ementa_text = ementa_div.get_text(strip=True)
                    documento['ementa'] = re.sub(r'\s+', ' ', ementa_text).replace('Ementa', '').strip()
                else:
                    documento['ementa'] = "Ementa não disponível"
                
                # Extrai assunto
                assunto = ficha.find('p', class_='assunto')
                if assunto:
                    assunto_text = assunto.get_text(strip=True)
                    documento['assunto'] = assunto_text.replace('Assunto', '').strip()
                
                # Extrai links de PDF (Texto Integral e Nota Técnica)
                links_sites = ficha.find_all('p', class_='sites')
                for link_site in links_sites:
                    rotulo = link_site.find('span', class_='rotulo')
                    if rotulo:
                        rotulo_text = rotulo.get_text(strip=True)
                        link_a = link_site.find('a')
                        if link_a and link_a.get('href'):
                            url = link_a.get('href')
                            if 'Texto Integral' in rotulo_text:
                                documento['link_texto_integral'] = url
                                # Extrai número do documento
                                match_numero = re.search(r'/([^/]+)\.pdf$', url)
                                if match_numero:
                                    documento['numero_documento'] = match_numero.group(1)
                            elif 'Nota Técnica' in rotulo_text or 'Voto' in rotulo_text:
                                documento['link_nota_tecnica'] = url
                
                documento['termo_busca'] = 'Portaria'
                
                # Só adiciona se tiver pelo menos o link do texto integral
                if 'link_texto_integral' in documento:
                    documentos.append(documento)
                    logger.info(f"Documento {i} extraído: {documento.get('titulo', 'sem_titulo')}")
                else:
                    logger.warning(f"Documento {i} ignorado (sem link de texto integral)")
                    
            except Exception as e:
                logger.error(f"Erro ao processar ficha {i}: {e}")
                continue
        
        logger.info(f"Total de documentos extraídos: {len(documentos)}")
        return documentos
        
    except Exception as e:
        logger.error(f"Erro geral na extração: {e}")
        logger.error(traceback.format_exc())
        return []

async def buscar_termo(pagina, termo, data_pesquisa):
    try:
        logger.info(f"Iniciando busca pelo termo: {termo} - Data: {data_pesquisa}")
        await pagina.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")

        # Clica na aba Legislação
        await pagina.wait_for_selector('button:has-text("Legislação"), a:has-text("Legislação")', timeout=10000)
        try:
            await pagina.click('button:has-text("Legislação")')
        except:
            await pagina.click('a:has-text("Legislação")')
        
        await asyncio.sleep(2)

        # Preenche campos
        input_palavra = pagina.locator('input[name="LegislacaoPalavraChave"]')
        await input_palavra.clear()
        await input_palavra.fill(termo)
        await asyncio.sleep(1)
        
        valor_preenchido = await input_palavra.input_value()
        logger.info(f"Valor no campo palavra-chave: '{valor_preenchido}'")

        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
        await asyncio.sleep(1)

        input_data = pagina.locator('input[name="LegislacaoDataPublicacao1"]')
        await input_data.clear()
        await input_data.fill(data_pesquisa)
        await asyncio.sleep(1)
        
        data_preenchida = await input_data.input_value()
        logger.info(f"Valor no campo data: '{data_preenchida}'")
        logger.info("Campos de busca preenchidos e verificados")

        # Executa busca
        await asyncio.sleep(2)
        await pagina.click('button:has-text("Buscar")')
        await pagina.wait_for_load_state('networkidle')
        await asyncio.sleep(5)
        
        logger.info("Busca executada e página carregada")

        # Salva página de resultados
        content = await pagina.content()
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Página de resultados salva")

        # Regex para detectar número de registros
        registros_match = re.search(r'<strong>(\d+)</strong>\s*registros encontrados', content, re.IGNORECASE)
        if not registros_match:
            registros_match = re.search(r'(\d+)\s*registros encontrados', content, re.IGNORECASE)
        
        if registros_match:
            total_registros = int(registros_match.group(1))
            logger.info(f"Encontrados {total_registros} registros na busca")
        else:
            total_registros = 0
            logger.warning("Não foi possível determinar o número de registros")

        if total_registros == 0:
            if "Nenhum registro encontrado" in content:
                logger.info("Nenhum registro encontrado para a busca")
            return []

        # Extrai documentos detalhados
        documentos = extrair_documentos_detalhados(content)
        
        # Enriquece cada documento
        for doc in documentos:
            doc['data_busca'] = data_pesquisa

        logger.info(f"Total de documentos processados: {len(documentos)}")
        return documentos

    except Exception as e:
        logger.error(f"Erro ao buscar termo '{termo}': {e}")
        logger.error(traceback.format_exc())
        try:
            with open(f"erro_{termo}.html", "w", encoding="utf-8") as f:
                f.write(await pagina.content())
        except:
            pass
        return []

async def main_async():
    data_pesquisa = datetime.now().strftime("%d/%m/%Y")
    logger.info(f"Executando busca para data: {data_pesquisa}")
    documentos_totais = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_viewport_size({"width": 1280, "height": 720})

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
        logger.info(f"Processo concluído. {len(documentos_totais)} documentos encontrados e e-mail enviado.")
    else:
        logger.info("Nenhum documento encontrado, e-mail não será enviado")

def enviar_email(documentos):
    remetente = os.getenv("GMAIL_USER")
    senha = os.getenv("GMAIL_APP_PASSWORD")
    destinatario = os.getenv("EMAIL_DESTINATARIO")
    
    logger.info(f"Tentativa de envio e-mail de '{remetente}' para '{destinatario}'")
    
    if not remetente or not senha or not destinatario:
        logger.error(f"Credenciais inválidas: remetente={remetente}, dest={destinatario}, senha={'OK' if senha else 'MISSING'}")
        return

    assunto = f"📋 Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} documento(s)"
    
    corpo = f"🔍 MONITORAMENTO ANEEL - {datetime.now().strftime('%d/%m/%Y')}\n"
    corpo += f"{'═' * 70}\n\n"
    corpo += f"📊 TOTAL: {len(documentos)} documento(s)\n\n"

    for i, doc in enumerate(documentos, 1):
        corpo += f"📄 DOCUMENTO {i}\n"
        corpo += f"{'─' * 60}\n"
        
        if 'titulo' in doc:
            corpo += f"📌 {doc['titulo']}\n\n"
        
        if 'ementa' in doc and doc['ementa']:
            corpo += f"📝 EMENTA:\n   {doc['ementa']}\n\n"
        
        if 'assunto' in doc and doc['assunto']:
            corpo += f"🏷️  ASSUNTO: {doc['assunto']}\n"
        
        if 'data_assinatura' in doc:
            corpo += f"✍️  ASSINATURA: {doc['data_assinatura']}\n"
        if 'data_publicacao' in doc:
            corpo += f"📅 PUBLICAÇÃO: {doc['data_publicacao']}\n"
        
        if 'link_texto_integral' in doc:
            corpo += f"🔗 TEXTO INTEGRAL: {doc['link_texto_integral']}\n"
        if 'link_nota_tecnica' in doc:
            corpo += f"📋 NOTA TÉCNICA: {doc['link_nota_tecnica']}\n"
        
        if 'numero_documento' in doc:
            corpo += f"🆔 NÚMERO: {doc['numero_documento']}\n"
        
        corpo += f"\n{'═' * 70}\n\n"

    corpo += f"🤖 E-mail automático - Sistema de Monitoramento ANEEL\n"
    corpo += f"⏰ {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}\n"

    msg = MIMEMultipart()
    msg["From"] = remetente
    msg["To"] = destinatario
    msg["Subject"] = assunto
    msg.attach(MIMEText(corpo, "plain", "utf-8"))

    try:
        logger.info("Iniciando conexão SMTP...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            logger.info("Fazendo login...")
            server.login(remetente, senha)
            logger.info("Enviando mensagem...")
            server.send_message(msg)
        logger.info("✅ E-mail enviado com sucesso!")
    except Exception as e:
        logger.error(f"❌ Falha no envio: {e}")
        logger.error(traceback.format_exc())

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
