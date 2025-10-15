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

        # Salva página inicial para debug
        with open("pagina_debug.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())

        # Aguarda o formulário carregar completamente
        await pagina.wait_for_selector('input[name="LegislacaoPalavraChave"]', timeout=10000)
        
        # Preenche palavra-chave com verificação
        input_palavra = pagina.locator('input[name="LegislacaoPalavraChave"]')
        await input_palavra.clear()
        await input_palavra.fill(termo)
        await asyncio.sleep(1)
        
        # Verifica se o campo foi preenchido
        valor_preenchido = await input_palavra.input_value()
        logger.info(f"Valor no campo palavra-chave: '{valor_preenchido}'")
        
        if valor_preenchido != termo:
            logger.error(f"Campo palavra-chave não foi preenchido corretamente. Esperado: '{termo}', Obtido: '{valor_preenchido}'")
            return []

        # Seleciona filtro de data
        await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
        await asyncio.sleep(1)

        # Preenche data
        input_data = pagina.locator('input[name="LegislacaoDataPublicacao1"]')
        await input_data.clear()
        await input_data.fill(data_pesquisa)
        await asyncio.sleep(1)
        
        # Verifica se a data foi preenchida
        data_preenchida = await input_data.input_value()
        logger.info(f"Valor no campo data: '{data_preenchida}'")
        
        logger.info("Campos de busca preenchidos e verificados")

        # Clica no botão buscar
        await asyncio.sleep(2)
        await pagina.click('button:has-text("Buscar")')
        await pagina.wait_for_load_state('networkidle')
        await asyncio.sleep(5)  # Aumenta tempo de espera
        
        logger.info("Busca executada e página carregada")

        # Verifica resultados
        documentos = []
        
        # Primeiro verifica se há mensagem de "nenhum registro"
        nenhum_resultado = await pagina.locator('text=Nenhum registro encontrado').count()
        if nenhum_resultado > 0:
            logger.info("Mensagem 'Nenhum registro encontrado' detectada")
            nome_html = f"pagina_sem_resultados_{termo}_{int(time.time())}.html"
            with open(nome_html, "w", encoding="utf-8") as f:
                f.write(await pagina.content())
            logger.warning(f"Sem resultados para o termo. Página salva: {nome_html}")
            return documentos

        # Verifica se há tabela de resultados
        try:
            await pagina.wait_for_selector('table', timeout=30000)
            logger.info("Tabela de resultados encontrada")
        except:
            nome_html = f"pagina_sem_tabela_{termo}_{int(time.time())}.html"
            with open(nome_html, "w", encoding="utf-8") as f:
                f.write(await pagina.content())
            logger.warning(f"Sem tabela de resultados. Página salva: {nome_html}")
            return documentos

        # Extrai resultados da tabela
        with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
            f.write(await pagina.content())

        rows = await pagina.query_selector_all('table tr')
        logger.info(f"Encontradas {len(rows)} linhas na tabela")
        
        for i, row in enumerate(rows[1:], 1):  # Pula cabeçalho
            cols = await row.query_selector_all("td")
            if len(cols) >= 2:
                try:
                    titulo = (await cols[1].inner_text()).strip()
                    link_elem = await cols[1].query_selector("a")
                    url = await link_elem.get_attribute("href") if link_elem else None
                    url_completa = url if url and url.startswith("http") else f"https://biblioteca.aneel.gov.br{url}" if url else None
                    documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})
                    logger.info(f"Documento {i}: {titulo[:50]}...")
                except Exception as e:
                    logger.error(f"Erro ao processar linha {i}: {e}")

        logger.info(f"Total de documentos encontrados: {len(documentos)}")
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
        
        # Configura viewport para garantir que elementos sejam visíveis
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

        assunto = f"Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        corpo = f"Foram encontrados {len(documentos)} documentos:\n\n"
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

        logger.info("E-mail enviado com sucesso!")
    except Exception:
        logger.error("Erro ao enviar e-mail:")
        logger.error(traceback.format_exc())

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
