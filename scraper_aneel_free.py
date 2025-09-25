import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AneelScraperFree:
    def __init__(self):
        self.base_url = "https://biblioteca.aneel.gov.br/Busca/Avancada"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": self.base_url,
            "Origin": "https://biblioteca.aneel.gov.br"
        })
        self.palavras_chave = ["Portaria"]
        self.data_pesquisa = datetime.now().strftime("%d/%m/%Y")
        self.documentos = []

    def buscar_por_termo(self, termo):
        logger.debug(f"Buscando termo: {termo}")
        resp = self.session.get(self.base_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        viewstate = soup.select_one('input[name="__VIEWSTATE"]')
        eventvalidation = soup.select_one('input[name="__EVENTVALIDATION"]')
        viewstategenerator = soup.select_one('input[name="__VIEWSTATEGENERATOR"]')

        if not (viewstate and eventvalidation and viewstategenerator):
            logger.error("Campos __VIEWSTATE, __EVENTVALIDATION ou __VIEWSTATEGENERATOR ausentes")
            return []

        data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": viewstate["value"],
            "__VIEWSTATEGENERATOR": viewstategenerator["value"],
            "__EVENTVALIDATION": eventvalidation["value"],
            "ctl00$Conteudo$txtPalavraChave": termo,
            "ctl00$Conteudo$ddlCampoPesquisa": "Todos os campos",
            "ctl00$Conteudo$ddlTipoPesquisa": "avancada",
            "ctl00$Conteudo$txtDataInicio": self.data_pesquisa,
            "ctl00$Conteudo$txtDataFim": self.data_pesquisa,
            "ctl00$Conteudo$btnPesquisar": "Buscar",
        }

        post_resp = self.session.post(self.base_url, data=data)
        post_resp.raise_for_status()

        logger.debug(f"Tamanho da resposta POST: {len(post_resp.text)}")

        # Salvar HTML para análise
        with open("resultado_busca_aneel.html", "w", encoding="utf-8") as f:
            f.write(post_resp.text)
        logger.info("Arquivo resultado_busca_aneel.html salvo.")

        documentos = self.extrair_documentos(post_resp.text, termo)
        logger.info(f"Documentos encontrados: {len(documentos)}")

        self.documentos.extend(documentos)
        return documentos

    def extrair_documentos(self, html, termo):
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.k-grid-table tr")
        documentos = []
        if not rows:
            logger.warning("Nenhuma linha encontrada na tabela de resultados")
        for row in rows[1:]:
            cols = row.find_all("td")
            if len(cols) >= 2:
                titulo = cols[1].get_text(strip=True)
                link_tag = cols[1].find("a")
                url_completa = f"https://biblioteca.aneel.gov.br{link_tag['href']}" if link_tag and link_tag.has_attr("href") else ""
                documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})
        return documentos

    def executar_consulta_completa(self):
        for termo in self.palavras_chave:
            self.buscar_por_termo(termo)

        logger.info(f"Total de documentos encontrados: {len(self.documentos)}")
        self.salvar_resultados()

        if self.documentos:
            self.enviar_email()
        else:
            logger.info("Nenhum documento relevante encontrado.")

    def salvar_resultados(self):
        resultado = {
            "data_execucao": datetime.now().isoformat(),
            "documentos": self.documentos,
        }
        with open("resultados_aneel.json", "w", encoding="utf-8") as f:
            json.dump(resultado, f, ensure_ascii=False, indent=2)
        logger.info("Arquivo resultados_aneel.json salvo.")

    def enviar_email(self):
        try:
            remetente = os.getenv("GMAIL_USER")
            senha = os.getenv("GMAIL_APP_PASSWORD")
            destinatario = os.getenv("EMAIL_DESTINATARIO")
            if not (remetente and senha and destinatario):
                logger.error("Variáveis de ambiente de e-mail não configuradas.")
                return
            assunto = f"Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            corpo = "Documentos encontrados:\n"
            for doc in self.documentos:
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

            logger.info("E-mail enviado com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao enviar e-mail: {e}")


def main():
    logger.info("Iniciando monitoramento ANEEL...")
    scraper = AneelScraperFree()
    scraper.executar_consulta_completa()
    logger.info("Monitoramento finalizado.")


if __name__ == "__main__":
    main()
