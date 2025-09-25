import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def teste_gravar_arquivo():
    cwd = os.getcwd()
    logger.info(f"Diretório atual: {cwd}")
    try:
        nome_arquivo = os.path.join(cwd, 'teste_gravacao_simples.html')
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            f.write('<html><body>Conteúdo de teste</body></html>')
        logger.info(f"Arquivo '{nome_arquivo}' salvo com sucesso.")
    except Exception as e:
        logger.error(f"Falha ao salvar arquivo: {e}")

if __name__ == "__main__":
    teste_gravar_arquivo()
