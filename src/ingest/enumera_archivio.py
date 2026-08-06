# -*- coding: utf-8 -*-
"""Passo 3 — Enumerazione dell'archivio e costruzione del manifest v0.
 
Percorre due sorgenti distinte:
  - fascicoli/archivio       -> i 33 fascicoli chiusi (con PDF di fascicolo)
  - fascicoli/in-anteprima   -> i fascicoli aperti, in pubblicazione continua
 
Per ogni fascicolo apre la pagina-indice e ne ricava l'elenco delle schede.
NON apre le pagine-scheda: quello e' il crawl vero e proprio, che viene dopo.
 
Contratto strutturale, rilevato nella ricognizione del 4/8:
  - l'intestazione di rubrica e' <h3 class="border-bottom-2 text-primary">;
  - le schede che la seguono, in ordine di documento, appartengono a quella
    rubrica finche' non compare l'intestazione successiva;
  - il collegamento alla scheda ha forma /articoli/<slug>/<id>;
  - il PDF della singola scheda e' un /File/Download?code=<uuid> nella stessa
    riga (<div class="row">) della scheda.
 
Uscite:
  data/raw/indici/*.raw                  pagine-indice archiviate in byte grezzi
  data/raw/manifest/manifest_v0_*.csv    una riga per scheda
  data/raw/manifest/verbale_*.txt        verbale con impronte e conteggi
  config/acquisizione.yaml               vi viene scritto il cutoff, a fine corsa
 
Uso:  python src/ingest/enumera_archivio.py     (dalla radice del progetto)
"""
from __future__ import annotations
 
import csv
import hashlib
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
 
import httpx
from bs4 import BeautifulSoup, Tag
 
from src.config import carica
 
# --- parametri: unica fonte di verita' e' config/acquisizione.yaml --------
_conf = carica()
UA: str = _conf["user_agent"]
RITARDO: float = _conf["ritardo_secondi"]
TIMEOUT: float = _conf["timeout_secondi"]
PORTALE: str = _conf["portale"]
ARCHIVIO = urljoin(PORTALE, _conf["elenco_fascicoli_chiusi"])
ANTEPRIMA = urljoin(PORTALE, _conf["elenco_fascicoli_aperti"])
 
DIR_INDICI = Path("data/raw/indici")
DIR_MANIFEST = Path("manifest")
 
RE_ARTICOLO = re.compile(r"^/articoli/(?P<slug>.+)/(?P<id>\d+)/?$")
RE_FASCICOLO = re.compile(r"^/fascicoli/(?P<slug>[^/]+)/(?P<id>\d+)/?$")
CLASSI_RUBRICA = {"border-bottom-2", "text-primary"}
 
# i nomi delle rubriche variano negli anni: si normalizzano
ALIAS = {
    "CONSULENZE LINGUISTICHE": "CONSULENZA LINGUISTICA",
    "GLI ARTICOLI": "ARTICOLI",
}
NUCLEO = {"CONSULENZA LINGUISTICA", "LA CRUSCA RISPOSE"}
ESTENSIONE = {"PAROLE NUOVE"}
 
richieste = 0
visti_finali: set[str] = set()
 
 
def normalizza_rubrica(testo: str) -> str:
    t = " ".join(testo.split()).upper()
    return ALIAS.get(t, t)
 
 
def nome_file(url: str) -> str:
    g = url.split("://", 1)[1]
    return "".join(c if c.isalnum() else "_" for c in g)[:120]
 
 
def preleva(client: httpx.Client, url: str, dest: Path, stamp: str):
    """Scarica, archivia i byte grezzi, restituisce (zuppa, url_finale, sha, byte).
 
    Deduplica sull'URL finale: due indirizzi che convergono sullo stesso
    documento vengono archiviati una volta sola.
    """
    global richieste
    richieste += 1
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        print(f"  ERRORE DI RETE  {url}: {e}")
        return None
    if r.status_code != 200:
        print(f"  HTTP {r.status_code}  {url}")
        return None
 
    finale = str(r.url)
    dati = r.content
    if finale not in visti_finali:
        visti_finali.add(finale)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{nome_file(url)}_{stamp}.raw").write_bytes(dati)
    return (BeautifulSoup(dati, "lxml"), finale,
            hashlib.sha256(dati).hexdigest(), len(dati))
 
 
def fascicoli_da(zuppa: BeautifulSoup, base: str) -> list[dict]:
    """Fascicoli elencati in una pagina, deduplicati per identificatore."""
    trovati: dict[str, dict] = {}
    for a in zuppa.find_all("a", href=True):
        u = urljoin(base, a["href"])
        if urlparse(u).netloc != urlparse(base).netloc:
            continue
        m = RE_FASCICOLO.match(urlparse(u).path)
        if not m:
            continue
        idf = m.group("id")
        testo = a.get_text(" ", strip=True)
        if idf not in trovati:
            trovati[idf] = {"id_fascicolo": idf, "url": u,
                            "slug": m.group("slug"), "etichetta": testo}
        elif testo and not trovati[idf]["etichetta"]:
            trovati[idf]["etichetta"] = testo
    return list(trovati.values())
 
 
def riga_di(a: Tag) -> Tag | None:
    return a.find_parent("div", class_="row")
 
 
def pdf_nella_riga(a: Tag) -> str:
    riga = riga_di(a)
    if riga is None:
        return ""
    for link in riga.find_all("a", href=True):
        if "/File/Download" in link["href"]:
            return link["href"]
    return ""
 
 
def testo_riga(a: Tag) -> str:
    riga = riga_di(a)
    return " | ".join(riga.stripped_strings)[:300] if riga else ""
 
 
def schede_da(zuppa: BeautifulSoup, base: str, fasc: dict, stato: str) -> list[dict]:
    """Percorre la pagina in ordine di documento associando rubrica e schede."""
    rubrica = "?"
    viste: set[str] = set()
    righe: list[dict] = []
 
    for el in zuppa.find_all(True):
        if el.name == "h3" and CLASSI_RUBRICA <= set(el.get("class", [])):
            rubrica = el.get_text(" ", strip=True)
            continue
        if el.name != "a" or not el.get("href"):
            continue
        u = urljoin(base, el["href"])
        if urlparse(u).netloc != urlparse(base).netloc:
            continue
        m = RE_ARTICOLO.match(urlparse(u).path)
        if not m:
            continue
        ids = m.group("id")
        if ids in viste:
            continue
        viste.add(ids)
        rn = normalizza_rubrica(rubrica)
        pdf = pdf_nella_riga(el)
        righe.append({
            "id_scheda": ids,
            "url": u,
            "slug": m.group("slug"),
            "titolo": el.get_text(" ", strip=True),
            "rubrica": rubrica,
            "rubrica_norm": rn,
            "nel_nucleo": rn in NUCLEO,
            "estensione": rn in ESTENSIONE,
            "fascicolo": fasc["etichetta"],
            "id_fascicolo": fasc["id_fascicolo"],
            "stato_fascicolo": stato,
            "fonte_di_record": "HTML+PDF" if (stato == "chiuso" and pdf) else "solo HTML",
            "url_pdf_scheda": urljoin(base, pdf) if pdf else "",
            "contesto_riga": testo_riga(el),
        })
    return righe
 
 
def main() -> None:
    global richieste
    momento = datetime.now(timezone.utc).astimezone()
    stamp = momento.strftime("%Y%m%d")
    verbale = [
        "ENUMERAZIONE DELL'ARCHIVIO — manifest v0",
        f"Momento della raccolta (cutoff): {momento.isoformat(timespec='seconds')}",
        f"User-Agent: {UA}",
        f"Ritardo fra le richieste: {RITARDO} s",
        "",
    ]
    schede: list[dict] = []
    completo = True
 
    with httpx.Client(headers={"User-Agent": UA}, timeout=TIMEOUT,
                      follow_redirects=True) as client:
 
        elenco: list[tuple[dict, str]] = []
        for pagina, stato in ((ARCHIVIO, "chiuso"), (ANTEPRIMA, "aperto")):
            print(f"\n=== {pagina} ===")
            res = preleva(client, pagina, DIR_INDICI, stamp)
            if not res:
                print("Impossibile proseguire senza la pagina di elenco.")
                return
            zuppa, finale, sha, n = res
            verbale.append(f"{pagina}  |  {n} byte  |  SHA256 {sha}")
            trovati = [f for f in fascicoli_da(zuppa, finale)
                       if f["url"] not in (pagina, finale)]
            print(f"  fascicoli {stato}i individuati: {len(trovati)}")
            elenco += [(f, stato) for f in trovati]
            time.sleep(RITARDO)
 
        verbale += ["", f"Fascicoli da visitare: {len(elenco)}", ""]
 
        for i, (fasc, stato) in enumerate(elenco, 1):
            etichetta = fasc["etichetta"] or fasc["slug"]
            print(f"[{i:>2}/{len(elenco)}] {etichetta}")
            res = preleva(client, fasc["url"], DIR_INDICI, stamp)
            if not res:
                verbale.append(f"{fasc['url']}  |  NON SCARICATO")
                completo = False
                time.sleep(RITARDO)
                continue
            zuppa, finale, sha, n = res
            righe = schede_da(zuppa, finale, fasc, stato)
            schede += righe
            print(f"        schede: {len(righe)}")
            verbale.append(f"{fasc['url']}  |  {n} byte  |  SHA256 {sha}  "
                           f"|  schede: {len(righe)}  |  stato: {stato}")
            time.sleep(RITARDO)

        # Controllo di determinismo: la stessa pagina, scaricata due volte,
        # deve produrre la stessa impronta. Se non fosse cosi', la garanzia
        # di immutabilita' con checksum dello store grezzo andrebbe riformulata.
        if schede:
            prova = schede[0]["url"]
            a = client.get(prova);
            time.sleep(RITARDO)
            b = client.get(prova)
            sa = hashlib.sha256(a.content).hexdigest()
            sb = hashlib.sha256(b.content).hexdigest()
            richieste += 2
            esito = "stabile" if sa == sb else "INSTABILE"
            verbale.append("")
            verbale.append(f"Controllo di determinismo su {prova}: {esito}")
            verbale.append(f"  1a lettura SHA256 {sa}")
            verbale.append(f"  2a lettura SHA256 {sb}")
            print(f"\nControllo di determinismo sulla pagina-scheda: {esito}")

    # --- uscite: prima gli artefatti, poi il cutoff ------------------------
    DIR_MANIFEST.mkdir(parents=True, exist_ok=True)
    csv_out = DIR_MANIFEST / f"manifest_v0_prelim_{stamp}.csv"
    if schede:
        with csv_out.open("w", newline="", encoding="utf-8-sig") as fo:
            w = csv.DictWriter(fo, fieldnames=list(schede[0].keys()))
            w.writeheader()
            w.writerows(schede)
 
    per_rubrica = Counter(r["rubrica_norm"] for r in schede)
    per_stato = Counter(r["stato_fascicolo"] for r in schede)
    riepilogo = [
        "",
        "--- RIEPILOGO ---",
        f"Richieste inviate: {richieste}",
        f"Schede totali: {len(schede)}",
        f"Per stato del fascicolo: {dict(per_stato)}",
        f"Nucleo consultivo: {sum(1 for r in schede if r['nel_nucleo'])}   "
        f"Estensione (Parole nuove): {sum(1 for r in schede if r['estensione'])}",
        f"Schede senza PDF individuato: {sum(1 for r in schede if not r['url_pdf_scheda'])}",
        f"Schede senza rubrica attribuita: {sum(1 for r in schede if r['rubrica_norm'] == '?')}",
        "",
        "Per rubrica normalizzata:",
    ] + [f"  {n:>5}  {r}" for r, n in per_rubrica.most_common()]
 
    verbale += riepilogo
    (DIR_MANIFEST / f"verbale_enumerazione_prelim_{stamp}.txt").write_text(
        "\n".join(verbale) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(riepilogo))
    print(f"\nManifest: {csv_out}")
 
    # Il cutoff si registra solo se la raccolta e' completa: una data
    # riferita a un'enumerazione parziale sarebbe una dichiarazione falsa.
    if not completo:
        print("\nATTENZIONE: enumerazione incompleta. "
              "Esaminare il verbale prima di rilanciare.")
    print("\nCutoff NON registrato: questa e' l'enumerazione preliminare, "
          "telaio di campionamento e non corpus (decisione 6/8). Lo scrivera' "
          "l'enumerazione definitiva, contestuale al crawl.")


 
if __name__ == "__main__":
    main()