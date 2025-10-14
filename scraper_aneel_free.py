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
        
        # Salvar debug inicial
        content = await pagina.content()
        with open("pagina_debug.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("HTML de debug inicial salvo")
        
        # Clicar na aba "Legislação" - usar o seletor correto baseado no HTML
        try:
            await pagina.wait_for_selector('button:has-text("Legislação")', timeout=10000)
            await pagina.click('button:has-text("Legislação")')
            logger.info("Clicou na aba Legislação")
            
            # Aguardar um pouco para a aba carregar completamente
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Erro ao clicar na aba Legislação: {e}")
            return []
        
        # Salvar debug após clicar na aba
        content = await pagina.content()
        with open("pagina_debug_pos_click.html", "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("HTML pós-click salvo")
        
        # Preencher o campo "Todos os campos" da Legislação
        try:
            await pagina.wait_for_selector('input[name="LegislacaoPalavraChave"]', timeout=15000)
            await pagina.fill('input[name="LegislacaoPalavraChave"]', termo)
            logger.info(f"Preencheu palavra-chave: {termo}")
            
            # Configurar filtro de publicação para "Igual a" (que já é o padrão)
            await pagina.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label='Igual a')
            logger.info("Selecionou 'Igual a' para publicação")
            
            # Preencher apenas a data de publicação (campo 1, já que é "Igual a")
            await pagina.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
            logger.info(f"Preencheu data de publicação: {data_pesquisa}")
            
            # Clicar no botão Buscar
            await pagina.click('button[type="submit"]:has-text("Buscar")', timeout=10000)
            logger.info("Clicou em Buscar")
            
            # Aguardar resultados
            await pagina.wait_for_selector('table', timeout=30000)
            logger.info("Tabela de resultados carregada")
            
            # Salvar página de resultados
            content = await pagina.content()
            with open(f"resultado_{termo}.html", "w", encoding="utf-8") as f:
                f.write(content)
            
            # Processar resultados
            rows = await pagina.query_selector_all('table tr')
            documentos = []
            
            for row in rows[1:]:  # Pular cabeçalho
                cols = await row.query_selector_all("td")
                if len(cols) >= 2:
                    try:
                        titulo = (await cols[1].inner_text()).strip()
                        linkElem = await cols[1].query_selector("a")
                        url = await linkElem.get_attribute("href") if linkElem else None
                        if url and not url.startswith("http"):
                            url = f"https://biblioteca.aneel.gov.br{url}"
                        documentos.append({
                            "termo": termo, 
                            "titulo": titulo, 
                            "url": url
                        })
                    except Exception as e:
                        logger.error(f"Erro ao processar linha da tabela: {e}")
            
            logger.info(f"{len(documentos)} documentos encontrados para termo {termo}")
            return documentos
            
        except Exception as e:
            logger.error(f"Erro ao preencher campos ou buscar: {e}")
            return []
        
    except Exception as e:
        logger.error("Erro geral no buscar_termo:")
        logger.error(traceback.format_exc())
        
        # Salvar HTML de erro
        try:
            content = await pagina.content()
            with open("pagina_debug_erro.html", "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("HTML de erro salvo")
        except:
            pass
        
        return []

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
        
        # Salvar resultados
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
        logger.error("Erro crítico no scraper:")
        logger.error(traceback.format_exc())

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
        logger.error("Erro ao enviar email:")
        logger.error(traceback.format_exc())

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
