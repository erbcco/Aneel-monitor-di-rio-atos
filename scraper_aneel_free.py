import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AneelScraperFree:

    def __init__(self):
        self.base_url = "https://biblioteca.aneel.gov.br/Busca/Avancada"
        self.session = requests.Session()

        # Cabeçalhos comuns para simular navegador real
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ' +
                          'AppleWebKit/537.36 (KHTML, like Gecko) ' +
                          'Chrome/116.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': self.base_url,
            'Origin': 'https://biblioteca.aneel.gov.br',
        })

        # Lista de palavras-chave monitoradas
        self.palavras_chave = [
            "Diamante", "Pecem", "Lacerda", "CTJL", "UTLA", "UTLB", "UTLC",
            "CVU", "CER", "Portaria", "exportação", "Termelétrica",
            "Consulta Pública", "Tomada de Subsídio"
        ]
        self.data_pesquisa = datetime.now().strftime('%d/%m/%Y')
        self.documentos = []

    def buscar_por_termo(self, termo):
        logger.info(f"Buscando termo: '{termo}'")

        resp = self.session.get(self.base_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Campos ocultos essenciais para o POST
        viewstate = soup.select_one('input[name="__VIEWSTATE"]')
        eventvalidation = soup.select_one('input[name="__EVENTVALIDATION"]')
        viewstategenerator = soup.select_one('input[name="__VIEWSTATEGENERATOR"]')

        if not all([viewstate, eventvalidation, viewstategenerator]):
            logger.error("Campos __VIEWSTATE, __EVENTVALIDATION ou __VIEWSTATEGENERATOR não encontrados.")
            return []

        data = {
            '__EVENTTARGET': '',
            '__EVENTARGUMENT': '',
            '__LASTFOCUS': '',
            '__VIEWSTATE': viewstate['value'],
            '__VIEWSTATEGENERATOR': viewstategenerator['value'],
            '__EVENTVALIDATION': eventvalidation['value'],
            'ctl00$Conteudo$txtPalavraChave': termo,
            'ctl00$Conteudo$ddlCampoPesquisa': 'Todos os campos',
            'ctl00$Conteudo$ddlTipoPesquisa': 'avancada',
            'ctl00$Conteudo$txtDataInicio': self.data_pesquisa,
            'ctl00$Conteudo$txtDataFim': self.data_pesquisa,
            'ctl00$Conteudo$btnPesquisar': 'Buscar'
        }

        post_resp = self.session.post(self.base_url, data=data)
        post_resp.raise_for_status()

        logger.info(f"Tamanho do HTML recebido: {len(post_resp.text)} caracteres")

        # Salvar HTML (.html fixo) para análise
        nome_arquivo = 'resultado_busca_aneel_teste.html'
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            f.write(post_resp.text)
        logger.info(f"Arquivo HTML salvo: {nome_arquivo}")

        documentos = self.extrair_documentos(post_resp.text, termo)
        logger.info(f"Documentos encontrados para '{termo}': {len(documentos)}")

        self.documentos.extend(documentos)
        return documentos

    def extrair_documentos(self, html, termo):
        documentos = []
        soup = BeautifulSoup(html, 'html.parser')
        linhas = soup.select('table.k-grid-table tr')

        if not linhas:
            logger.warning(f"Nenhuma linha encontrada para o termo '{termo}'")

        for linha in linhas[1:]:
            colunas = linha.find_all('td')
            if len(colunas) >= 2:
                titulo = colunas[1].get_text(strip=True)
                link_tag = colunas[1].find('a')
                url_relativa = link_tag['href'] if link_tag and 'href' in link_tag.attrs else None
                url_completa = f"https://biblioteca.aneel.gov.br{url_relativa}" if url_relativa else None
                documentos.append({"termo": termo, "titulo": titulo, "url": url_completa})

        return documentos

    def executar_consulta_completa(self):
        logger.info("Iniciando consulta completa...")
        for termo in self.palavras_chave:
            self.buscar_por_termo(termo)

        logger.info(f"Total documentos encontrados: {len(self.documentos)}")
        self.salvar_resultados()

        if self.documentos:
            self.enviar_email_resultados()
        else:
            logger.info("Nenhum documento relevante encontrado.")

    def salvar_resultados(self):
        resultados = {
            "estatisticas": {
                "total_termos_buscados": len(self.palavras_chave),
                "total_documentos_encontrados": len(self.documentos),
                "data_execucao": datetime.now().isoformat()
            },
            "documentos_relevantes": self.documentos
        }
        with open("resultados_aneel.json", "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        logger.info("Resultados salvos em resultados_aneel.json")

    def enviar_email_resultados(self):
        try:
            remetente = os.getenv("GMAIL_USER")
            senha = os.getenv("GMAIL_APP_PASSWORD")
            destinatario = os.getenv("EMAIL_DESTINATARIO")

            if not remetente or not senha or not destinatario:
                logger.error("Credenciais de e-mail não configuradas corretamente")
                return

            assunto = f"Resultados do Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            
            corpo = "Documentos relevantes encontrados:\n\n"
            for doc in self.documentos:
                corpo += f"- {doc['titulo']}: {doc['url']}\n"

            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = destinatario
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))

            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(remetente, senha)
                server.sendmail(remetente, destinatario, msg.as_string())

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
