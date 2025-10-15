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

# Configuração de logging
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
            # Verifica se há mensagem de "nenhum registro"
            if "Nenhum registro encontrado" in content:
                logger.info("Nenhum registro encontrado para a busca")
            else:
                logger.warning("Não foi possível determinar o resultado da busca")
            return documentos

        # Extrai URLs dos documentos (links para PDFs)
        pdf_links = re.findall(r'https://www2\.aneel\.gov\.br/cedoc/[^"]+\.pdf', content)
        logger.info(f"Encontrados {len(pdf_links)} links de documentos")

        # Extrai títulos/descrições dos documentos
        # Procura por padrões de texto que descrevem as portarias
        descricoes = re.findall(r'<[^>]*>([^<]+(?:Libera|Aprova|Autoriza|Estabelece|Define)[^<]*)</[^>]*>', content, re.IGNORECASE)
        
        # Se não encontrar descrições, pega textos próximos aos links
        if not descricoes and pdf_links:
            # Extrai contexto ao redor dos links PDF
            for link in pdf_links:
                pattern = rf'(.{{0,200}}){re.escape(link)}(.{{0,200}})'
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    contexto = match.group(1) + match.group(2)
                    # Remove tags HTML
                    contexto_limpo = re.sub(r'<[^>]+>', ' ', contexto)
                    contexto_limpo = ' '.join(contexto_limpo.split())  # Remove espaços extras
                    if len(contexto_limpo) > 20:  # Se tem conteúdo relevante
                        descricoes.append(contexto_limpo[:200])

        # Cria lista de documentos
        for i, link in enumerate(pdf_links):
            titulo = f"Portaria ANEEL - {data_pesquisa}"
            if i < len(descricoes) and descricoes[i].strip():
                titulo = descricoes[i].strip()[:150] + "..." if len(descricoes[i]) > 150 else descricoes[i].strip()
            
            documentos.append({
                "termo": termo,
                "titulo": titulo,
                "url": link,
                "data_publicacao": data_pesquisa
            })

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

        assunto = f"Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')} - {len(documentos)} documento(s)"
        corpo = f"Foram encontrados {len(documentos)} documentos:\n\n"
        for i, doc in enumerate(documentos, 1):
            corpo += f"{i}. {doc['titulo']}\n   URL: {doc['url']}\n   Data: {doc['data_publicacao']}\n\n"

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
