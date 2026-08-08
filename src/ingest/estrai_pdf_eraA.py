# -*- coding: utf-8 -*-
"""Parser del PDF di scheda per l'era-A (2017-2018).

Serve alle 172 schede del nucleo consultivo le cui pagine-scheda HTML non
contengono il corpo dell'articolo (decisione 7/8). Produce lo stesso
`Documento` dell'estrattore HTML: il resto della pipeline non deve sapere da
quale fonte provenga un documento.

CONTRATTO TIPOGRAFICO, rilevato l'8/8 su sette schede 2017-2018. Nell'era-A la
struttura non e' marcata semanticamente ma tipograficamente, e i font sono
nominati, quindi leggibili:

    testatina           SimonciniGaramondStd 12,0 · OpenSans-Light 10,0 «- p.»
    rubrica e accesso   OpenSans 10,0 «| OPEN ACCESS», «SOTTOPOSTO A»
    titolo              OpenSans-Bold* 14,0
    autore              OpenSans-Semibold 11,3
    data                OpenSans-Light 9,0 «PUBBLICATO:»
    etichetta quesito   CormorantGaramond-Bold 13,0, testo «Quesito:»
    confine quesito     CormorantGaramond-Bold 13,0 = titolo ripetuto
    capolettera         CormorantGaramond 20,0 o piu' (osservato 61,0)
    corpo               CormorantGaramond-Regular/Italic 13,0
    esempi              CormorantGaramond 11,0  ->  equivale a blockquote.cit
    colophon            OpenSans-Semibold 10,2 «Cita come:»

L'etichetta «Quesito:» e' esplicita in tutte le rubriche, *La Crusca rispose*
compresa: nell'era-A il PDF e' piu' uniforme dell'HTML degli anni successivi.

Il corsivo si legge dal nome del font (`-Italic`) e dai flag: le forme
menzionate si recuperano. Vale la stessa avvertenza dell'HTML — si conserva la
tipografia, non la semantica.

Uso come modulo:
    from src.ingest.estrai_pdf_eraA import documento_da_pdf
Collaudo sulle sette schede 2017-2018 gia' su disco:
    python -m src.ingest.estrai_pdf_eraA

NOTA PER L'INGESTION. Questo modulo estrae il **corpo**, non i metadati:
    per le schede 2017-2018 la pagina-scheda HTML espone comunque `citation_*`
    e `DC.*` completi, ed e' da li' che vanno letti autori, data, DOI, licenza,
    fascicolo e paginazione. Il Documento prodotto qui va fuso con quello
    restituito da `estrai_scheda.metadati_html`.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import fitz

from src.ingest.estrai_scheda import Blocco, Documento, _fondi

CORPO_TESTO = 13.0
CORPO_ESEMPIO = 11.0
CAPOLETTERA = 20.0
FONT_TESTO = "Cormorant"
TOLLERANZA = 0.6

RE_QUESITO = re.compile(r"^\s*quesito\s*:", re.I)



def _stili(s: dict) -> set[str]:
    st: set[str] = set()
    nome = s["font"].lower()
    if "italic" in nome or s["flags"] & 2 ** 1:
        st.add("corsivo")
    if "bold" in nome or "semibold" in nome or s["flags"] & 2 ** 4:
        st.add("grassetto")
    return st


def _vicino(a: float, b: float) -> bool:
    return abs(a - b) <= TOLLERANZA


def _span_utili(doc: fitz.Document) -> list[dict]:
    """Span del solo testo d'autore, in ordine di lettura.

    Elimina testatine, intestazione editoriale, titolo, autore e data, che
    stanno tutti in OpenSans o SimonciniGaramond; conserva il Cormorant, che
    e' il carattere del testo.
    """
    fuori: list[dict] = []
    n = 0
    for pagina in doc:
        for blocco in pagina.get_text("dict")["blocks"]:
            n += 1
            for riga in blocco.get("lines", []):
                for s in riga["spans"]:
                    if not s["text"].strip():
                        continue
                    if FONT_TESTO not in s["font"]:
                        continue
                    fuori.append({"testo": s["text"],
                                  "corpo": round(s["size"], 1),
                                  "stili": _stili(s),
                                  "blocco": n})
    return fuori


def _blocco_da(span: list[dict], tipo: str) -> Blocco | None:
    """Costruisce un Blocco conservando gli intervalli di formattazione."""
    pezzi: list[str] = []
    spans: list[tuple[int, int, str]] = []
    lung = 0
    for s in span:
        t = " ".join(s["testo"].split())
        if not t:
            continue
        if pezzi and pezzi[-1].endswith("-") and re.match(r"\w", t) \
                and re.search(r"\w-$", pezzi[-1]):
            pezzi[-1] = pezzi[-1][:-1]  # sillabazione di fine riga
            lung -= 1
            spans = [(a, min(b, lung), k) for a, b, k in spans]
        elif pezzi and not pezzi[-1].endswith((" ", "\u2019", "'", "(", "[")) \
                and not t.startswith((",", ".", ";", ":", "!", "?", ")",
                                      "]", "\u2019", "'")):
            pezzi.append(" ")
            lung += 1
        inizio = lung
        pezzi.append(t)
        lung += len(t)
        for st in s["stili"]:
            spans.append((inizio, lung, st))
    testo = unicodedata.normalize("NFC", "".join(pezzi)).strip()
    if not testo:
        return None
    return Blocco(tipo, testo, _fondi([s for s in spans if s[0] < s[1]]))


def documento_da_pdf(dati: bytes, id_scheda: str, titolo: str,
                     url: str = "") -> Documento:
    """Estrae il Documento dal PDF di scheda dell'era-A.

    `titolo` viene dal manifest o dai metadati della pagina-scheda: serve a
    riconoscere la ripetizione che separa il quesito dal corpo.
    """
    d = Documento(id_scheda=id_scheda, titolo=titolo, url=url)
    with fitz.open(stream=dati, filetype="pdf") as doc:
        span = _span_utili(doc)


    # 1. capolettera: si riattacca allo span successivo
    ripulito: list[dict] = []
    for s in span:
        if s["corpo"] >= CAPOLETTERA and len(s["testo"].strip()) <= 2:
            ripulito.append({"testo": s["testo"].strip(), "corpo": CORPO_TESTO,
                             "stili": set(), "blocco": s["blocco"],
                             "capolettera": True})
        else:
            ripulito.append(s)
    for i, s in enumerate(ripulito):
        if s.get("capolettera") and i + 1 < len(ripulito):
            ripulito[i + 1]["testo"] = s["testo"] + ripulito[i + 1]["testo"].lstrip()
            s["testo"] = ""
    span = [s for s in ripulito if s["testo"]]

    # 2. quesito: dall'etichetta alla ripetizione del titolo
    i_q = next((i for i, s in enumerate(span) if RE_QUESITO.match(s["testo"])),
               None)
    inizio_corpo = 0
    if i_q is None:
        d.qualita_parsing.append("etichetta «Quesito:» assente nel PDF")
    else:
        confronta = lambda t: re.sub(r"[^\w]+", "", t.lower())
        bersaglio = confronta(titolo)
        i_t, accumulato = None, ""
        for i in range(i_q + 1, len(span)):
            if "grassetto" not in span[i]["stili"]:
                accumulato = ""
                continue
            accumulato += confronta(span[i]["testo"])
            if bersaglio and accumulato.endswith(bersaglio):
                i_t = i
                break
        if i_t is None:
            d.qualita_parsing.append("titolo ripetuto non riconosciuto: "
                                     "confine quesito/corpo presunto")
            i_t = i_q
        quesito = _blocco_da(span[i_q:i_t + 1], "quesito")
        if quesito:
            testo = RE_QUESITO.sub("", quesito.testo).strip()
            scarto = len(quesito.testo) - len(testo)
            # si toglie anche la ripetizione del titolo in coda
            coda = re.sub(r"[^\w]+", "", testo.lower())
            if bersaglio and coda.endswith(bersaglio):
                k = len(testo)
                while k > 0 and confronta(testo[k:]) != bersaglio:
                    k -= 1
                if k > 0:
                    testo = testo[:k].strip(" -–—")
            d.quesito = testo
            d.quesito_span = _fondi([(max(0, a - scarto), min(len(testo), b - scarto), k)
                                     for a, b, k in quesito.span
                                     if b - scarto > 0 and a - scarto < len(testo)])
        inizio_corpo = i_t + 1

    # 3. corpo: si raggruppano gli span contigui dello stesso corpo tipografico
    gruppo: list[dict] = []
    tipo_corrente: str | None = None
    for s in span[inizio_corpo:]:
        tipo = ("esempio" if _vicino(s["corpo"], CORPO_ESEMPIO)
                else "paragrafo" if _vicino(s["corpo"], CORPO_TESTO)
                else "altro")
        stacco = (s["blocco"] != gruppo[-1]["blocco"]) if gruppo else False
        # un blocco di PyMuPDF che comincia a meta' frase e' una rottura di
        # impaginazione, non un confine di paragrafo: si ricuce
        if stacco and not gruppo[-1]["testo"].rstrip().endswith(
                (".", "!", "?", ":", ";", "»", "\u201d", ")")):
            stacco = False
        if gruppo and (tipo != tipo_corrente or stacco):
            b = _blocco_da(gruppo, tipo_corrente or "paragrafo")
            if b:
                d.corpo.append(b)
            gruppo = []
        tipo_corrente = tipo
        gruppo.append(s)
    if gruppo:
        b = _blocco_da(gruppo, tipo_corrente or "paragrafo")
        if b:
            d.corpo.append(b)

    if not d.corpo:
        d.qualita_parsing.append("corpo vuoto")
    d.qualita_parsing.append("fonte primaria: PDF di scheda (era-A)")
    return d


def _collaudo() -> None:
    import pandas as pd
    m = sorted(Path("manifest").glob("manifest_v0_prelim_*.csv"))[-1]
    df = pd.read_csv(m, encoding="utf-8-sig", dtype=str).set_index("id_scheda")
    print(f"{'id':>6} {'blocchi':>7} {'esempi':>6} {'car_q':>6} {'car_corpo':>9} "
          f"{'corsivi':>7}  quesito / note")
    for ids in ("43", "51", "85", "93", "186", "197", "199"):
        f = next(Path("data/raw/campione").glob(f"{ids}_*.pdf"), None)
        if f is None or ids not in df.index:
            continue
        titolo = " ".join(str(df.loc[ids, "titolo"]).split())
        d = documento_da_pdf(f.read_bytes(), ids, titolo)
        corsivi = sum(1 for b in d.corpo for s in b.span if s[2] == "corsivo")
        note = (d.quesito[:46] + "…") if d.quesito else "—"
        problemi = [n for n in d.qualita_parsing if not n.startswith("fonte")]
        if problemi:
            note += "  ||  " + "; ".join(problemi)
        print(f"{ids:>6} {len(d.corpo):>7} {len(d.esempi):>6} {len(d.quesito):>6} "
              f"{len(d.testo_corpo):>9} {corsivi:>7}  {note}")


if __name__ == "__main__":
    _collaudo()
