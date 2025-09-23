import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AneelScraperFree:
    def __init__(self):
        self.base_url = "https://biblioteca.aneel.gov.br/Busca/Avancada"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Palavras-chave específicas fornecidas
        self.palavras_chave = [
            "Diamante", "Diamante Energia", "Diamante Geração",
            "Porto do Pecém I", "P. Pecém", "Pecém", "Pecem",
            "Consulta Pública", "Tomada de Subsídio", "CVU", "CER",
            "Lacerda", "J. Lacerda", "Jorge Lacerda", "CTJL",
            "UTLA", "UTLB", "UTLC", "exportação de energia"
            "Portaria", "Diamante Comercializadora de Energia"
        ]
        
        # Categorização para análise
        self.categorias = {
            "Diamante_Energia": ["Diamante", "Diamante Energia", "Diamante Geração"],
            "Porto_Pecem": ["Porto do Pecém I", "P. Pecém", "Pecém", "Pecem"],
            "Jorge_Lacerda": ["Lacerda", "J. Lacerda", "Jorge Lacerda", "CTJL", "UTLA", "UTLB", "UTLC"],
            "Processos_Regulatorios": ["Consulta Pública", "Tomada de Subsídio", "CVU", "CER"],
            "Comercializacao": ["exportação de energia"]
        }
    
    def buscar_por_termo(self, termo):
        """Busca individual por termo específico"""
        params = {
            'guid': '4aa5bd4e1cb771e263ab',
            'campo1': 'Todos os campos',
            'termo1': termo,
            'conectivo1': 'E'
        }
        
        try:
            logger.info(f"Buscando: {termo}")
            response = requests.get(self.base_url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            documentos = self.extrair_documentos(soup, termo)
            
            # Delay para não sobrecarregar o servidor
            time.sleep(2)
            
            return documentos
            
        except Exception as e:
            logger.error(f"Erro ao buscar '{termo}': {e}")
            return []
    
    def extrair_documentos(self, soup, termo_busca):
        """Extrai documentos da página de resultados"""
        documentos = []
        
        # Tentar diferentes seletores para encontrar resultados
        possíveis_seletores = [
            '.resultado-item',
            '.resultado',
            '.item-resultado',
            '.document-item',
            'div[class*="result"]',
            'tr[class*="result"]'
        ]
        
        resultados = []
        for seletor in possíveis_seletores:
            elementos = soup.select(seletor)
            if elementos:
                resultados = elementos
                break
        
        # Se não encontrou seletores específicos, buscar por padrões
        if not resultados:
            # Buscar por links que contenham padrões típicos da ANEEL
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                texto = link.get_text().strip()
                
                if any(pattern in href.lower() for pattern in ['documento', 'resolucao', 'despacho']) or \
                   any(pattern in texto.lower() for pattern in ['resolução', 'despacho', 'consulta']):
                    
                    documento = {
                        'titulo': texto[:200] if texto else 'Documento encontrado',
                        'url': self.construir_url_completa(href),
                        'tipo': self.identificar_tipo(texto),
                        'termo_busca': termo_busca,
                        'data_encontrado': datetime.now().strftime('%Y-%m-%d'),
                        'relevancia': self.calcular_relevancia(texto, termo_busca)
                    }
                    documentos.append(documento)
        
        # Processar resultados encontrados com seletores
        for resultado in resultados[:10]:  # Limitar a 10 por busca
            try:
                # Tentar extrair título
                titulo_elem = resultado.find(['h1', 'h2', 'h3', 'h4', 'a']) or resultado
                titulo = titulo_elem.get_text().strip() if titulo_elem else "Título não encontrado"
                
                # Tentar extrair URL
                link_elem = resultado.find('a', href=True)
                url = self.construir_url_completa(link_elem.get('href')) if link_elem else ""
                
                documento = {
                    'titulo': titulo[:200],
                    'url': url,
                    'tipo': self.identificar_tipo(titulo),
                    'termo_busca': termo_busca,
                    'data_encontrado': datetime.now().strftime('%Y-%m-%d'),
                    'relevancia': self.calcular_relevancia(titulo, termo_busca),
                    'categoria': self.identificar_categoria(termo_busca)
                }
                
                documentos.append(documento)
                
            except Exception as e:
                logger.warning(f"Erro ao processar resultado individual: {e}")
                continue
        
        logger.info(f"Encontrados {len(documentos)} documentos para '{termo_busca}'")
        return documentos
    
    def construir_url_completa(self, href):
        """Constrói URL completa a partir de href relativo"""
        if not href:
            return ""
        
        if href.startswith('http'):
            return href
        elif href.startswith('/'):
            return f"https://biblioteca.aneel.gov.br{href}"
        else:
            return f"https://biblioteca.aneel.gov.br/{href}"
    
    def identificar_tipo(self, titulo):
        """Identifica tipo do documento pelo título"""
        titulo_lower = titulo.lower()
        
        tipos = {
            'resolução': 'Resolução Normativa',
            'despacho': 'Despacho Regulatório',
            'consulta pública': 'Consulta Pública',
            'audiência': 'Audiência Pública',
            'tomada de subsídio': 'Tomada de Subsídio',
            'cvv': 'CVU - Custo Variável Unitário',
            'cer': 'CER - Certificado de Energia Renovável',
            'relatório': 'Relatório',
            'ata': 'Ata de Reunião'
        }
        
        for palavra, tipo in tipos.items():
            if palavra in titulo_lower:
                return tipo
        
        return 'Documento Regulatório'
    
    def calcular_relevancia(self, titulo, termo_busca):
        """Calcula relevância baseada em critérios específicos"""
        titulo_lower = titulo.lower()
        termo_lower = termo_busca.lower()
        
        # Alta relevância
        if any(palavra in titulo_lower for palavra in [
            'resolução normativa', 'despacho', 'consulta pública',
            'audiência pública', 'tomada de subsídio'
        ]):
            return 'alta'
        
        # Média relevância
        if termo_lower in titulo_lower:
            return 'média'
        
        return 'baixa'
    
    def identificar_categoria(self, termo_busca):
        """Identifica categoria do termo buscado"""
        for categoria, termos in self.categorias.items():
            if termo_busca in termos:
                return categoria
        return 'Outros'
    
    def executar_consulta_completa(self):
        """Executa busca para todos os termos"""
        logger.info("Iniciando consulta completa ANEEL...")
        
        todos_documentos = []
        estatisticas = {
            'total_termos_buscados': len(self.palavras_chave),
            'total_documentos_encontrados': 0,
            'documentos_por_categoria': {},
            'documentos_relevantes': 0,
            'data_execucao': datetime.now().isoformat()
        }
        
        # Buscar por cada termo individualmente
        for termo in self.palavras_chave:
            documentos = self.buscar_por_termo(termo)
            todos_documentos.extend(documentos)
            
            # Atualizar estatísticas
            categoria = self.identificar_categoria(termo)
            if categoria not in estatisticas['documentos_por_categoria']:
                estatisticas['documentos_por_categoria'][categoria] = 0
            estatisticas['documentos_por_categoria'][categoria] += len(documentos)
        
        # Remover duplicatas baseado em título
        documentos_unicos = []
        titulos_vistos = set()
        
        for doc in todos_documentos:
            titulo_normalizado = doc['titulo'].lower().strip()
            if titulo_normalizado not in titulos_vistos and len(titulo_normalizado) > 10:
                documentos_unicos.append(doc)
                titulos_vistos.add(titulo_normalizado)
        
        # Filtrar apenas relevantes
        documentos_relevantes = [d for d in documentos_unicos if d['relevancia'] in ['alta', 'média']]
        
        # Atualizar estatísticas finais
        estatisticas['total_documentos_encontrados'] = len(documentos_unicos)
        estatisticas['documentos_relevantes'] = len(documentos_relevantes)
        
        # Preparar resultado final
        resultado = {
            'estatisticas': estatisticas,
            'documentos_relevantes': documentos_relevantes[:20],  # Máximo 20 mais relevantes
            'todos_documentos': documentos_unicos
        }
        
        # Salvar resultado
        self.salvar_resultados(resultado)
        
        # Enviar email se houver documentos relevantes
        if documentos_relevantes:
            self.enviar_email_gratuito(resultado)
            logger.info(f"Email enviado! Encontrados {len(documentos_relevantes)} documentos relevantes")
        else:
            logger.info("Nenhum documento relevante encontrado")
        
        return resultado
    
    def salvar_resultados(self, resultado):
        """Salva resultados em arquivo JSON"""
        try:
            with open('resultados_aneel.json', 'w', encoding='utf-8') as f:
                json.dump(resultado, f, ensure_ascii=False, indent=2)
            logger.info("Resultados salvos em resultados_aneel.json")
        except Exception as e:
            logger.error(f"Erro ao salvar arquivo: {e}")
    
    def enviar_email_gratuito(self, resultado):
        """Envia email usando Gmail SMTP gratuito"""
        # Configurações do email (via variáveis de ambiente)
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
        email_user = os.getenv('GMAIL_USER')  # seu.email@gmail.com
        email_pass = os.getenv('GMAIL_APP_PASSWORD')  # senha de app do Gmail
        email_to = os.getenv('EMAIL_DESTINATARIO')  # destinatario@email.com
        
        if not all([email_user, email_pass, email_to]):
            logger.warning("Configurações de email não definidas nas variáveis de ambiente")
            return False
        
        try:
            # Criar mensagem
            msg = MIMEMultipart()
            msg['From'] = email_user
            msg['To'] = email_to
            msg['Subject'] = f"[ANEEL] Monitoramento Diário - {datetime.now().strftime('%d/%m/%Y')}"
            
            # Preparar corpo do email
            stats = resultado['estatisticas']
            docs_relevantes = resultado['documentos_relevantes']
            
            corpo = f"""
📊 RELATÓRIO DIÁRIO - ANEEL
Data: {datetime.now().strftime('%d/%m/%Y às %H:%M')}

🔍 ESTATÍSTICAS DA CONSULTA:
• Termos pesquisados: {stats['total_termos_buscados']}
• Documentos encontrados: {stats['total_documentos_encontrados']}
• Documentos relevantes: {stats['documentos_relevantes']}

📋 DOCUMENTOS POR CATEGORIA:
"""
            
            for categoria, quantidade in stats['documentos_por_categoria'].items():
                corpo += f"• {categoria.replace('_', ' ')}: {quantidade}\n"
            
            if docs_relevantes:
                corpo += f"\n🎯 DOCUMENTOS MAIS RELEVANTES ({len(docs_relevantes)}):\n\n"
                
                for i, doc in enumerate(docs_relevantes[:10], 1):  # Top 10
                    corpo += f"{i}. {doc['titulo']}\n"
                    corpo += f"   Tipo: {doc['tipo']}\n"
                    corpo += f"   Categoria: {doc['categoria']}\n"
                    corpo += f"   Relevância: {doc['relevancia']}\n"
                    if doc['url']:
                        corpo += f"   URL: {doc['url']}\n"
                    corpo += "\n"
            
            corpo += """
⚡ Sistema de monitoramento automático
🆓 Executado gratuitamente via GitHub Actions
📧 Email enviado via Gmail SMTP gratuito
"""
            
            msg.attach(MIMEText(corpo, 'plain', 'utf-8'))
            
            # Enviar email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
            server.quit()
            
            logger.info("✅ Email enviado com sucesso!")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erro ao enviar email: {e}")
            return False

def main():
    """Função principal"""
    print("🚀 Iniciando ANEEL Scraper Gratuito...")
    
    scraper = AneelScraperFree()
    resultado = scraper.executar_consulta_completa()
    
    print(f"✅ Consulta finalizada!")
    print(f"📊 Documentos encontrados: {resultado['estatisticas']['total_documentos_encontrados']}")
    print(f"🎯 Documentos relevantes: {resultado['estatisticas']['documentos_relevantes']}")

if __name__ == "__main__":
    main()
