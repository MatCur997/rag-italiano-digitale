# -*- coding: utf-8 -*-
"""Passo 1 — Verifica dei vincoli di accesso al portale di *Italiano digitale*.

Perimetro: il solo dominio `id.accademiadellacrusca.org`, che e' l'unico da cui
verra' effettuata la raccolta. `robots.txt` vincola per host: interrogare il
sito istituzionale `accademiadellacrusca.it`, che non sara' mai oggetto di
crawl, aggiungerebbe righe al verbale senza aggiungere garanzie.
Le pagine legali *collegate* dal portale vengono comunque archiviate anche se
risiedono su un altro dominio, e in quel caso sono marcate `[fuori dominio]`:
il perimetro documentale e' piu' ampio di quello di raccolta.

Che cosa fa:
  1. scarica robots.txt e sitemap.xml del portale, piu' le pagine che
     regolano l'uso dei contenuti (criteri e norme, codice etico);
  2. scarica la home del portale e ne estrae i collegamenti a pagine legali
     ed editoriali;
  3. scarica quelle pagine;
  4. scarica i documenti allegati alla pagina dei criteri editoriali
     (collegamenti a file, riconosciuti per estensione o per endpoint);
  5. archivia ogni risposta in byte grezzi (nessuna decodifica, nessun BOM,
     nessuna traduzione dei fine riga) e ne calcola lo SHA-256;
  6. scrive un verbale con URL, codice di stato, dimensione, impronta, redirect.

Che cosa NON fa: non scarica schede e non estrae testo. Serve solo a stabilire
se e a quali condizioni la raccolta automatica sia ammessa, e a conservare la
prova documentale di che cosa dichiarasse la fonte alla data di accesso.

La deduplica avviene sull'URL **finale**, dopo i redirect: due indirizzi diversi
che convergono sullo stesso documento vengono archiviati una volta sola.

Idempotente: rieseguirlo sovrascrive i file della stessa data e rigenera il
verbale, senza duplicare nulla.

Uso:  python -m src.ingest.verifica_accesso     (dalla radice del progetto)
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

# --- parametri della raccolta: dichiarati qui, da riportare nel cap. 4 ----
# ATTENZIONE: questo User-Agent deve coincidere alla lettera con quello che
# verra' scritto in config/acquisizione.yaml e usato dal crawl. Un verbale che
# attesta le condizioni d'accesso di un agente diverso da quello che ha
# raccolto il corpus non attesta nulla.
UA = "TesiRAG-Crawler/0.1 (ricerca universitaria; matteo.curiale@students.uniroma2.eu)"
RITARDO = 2.0          # secondi fra una richiesta e l'altra
TIMEOUT = 30.0

PORTALE = "https://id.accademiadellacrusca.org/"
DOMINIO = urlparse(PORTALE).netloc

CRITERI = urljoin(PORTALE, "criteri-e-norme")

URL_BASE = [
    urljoin(PORTALE, "robots.txt"),
    urljoin(PORTALE, "sitemap.xml"),
    CRITERI,
    urljoin(PORTALE, "codice-etico")
]

# parole chiave cercate nel testo e nell'href dei collegamenti della home
CHIAVI = ("note legali", "privacy", "termini", "condizioni", "credit",
          "cookie", "copyright", "licenz", "informativa", "norme", "etico")

# un allegato e' un collegamento a un documento: si riconosce per estensione
# oppure per endpoint di scaricamento
ESTENSIONI = (".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt")
ENDPOINT = ("/File/Download",)

DEST = Path("data/raw/legal")

richieste = 0                 # richieste effettivamente inviate
visti_finali: set[str] = set()  # URL finali gia' archiviati


def nome_file(url: str) -> str:
    """Nome di archiviazione derivato dall'URL, senza caratteri problematici."""
    grezzo = url.split("://", 1)[1]
    return "".join(c if c.isalnum() else "_" for c in grezzo)[:120]


def fuori_dominio(url: str) -> bool:
    """Vero se l'URL non appartiene al dominio del portale."""
    return urlparse(url).netloc != DOMINIO


def marca(url: str) -> str:
    return "[fuori dominio] " if fuori_dominio(url) else ""


def e_allegato(href: str) -> bool:
    percorso = urlparse(href).path.lower()
    return percorso.endswith(ESTENSIONI) or any(e in href for e in ENDPOINT)


def archivia(url: str, r: httpx.Response, stamp: str) -> Path:
    """Scrive i byte grezzi e un file gemello con stato e intestazioni."""
    base = DEST / f"{nome_file(url)}_{stamp}"
    base.with_suffix(".raw").write_bytes(r.content)
    testa = [f"HTTP {r.status_code} {r.reason_phrase}", f"URL finale: {r.url}"]
    testa += [f"{k}: {v}" for k, v in r.headers.items()]
    base.with_suffix(".headers.txt").write_text(
        "\n".join(testa) + "\n", encoding="utf-8", newline="\n")
    return base.with_suffix(".raw")


def scarica(client: httpx.Client, url: str, stamp: str) -> tuple[str, httpx.Response | None]:
    """Scarica un URL, archivia i byte grezzi, restituisce (riga di verbale, risposta)."""
    global richieste
    richieste += 1
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        return f"{marca(url)}{url}  ->  errore di rete: {type(e).__name__}: {e}", None

    finale = str(r.url)
    data_srv = r.headers.get("date", "?")
    tipo = r.headers.get("content-type", "?")
    sha = hashlib.sha256(r.content).hexdigest()

    if finale in visti_finali:
        return (f"{marca(url)}{url}  ->  gia' archiviato come {finale} "
                f"(duplicato dopo redirect)"), r
    visti_finali.add(finale)
    percorso = archivia(url, r, stamp)

    nota = "" if finale == url else f"  [redirect -> {finale}]"
    esito = "HTTP 200" if r.status_code == 200 else \
            f"HTTP {r.status_code}  (NON DISPONIBILE -- assenza archiviata)"
    return (f"{marca(url)}{url}  ->  {esito}  |  {len(r.content)} byte  |  {tipo}  |  "
            f"Date: {data_srv}  |  SHA256 {sha}  |  {percorso.name}{nota}"), r


def pagine_collegate(client: httpx.Client, home: str, stamp: str) -> tuple[list[str], str]:
    """Archivia la home e restituisce gli URL delle pagine legali collegate."""
    riga, r = scarica(client, home, stamp)
    if r is None or r.status_code != 200:
        return [], riga
    zuppa = BeautifulSoup(r.content, "lxml")

    trovati: list[str] = []
    for a in zuppa.find_all("a", href=True):
        testo = " ".join(a.get_text(" ", strip=True).lower().split())
        href = a["href"].lower()
        if any(k in testo for k in CHIAVI) or any(k in href for k in CHIAVI):
            assoluto = urljoin(home, a["href"])
            if urlparse(assoluto).scheme in ("http", "https") and assoluto not in trovati:
                trovati.append(assoluto)
    return trovati, riga


def allegati(client: httpx.Client, pagina: str, r: httpx.Response | None,
             stamp: str) -> list[str]:
    """Scarica i documenti collegati da una pagina editoriale gia' scaricata."""
    if r is None or r.status_code != 200:
        return [f"{pagina}: pagina non disponibile, allegati non ispezionabili"]
    zuppa = BeautifulSoup(r.content, "lxml")
    base = str(r.url)
    righe: list[str] = []

    visti: set[str] = set()
    for a in zuppa.find_all("a", href=True):
        if not e_allegato(a["href"]):
            continue
        u = urljoin(base, a["href"])
        if u in visti:
            continue
        visti.add(u)
        etichetta = a.get_text(" ", strip=True)[:60] or "(senza etichetta)"
        righe.append(f"[{etichetta}] " + scarica(client, u, stamp)[0])
        time.sleep(RITARDO)

    if not righe:
        righe.append(f"{pagina}: nessun allegato individuato")
    return righe


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    momento = datetime.now(timezone.utc).astimezone()
    stamp = momento.strftime("%Y%m%d")

    righe = [
        "VERIFICA DEI VINCOLI DI ACCESSO",
        f"Momento dell'accesso: {momento.isoformat(timespec='seconds')}",
        f"User-Agent: {UA}",
        f"Ritardo dichiarato fra le richieste: {RITARDO} s",
        f"Perimetro di raccolta: il solo dominio {DOMINIO}.",
        "Il sito istituzionale accademiadellacrusca.it non e' oggetto di crawl e",
        "non viene interrogato come base; le sole pagine legali esplicitamente",
        "collegate dal portale sono archiviate e marcate [fuori dominio].",
        "",
        "--- robots.txt, sitemap e pagine editoriali del portale ---",
    ]

    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT,
                      follow_redirects=True) as client:

        risp_criteri = None
        for url in URL_BASE:
            riga, r = scarica(client, url, stamp)
            righe.append(riga)
            if url == CRITERI:
                risp_criteri = r
            time.sleep(RITARDO)

        righe += ["", "--- home del portale e pagine legali collegate ---"]
        note: list[str] = []
        trovati, riga = pagine_collegate(client, PORTALE, stamp)
        righe.append(riga)
        time.sleep(RITARDO)
        for u in trovati:
            if u not in note and u not in URL_BASE:
                note.append(u)

        if not note:
            righe.append("Nessun ulteriore collegamento individuato "
                         "automaticamente: controllare a mano il pie' di pagina.")
        for u in note:
            righe.append(scarica(client, u, stamp)[0])
            time.sleep(RITARDO)

        righe += ["", "--- allegati della pagina dei criteri editoriali ---"]
        righe += allegati(client, CRITERI, risp_criteri, stamp)

    esterni = sum(1 for u in visti_finali if fuori_dominio(u))
    righe += ["", f"Richieste inviate: {richieste}",
              f"Documenti distinti archiviati: {len(visti_finali)}",
              f"Di cui fuori dal dominio {DOMINIO}: {esterni}"]

    verbale = DEST / f"verbale_accesso_{stamp}.txt"
    verbale.write_text("\n".join(righe) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(righe))
    print(f"\nVerbale: {verbale}")


if __name__ == "__main__":
    main()
