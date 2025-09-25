import requests
from bs4 import BeautifulSoup
import logging
from datetime import datetime

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def main():
    url = "https://biblioteca.aneel.gov.br/Busca/Avancada"
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
        "Referer": url,
        "Origin": "https://biblioteca.aneel.gov.br"
    }
    resp = session.get(url, headers=headers)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    viewstate = soup.find("input", id="__VIEWSTATE")
    validation = soup.find("input", id="__EVENTVALIDATION")
    generator = soup.find("input", id="__VIEWSTATEGENERATOR")

    if not (viewstate and validation and generator):
        logger.error("Campos ocultos não encontrados.")
        return

    hoje = datetime.now().strftime("%d/%m/%Y")

    data = {
        "__VIEWSTATE": viewstate["value"],
        "__EVENTVALIDATION": validation["value"],
        "__VIEWSTATEGENERATOR": generator["value"],
        "ctl00$Conteudo$txtPalavraChave": "Portaria",
        "ctl00$Conteudo$ddlCampoPesquisa": "Todos",
        "ctl00$Conteudo$ddlTipoPesquisa": "avancada",
        "ctl00$Conteudo$txtDataInicio": hoje,
        "ctl00$Conteudo$txtDataFim": hoje,
        "ctl00$Conteudo$btnPesquisar": "Buscar"
    }

    post_resp = session.post(url, headers=headers, data=data)
    post_resp.raise_for_status()

    logger.debug(f"Tamanho resposta POST: {len(post_resp.text)}")
    with open("resultado.html", "w", encoding="utf-8") as f:
        f.write(post_resp.text)
    logger.info("Arquivo resultardo.html salvo para análise")

    soup = BeautifulSoup(post_resp.text, "html.parser")
    table = soup.find("table", class_="k-grid-table")
    if not table:
        logger.warning("Tabela de resultados não encontrada na página")
    else:
        rows = table.find_all("tr")[1:]
        logger.info(f"{len(rows)} resultados encontrados")
        for r in rows:
            cols = r.find_all("td")
            title = cols[1].get_text(strip=True)
            link = cols[1].find("a")["href"]
            logger.info(f"Título: {title}, Link: https://biblioteca.aneel.gov.br{link}")

if __name__ == "__main__":
    main()
