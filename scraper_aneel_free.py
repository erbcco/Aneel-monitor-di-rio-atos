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
    Extrai documentos com informações detalhadas: ementa, datas, links
    """
    documentos = []
    
    # Divide o conteúdo em blocos de documentos
    # Cada bloco começa com "Legislação" e vai até o próximo "Legislação" ou fim
    blocos = re.split(r'\n\s*Legislação\s*\n', content)
    
    for i, bloco in enumerate(blocos[1:], 1):  # Pula o primeiro bloco (cabeçalho)
        try:
            documento = {}
            
            # Extrai data de assinatura
            match_assinatura = re.search(r'Assinatura:\s*(\d{2}/\d{2}/\d{4})', bloco)
            if match_assinatura:
                documento['data_assinatura'] = match_assinatura.group(1)
            
            # Extrai data de publicação
            match_publicacao = re.search(r'Publicação:\s*(\d{2}/\d{2}/\d{4})', bloco)
            if match_publicacao:
                documento['data_publicacao'] = match_publicacao.group(1)
            
            # Extrai link do texto integral
            match_texto = re.search(r'Texto Integral:\s*(https://[^\s\n]+)', bloco)
            if match_texto:
                documento['link_texto_integral'] = match_texto.group(1)
            
            # Extrai link da nota técnica (se houver)
            match_nota = re.search(r'Nota Técnica[^:]*:\s*(https://[^\s\n]+)', bloco)
            if match_nota:
                documento['link_nota_tecnica'] = match_nota.group(1)
            
            # Extrai ementa/assunto
            # Procura por texto descritivo que não seja metadata
            linhas = bloco.split('\n')
            ementa_candidatos = []
            
            for linha in linhas:
                linha = linha.strip()
                # Pula linhas de metadata
                if any(palavra in linha for palavra in ['Esfera:', 'Situação:', 'Assinatura:', 'Publicação:', 'Texto Integral:', 'Nota Técnica', 'Assunto:']):
                    continue
                # Se a linha tem um bom tamanho e parece descritiva
                if len(linha) > 30 and any(verbo in linha.lower() for verbo in ['libera', 'aprova', 'autoriza', 'estabelece', 'define', 'regulamenta', 'determina', 'institui']):
                    ementa_candidatos.append(linha)
            
            # Pega a melhor ementa (mais longa e descritiva)
            if ementa_candidatos:
                documento['ementa'] = max(ementa_candidatos, key=len)
            else:
                # Se não encontrou ementa descritiva, procura por "Assunto:"
                match_assunto = re.search(r'Assunto:\s*([^\n]+)', bloco)
                if match_assunto:
                    documento['ementa'] = f"Assunto: {match_assunto.group(1)}"
                else:
                    documento['ementa'] = "Ementa não disponível"
            
            # Extrai número do documento do link (se possível)
            if 'link_texto_integral' in documento:
                match_numero = re.search(r'/([^/]+)\.pdf$', documento['link_texto_integral'])
                if match_numero:
                    documento['numero_documento'] = match_numero.group(1)
            
            # Só adiciona se tem pelo menos o link
            if 'link_texto_integral' in documento:
                documentos.append(documento)
                
        except Exception as e:
            logger.warning(f"Erro ao processar bloco {i}: {e}")
            continue
    
    return documentos

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

        # Extrai informações dos resultados
        documentos = []
        
        # Procura por "X registros encontrados"
        registros_match = re.search(r'(\d+)\s*registros encontrados', content)
        if registros_match:
            total_registros = int(registros_match.group(1))
            logger.info(f"Encontrados {total_registros} registros na busca")
        else:
            total_registros = 0

        if total_registros == 0:
            if "Nenhum registro encontrado" in content:
                logger.info("Nenhum registro encontrado para a busca")
            return documentos

        # Extrai documentos detalhados
        documentos = extrair_documentos_detalhados(content)
        
        # Enriquece cada documento com informações adicionais
        for doc in documentos:
            doc['termo_busca'] = termo
            doc['data_busca'] = data_pesquisa
            # Limpa e formata a ementa
            if 'ementa' in doc:
                doc['ementa'] = unescape(doc['ementa']).strip()
                # Remove tags HTML residuais
                doc['ementa'] = re.sub(r'<[^>]+>', '', doc['ementa'])

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
    try:
        remetente = os.getenv("GMAIL_USER")
        senha = os.getenv("GMAIL_APP_PASSWORD")
        destinatario = os.getenv("EMAIL_DESTINATARIO")

        if not (remetente and senha and destinatario):
            logger.warning("Variáveis de e-mail não configuradas")
            return

        assunto = f"📋 Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y')} - {len(documentos)} portaria(s)"
        
        # Cabeçalho do e-mail
        corpo = f"🔍 MONITORAMENTO ANEEL - PORTARIAS DO DIA {datetime.now().strftime('%d/%m/%Y')}\n"
        corpo += f"═══════════════════════════════════════════════════════════════\n\n"
        corpo += f"📊 TOTAL DE DOCUMENTOS ENCONTRADOS: {len(documentos)}\n\n"

        # Lista detalhada de cada documento
        for i, doc in enumerate(documentos, 1):
            corpo += f"📄 DOCUMENTO {i}\n"
            corpo += f"{'─' * 50}\n"
            
            # Ementa
            if 'ementa' in doc and doc['ementa']:
                corpo += f"📝 EMENTA:\n   {doc['ementa']}\n\n"
            
            # Datas
            if 'data_assinatura' in doc:
                corpo += f"✍️  DATA DE ASSINATURA: {doc['data_assinatura']}\n"
            if 'data_publicacao' in doc:
                corpo += f"📅 DATA DE PUBLICAÇÃO: {doc['data_publicacao']}\n"
            
            # Links
            if 'link_texto_integral' in doc:
                corpo += f"🔗 TEXTO INTEGRAL: {doc['link_texto_integral']}\n"
            if 'link_nota_tecnica' in doc:
                corpo += f"📋 NOTA TÉCNICA: {doc['link_nota_tecnica']}\n"
            
            # Identificação do documento
            if 'numero_documento' in doc:
                corpo += f"🆔 NÚMERO DO DOCUMENTO: {doc['numero_documento']}\n"
            
            corpo += f"\n{'═' * 60}\n\n"

        # Rodapé
        corpo += f"🤖 Este e-mail foi gerado automaticamente pelo sistema de monitoramento ANEEL.\n"
        corpo += f"⏰ Data/hora de execução: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}\n"

        msg = MIMEMultipart()
        msg["From"] = remetente
        msg["To"] = destinatario
        msg["Subject"] = assunto
        msg.attach(MIMEText(corpo, "plain", "utf-8"))

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
