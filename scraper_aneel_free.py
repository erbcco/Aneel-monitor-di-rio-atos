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
        self.headers = {
            'User-Agent': 'Mozilla/5.0'
        }
        self.palavras_chave = [
            "Diamante", "Diamante Energia", "Diamante Geração", "Diamante Comercializadora de Energia",
            "Porto do Pecem", "P. Pecem", "Pecem", "Pecem Energia",
            "Consulta Pública", "Tomada de Subsídio", "CVU", "CER", "Portaria",
            "Lacerda", "J. Lacerda", "Jorge Lacerda", "CTJL",
            "UTLA", "UTLB", "UTLC", "exportação de energia", "Termelétrica"
        ]
        self.data_pesquisa = datetime.now().strftime('%d/%m/%Y')
        self.documentos = []

    def buscar_por_termo(self, termo):
        try:
            resp = self.session.get(self.base_url, headers=self.headers)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            viewstate = soup.select_one('input[name="__VIEWSTATE"]')['value']
            eventvalidation = soup.select_one('input[name="__EVENTVALIDATION"]')['value']
            viewstategenerator = soup.select_one('input[name="__VIEWSTATEGENERATOR"]')['value']

            data = {
                '__EVENTTARGET': '',
                '__EVENTARGUMENT': '',
                '__LASTFOCUS': '',
                '__VIEWSTATE': viewstate,
                '__VIEWSTATEGENERATOR': viewstategenerator,
                '__EVENTVALIDATION': eventvalidation,
                'ctl00$Conteudo$txtPalavraChave': termo,
                'ctl00$Conteudo$ddlCampoPesquisa': 'Todos os campos',
                'ctl00$Conteudo$ddlTipoPesquisa': 'avancada',
                'ctl00$Conteudo$txtDataInicio': self.data_pesquisa,
                'ctl00$Conteudo$txtDataFim': self.data_pesquisa,
                'ctl00$Conteudo$btnPesquisar': 'Buscar'
            }

            resp_post = self.session.post(self.base_url, data=data, headers=self.headers)
            resp_post.raise_for_status()

            nome_arquivo = f"resultado_{termo.replace(' ', '_')}_{self.data_pesquisa.replace('/', '-')}.html"
            with open(nome_arquivo, 'w', encoding='utf-8') as f:
                f.write(resp_post.text)
            logger.info(f"Salvo resultado da busca em {nome_arquivo}")

            docs = self.extrair_documentos(resp_post.text, termo)
            self.documentos.extend(docs)
            return docs
        except Exception as e:
            logger.error(f"Erro na busca do termo '{termo}': {e}")
            return []

    def extrair_documentos(self, html_content, termo):
        documentos = []
        soup = BeautifulSoup(html_content, 'html.parser')
        linhas = soup.select('table.k-grid-table tr')
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
        for termo in self.palavras_chave:
            self.buscar_por_termo(termo)
        logger.info(f"Total documentos encontrados: {len(self.documentos)}")
        self.salvar_resultados()
        if self.documentos:
            self.enviar_email_resultados()
        else:
            logger.info("Nenhum documento relevante encontrado, e-mail não enviado.")

    def salvar_resultados(self):
        resultados = {
            "estatisticas": {
                "total_termos_buscados": len(self.palavras_chave),
                "total_documentos_encontrados": len(self.documentos),
                "data_execucao": datetime.now().isoformat()
            },
            "documentos_relevantes": self.documentos,
            "todos_documentos": self.documentos
        }
        with open("resultados_aneel.json", "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2)
        logger.info("Resultados salvos em resultados_aneel.json")

    def enviar_email_resultados(self):
        try:
            import os
            remetente = os.getenv("GMAIL_USER")
            senha = os.getenv("GMAIL_APP_PASSWORD")
            destinatario = os.getenv("EMAIL_DESTINATARIO")
            assunto = f"Resultados do Monitoramento ANEEL - {datetime.now().strftime('%d/%m/%Y %H:%M')}"

            corpo = "Foram encontrados os seguintes documentos relevantes:\n\n"
            for doc in self.documentos:
                corpo += f"- {doc['titulo']}: {doc['url']}\n"

            msg = MIMEMultipart()
            msg['From'] = remetente
            msg['To'] = destinatario
            msg['Subject'] = assunto
            msg.attach(MIMEText(corpo, 'plain'))

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(remetente, senha)
            server.sendmail(remetente, destinatario, msg.as_string())
            server.quit()
            logger.info(f"E-mail enviado para {destinatario}")
        except Exception as e:
            logger.error(f"Erro ao enviar e-mail: {e}")

def main():
    logger.info("Iniciando o monitoramento gratuito ANEEL...")
    scraper = AneelScraperFree()
    scraper.executar_consulta_completa()
    logger.info("Monitoramento finalizado.")

if __name__ == "__main__":
    main()
