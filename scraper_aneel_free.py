import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging

try:
    from zoneinfo import ZoneInfo
    brasilia_tz = ZoneInfo("America/Sao_Paulo")
except ImportError:
    import pytz
    brasilia_tz = pytz.timezone("America/Sao_Paulo")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AneelScraperFree:
    def __init__(self):
        self.base_url = "https://biblioteca.aneel.gov.br/Busca/Avancada"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        }
        self.palavras_chave = [
            "Diamante", "Diamante Energia", "Diamante Geração", "Diamante Comercializadora de Energia",
            "Porto do Pecem", "P. Pecem", "Pecem", "Pecem Energia",
            "Consulta Pública", "Tomada de Subsídio", "CVU", "CER", "Portaria MME",
            "Lacerda", "J. Lacerda", "Jorge Lacerda", "CTJL",
            "UTLA", "UTLB", "UTLC", "exportação de energia", "Termelétrica"
        ]
        self.categorias = {
            "Diamante_Energia": ["Diamante", "Diamante Energia", "Diamante Geração", "Diamante Comercializadora de Energia"],
            "Porto_Pecem": ["Porto do Pecem", "P. Pecem", "Pecem", "Pecem Energia"],
            "Jorge_Lacerda": ["Lacerda", "J. Lacerda", "Jorge Lacerda", "CTJL", "UTLA", "UTLB", "UTLC"],
            "Processos_Regulatorios": ["Consulta Pública", "Tomada de Subsídio", "CVU", "CER", "Portaria MME"],
            "Comercializacao": ["exportação de energia", "Termelétrica"]
        }
        self.data_pesquisa = datetime.now(brasilia_tz).strftime('%d/%m/%Y')
        self.contador_arquivos_html = 0

    def buscar_por_termo(self, termo):
        params = {
            'aba': 'Legislacao',
            'tipoPesquisa': 'avancada',
            'campoTexto1': 'Todos os campos',
            'operadorTexto1': 'E',
            'termoTexto1': termo,
            'campoData': 'Publicacao',
            'dataInicio': self.data_pesquisa,
            'dataFim': self.data_pesquisa,
            'paginaAtual': '1',
            'numeroRegistros': '10'
        }
        try:
            logger.info(f"Buscando: {termo} na data {self.data_pesquisa}")
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            html = response.text

            match = re.search(r"window\.location\s*=\s*'(/Resultado/ListarLegislacao\?guid=[^']+)'", html)
            if not match:
                logger.warning(f"GUID não encontrado para termo: {termo}")
                return []
            url_resultados = "https://biblioteca.aneel.gov.br" + match.group(1)
            logger.info(f"URL resultados: {url_resultados}")

            response_result = requests.get(url_resultados, headers=self.headers, timeout=30)
            response_result.raise_for_status()

            workspace = os.getenv('GITHUB_WORKSPACE', '.')
            nome_arquivo = os.path.join(workspace, f'pagina_resultados_{termo.replace(" ", "_")}.html')
            logger.info(f"Salvando arquivo HTML: {nome_arquivo}")

            with open(nome_arquivo, 'w', encoding='utf-8') as f:
                f.write(response_result.text)

            self.contador_arquivos_html += 1
            logger.info(f"Arquivo salvo com sucesso: {nome_arquivo} (Total arquivos HTML salvos: {self.contador_arquivos_html})")

            soup_result = BeautifulSoup(response_result.content, 'html.parser')
            documentos = self.extrair_documentos(soup_result, termo)
            return documentos
        except Exception as e:
            logger.error(f"Erro ao buscar '{termo}': {e}")
            return []

    def extrair_documentos(self, soup, termo_busca):
        documentos = []
        resultados = soup.select('div.col-md-10 > a')
        if not resultados:
            logger.warning("Nenhum documento encontrado nos seletores testados.")
        for resultado in resultados[:10]:
            try:
                titulo = resultado.get_text(strip=True)
                href = resultado.get('href')
                url = self.construir_url_completa(href)
                documento = {
                    'titulo': titulo[:200],
                    'url': url,
                    'tipo': self.identificar_tipo(titulo),
                    'termo_busca': termo_busca,
                    'data_encontrado': datetime.now(brasilia_tz).strftime('%Y-%m-%d %H:%M:%S'),
                    'relevancia': self.calcular_relevancia(titulo, termo_busca),
                    'categoria': self.identificar_categoria(termo_busca)
                }
                documentos.append(documento)
            except Exception as e:
                logger.warning(f"Erro ao processar documento: {e}")
                continue
        logger.info(f"{len(documentos)} atos encontrados para o termo '{termo_busca}'.")
        return documentos

    def construir_url_completa(self, href):
        if not href:
            return ""
        if href.startswith('http'):
            return href
        if href.startswith('/'):
            return f"https://biblioteca.aneel.gov.br{href}"
        return f"https://biblioteca.aneel.gov.br/{href}"

    def identificar_tipo(self, titulo):
        titulo_lower = titulo.lower()
        tipos = {
            'resolução': 'Resolução Normativa',
            'despacho': 'Despacho Regulatório',
            'consulta pública': 'Consulta Pública',
            'audiência': 'Audiência Pública',
            'tomada de subsídio': 'Tomada de Subsídio',
            'cvu': 'CVU - Custo Variável Unitário',
            'cer': 'CER - Contrato de Energia de Reserva',
            'relatório': 'Relatório',
            'ata': 'Ata de Reunião'
        }
        for chave, valor in tipos.items():
            if chave in titulo_lower:
                return valor
        return 'Documento Regulatório'

    def calcular_relevancia(self, titulo, termo_busca):
        titulo_lower = titulo.lower()
        termo_lower = termo_busca.lower()
        if any(pal in titulo_lower for pal in [
            'resolução normativa', 'despacho', 'consulta pública',
            'audiência pública', 'tomada de subsídio'
        ]):
            return 'alta'
        if termo_lower in titulo_lower:
            return 'média'
        return 'baixa'

    def identificar_categoria(self, termo_busca):
        for categoria, termos in self.categorias.items():
            if termo_busca in termos:
                return categoria
        return 'Outros'

    def executar_consulta_completa(self):
        logger.info("Iniciando consulta completa ANEEL...")
        todos_documentos, estatisticas = [], {
            'total_termos_buscados': len(self.palavras_chave),
            'total_documentos_encontrados': 0,
            'documentos_por_categoria': {},
            'documentos_relevantes': 0,
            'data_execucao': datetime.now(brasilia_tz).isoformat()
        }
        for termo in self.palavras_chave:
            doc = self.buscar_por_termo(termo)
            todos_documentos.extend(doc)
            categoria = self.identificar_categoria(termo)
            estatisticas['documentos_por_categoria'][categoria] = estatisticas['documentos_por_categoria'].get(categoria, 0) + len(doc)
        doc_unicos, titulos_vistos = [], set()
        for d in todos_documentos:
            titulo = d['titulo'].lower().strip()
            if titulo not in titulos_vistos and len(titulo) > 10:
                doc_unicos.append(d)
                titulos_vistos.add(titulo)
        docs_relevantes = [d for d in doc_unicos if d['relevancia'] in ('alta', 'média')]
        estatisticas['total_documentos_encontrados'] = len(doc_unicos)
        estatisticas['documentos_relevantes'] = len(docs_relevantes)
        resultado = {
            'estatisticas': estatisticas,
            'documentos_relevantes': docs_relevantes[:20],
            'todos_documentos': doc_unicos
        }
        self.salvar_resultados(resultado)
        self.enviar_email_gratuito(resultado)
        logger.info(f"E-mail enviado com {len(docs_relevantes)} documentos relevantes")
        return resultado

    def salvar_resultados(self, resultado):
        try:
            with open('resultados_aneel.json', 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            logger.info("Arquivo resultados_aneel.json salvo com sucesso.")
        except Exception as e:
            logger.error(f"Erro ao salvar resultados: {e}")

    def enviar_email_gratuito(self, resultado):
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        email_user = os.getenv('GMAIL_USER')
        email_pass = os.getenv('GMAIL_APP_PASSWORD')
        email_to = os.getenv('EMAIL_DESTINATARIO')
        if not all([email_user, email_pass, email_to]):
            logger.warning("Variáveis de ambiente de email não configuradas corretamente.")
            return False
        try:
            msg = MIMEMultipart()
            msg['From'] = email_user
            msg['To'] = email_to
            msg['Subject'] = f"[ANEEL] Monitoramento Diário - {datetime.now(brasilia_tz).strftime('%d/%m/%Y')}"
            stats = resultado['estatisticas']
            docs_relevantes = resultado['documentos_relevantes']
            corpo = f"""
📊 RELATÓRIO DIÁRIO - ANEEL
Data: {datetime.now(brasilia_tz).strftime('%d/%m/%Y às %H:%M')}

🔍 ESTATÍSTICAS DA CONSULTA:
• Termos pesquisados: {stats['total_termos_buscados']}
• Documentos encontrados: {stats['total_documentos_encontrados']}
• Documentos relevantes: {stats['documentos_relevantes']}

📋 DOCUMENTOS POR CATEGORIA:
"""
            for cat, qtd in stats['documentos_por_categoria'].items():
                corpo += f"• {cat.replace('_', ' ')}: {qtd}\n"
            if docs_relevantes:
                corpo += f"\n🎯 DOCUMENTOS MAIS RELEVANTES ({len(docs_relevantes)}):\n\n"
                for i, doc in enumerate(docs_relevantes[:10], 1):
                    corpo += f"{i}. {doc['titulo']}\n"
                    corpo += f"   Tipo: {doc['tipo']}\n"
                    corpo += f"   Categoria: {doc['categoria']}\n"
                    corpo += f"   Relevância: {doc['relevancia']}\n"
                    corpo += f"   URL: {doc['url']}\n\n"
            else:
                corpo += "\n⚠️ Nenhum ato publicado ou correspondente aos termos pesquisados para o dia.\n"
            corpo += """
⚡ Sistema automático de monitoramento
🆓 Executado via GitHub Actions
📧 Envio via Gmail SMTP gratuito
"""
            msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
            logger.info("E-mail enviado com sucesso!")
            return True
        except Exception as e:
            logger.error(f"Erro no envio do e-mail: {e}")
            return False

def main():
    logger.info("Iniciando o monitoramento gratuito ANEEL...")
    scraper = AneelScraperFree()
    resultado = scraper.executar_consulta_completa()
    logger.info(f"Consulta finalizada. Documentos encontrados: {resultado['estatisticas']['total_documentos_encontrados']}")
    logger.info(f"Documentos relevantes para envio: {resultado['estatisticas']['documentos_relevantes']}")

if __name__ == "__main__":
    main()
