import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import logging
import os

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

            # Salvando HTML da primeira resposta para debug
            with open('debug_resposta_busca.html', 'w', encoding='utf-8') as debug_file:
                debug_file.write(html)
            logger.info("HTML da resposta inicial salvo em debug_resposta_busca.html")

            match = re.search(r"window\.location\s*=\s*'(/Resultado/ListarLegislacao\?guid=[^']+)'", html)
            if not match:
                logger.warning(f"GUID não encontrado para termo: {termo}")
                return []
            url_resultados = "https://biblioteca.aneel.gov.br" + match.group(1)
            logger.info(f"URL resultados: {url_resultados}")

            response_result = requests.get(url_resultados, headers=self.headers, timeout=30)
            response_result.raise_for_status()

            nome_arquivo = f'pagina_resultados_{termo.replace(" ", "_")}.html'
            nome_arquivo = os.path.abspath(nome_arquivo)
            logger.info(f"Salvando arquivo HTML completo: {nome_arquivo}")

            with open(nome_arquivo, 'w', encoding='utf-8') as f:
                f.write(response_result.text)

            self.contador_arquivos_html += 1
            logger.info(f"Arquivo salvo com sucesso: {nome_arquivo} (Total arquivos HTML salvos: {self.contador_arquivos_html})")

            soup_result = BeautifulSoup(response_result.content, 'html.parser')
            documentos = self.extrair_documentos(soup_result, termo)  # Implemente este método conforme a extração necessária
            return documentos
        except Exception as e:
            logger.error(f"Erro ao buscar '{termo}': {e}")
            return []

    def executar_consulta_completa(self):
        resultados = {
            "estatisticas": {
                "total_termos_buscados": len(self.palavras_chave),
                "total_documentos_encontrados": 0,
                "documentos_por_categoria": {categoria: 0 for categoria in self.categorias},
                "documentos_relevantes": 0,
                "data_execucao": datetime.now().isoformat()
            },
            "documentos_relevantes": [],
            "todos_documentos": []
        }

        for termo in self.palavras_chave:
            documentos = self.buscar_por_termo(termo)
            resultados["todos_documentos"].extend(documentos)
            resultados["estatisticas"]["total_documentos_encontrados"] += len(documentos)
            # Atualize categorias e relevantes conforme sua lógica

        return resultados

    # Implemente outros métodos necessários como extrair_documentos, construção de URLs completas, etc.

def main():
    logger.info("Iniciando o monitoramento gratuito ANEEL...")
    scraper = AneelScraperFree()
    resultado = scraper.executar_consulta_completa()
    logger.info(f"Consulta finalizada. Documentos encontrados: {resultado['estatisticas']['total_documentos_encontrados']}")
    logger.info(f"Documentos relevantes para envio: {resultado['estatisticas']['documentos_relevantes']}")

if __name__ == "__main__":
    main()
