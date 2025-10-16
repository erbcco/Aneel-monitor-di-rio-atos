import asyncio, traceback, json, os, smtplib, re, logging
from datetime import datetime
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scraper_aneel")
fh = logging.FileHandler("scraper.log", encoding="utf-8")
fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(fh)

PALAVRAS_CHAVE=["Portaria"]

async def buscar_termo(page, termo, data_pesquisa):
    logger.info(f"Busca: {termo} em {data_pesquisa}")
    await page.goto("https://biblioteca.aneel.gov.br/Busca/Avancada", wait_until="networkidle")
    await page.fill('input[name="LegislacaoPalavraChave"]', termo)
    await page.select_option('select[name="LegislacaoTipoFiltroDataPublicacao"]', label="Igual a")
    await page.fill('input[name="LegislacaoDataPublicacao1"]', data_pesquisa)
    logger.info("Campos preenchidos")
    await page.click('button:has-text("Buscar")')
    # Espera resultados renderizarem
    await page.wait_for_selector('div.ficha-acervo-detalhe', timeout=20000)
    await page.wait_for_timeout(2000)
    content=await page.content()
    with open("resultado_Portaria.html","w",encoding="utf-8") as f: f.write(content)
    logger.info("Salvo resultado_Portaria.html")
    return content

def extrair_documentos(content, data_busca):
    logger.info("Extraindo documentos")
    soup=BeautifulSoup(content,"html.parser")
    fichas=soup.select("div.ficha-acervo-detalhe")
    logger.info(f"{len(fichas)} fichas encontradas")
    docs=[]
    for i,f in enumerate(fichas,1):
        d={}
        t=f.select_one("p.titulo")
        if t: d["titulo"]=t.get_text(strip=True)
        a=f.select_one("p.assinatura")
        if a:
            m=re.search(r"\d{2}/\d{2}/\d{4}",a.get_text())
            if m: d["data_assinatura"]=m.group(0)
        p=f.select_one("p.publicacao")
        if p:
            m=re.search(r"\d{2}/\d{2}/\d{4}",p.get_text())
            if m: d["data_publicacao"]=m.group(0)
        e=f.select_one("div.texto-html-container")
        if e: d["ementa"]=e.get_text(strip=True)
        s=f.select_one("p.assunto")
        if s: d["assunto"]=s.get_text(strip=True).replace("Assunto","").strip()
        for sp in f.select("p.sites"):
            r=sp.select_one("span.rotulo")
            a2=sp.select_one("a")
            if r and a2:
                text=r.get_text(strip=True)
                href=a2["href"]
                if "Texto Integral" in text: d["link_texto_integral"]=href
                if ("Nota" in text or "Voto" in text): d["link_nota_tecnica"]=href
        d["data_busca"]=data_busca
        if "link_texto_integral" in d:
            docs.append(d)
            logger.info(f"Doc {i} extraído")
    return docs

def enviar_email(docs):
    user=os.getenv("GMAIL_USER"); pwd=os.getenv("GMAIL_APP_PASSWORD"); dest=os.getenv("EMAIL_DESTINATARIO")
    if not user or not pwd or not dest:
        logger.error("Faltam credenciais")
        return
    subj=f"ANEEL {datetime.now().strftime('%d/%m/%Y')} - {len(docs)} doc"
    body=f"Total: {len(docs)}\n\n" + "\n".join(f"{i+1}. {d.get('titulo','')} - {d.get('link_texto_integral','')}" for i,d in enumerate(docs))
    msg=MIMEMultipart(); msg["From"]=user; msg["To"]=dest; msg["Subject"]=subj
    msg.attach(MIMEText(body,"plain","utf-8"))
    try:
        with smtplib.SMTP("smtp.gmail.com",587) as s:
            s.starttls(); s.login(user,pwd); s.send_message(msg)
        logger.info("E-mail enviado!")
    except Exception as e:
        logger.error(f"Erro envio: {e}\n{traceback.format_exc()}")

async def main_async():
    data=datetime.now().strftime("%d/%m/%Y")
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        page=await browser.new_page()
        content=await buscar_termo(page, "Portaria", data)
        await browser.close()
    docs=extrair_documentos(content, data)
    with open("resultados_aneel.json","w",encoding="utf-8") as f:
        json.dump({"data":data,"total":len(docs),"docs":docs},f,ensure_ascii=False,indent=2)
    if docs: enviar_email(docs)
    else: logger.info("Nenhum documento encontrado")

def main(): asyncio.run(main_async())
if __name__=="__main__": main()
