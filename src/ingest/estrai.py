# -*- coding: utf-8 -*-
"""Estrazione testuale dalle due fonti: pagina-scheda HTML e PDF di scheda.

Modulo di servizio, senza effetti su disco: espone funzioni che ricevono byte
e restituiscono testo o metadati. Lo usano il confronto HTML<->PDF (passo 5) e,
piu' avanti, l'ingestion.

Contratto strutturale della pagina-scheda, rilevato il 7/8 sul campione:
  - il corpo dell'articolo sta in `div.col-md-8`;
  - la colonna `div.col-md-4` contiene il blocco «Nella stessa rubrica», cioe'
    i titoli di cinque schede vicine: va eliminata prima di ogni estrazione,
    altrimenti ogni documento dell'indice contiene i titoli di altri cinque
    (Quadro, rischio 13);
  - l'etichetta «Quesito:» e' un `h4` presente dal 2019, assente nel 2017-2018
    e in *La Crusca rispose* su tutte le annate;
  - i metadati autorevoli stanno nei meta `citation_*` e `DC.*`, non nell'`h1`,
    che riflette il markup frammentato del titolo.

L'estrazione qui e' a testo piatto: serve al confronto fra le due fonti. La
preservazione degli span di formattazione, prevista dal Quadro §3, riguarda
l'estrattore definitivo e non questo passaggio.
"""
from __future__ import annotations

import re

import fitz  # PyMuPDF
from bs4 import BeautifulSoup

SCARTA = ("script", "style", "noscript")
BOILERPLATE = "div.col-md-4"
CORPO = "div.col-md-8"


def zuppa(dati: bytes) -> BeautifulSoup:
    """Analizza i byte e rimuove cio' che non e' contenuto."""
    z = BeautifulSoup(dati, "lxml")
    for sel in (BOILERPLATE,):
        for el in z.select(sel):
            el.decompose()
    for nome in SCARTA:
        for el in z.find_all(nome):
            el.decompose()
    return z


def metadati_html(dati: bytes) -> dict[str, str]:
    """Metadati strutturati della pagina-scheda: `citation_*` e `DC.*`."""
    z = BeautifulSoup(dati, "lxml")
    out: dict[str, str] = {}
    for m in z.find_all("meta"):
        nome = (m.get("name") or m.get("property") or "").strip()
        if nome.lower().startswith(("citation_", "dc.")):
            out[nome] = " ".join(str(m.get("content", "")).split())
    return out


def ha_quesito(dati: bytes) -> bool:
    """Vero se la pagina espone l'etichetta «Quesito:»."""
    z = BeautifulSoup(dati, "lxml")
    return bool(z.find("h4", string=re.compile(r"Quesito", re.I)))


def testo_html(dati: bytes) -> str:
    """Testo del corpo dell'articolo, a testo piatto."""
    z = zuppa(dati)
    corpo = z.select_one(CORPO)
    if corpo is None:
        return ""
    return corpo.get_text("\n", strip=True)


def testo_pdf(dati: bytes) -> str:
    """Testo del PDF, pagina per pagina, nell'ordine del documento."""
    with fitz.open(stream=dati, filetype="pdf") as doc:
        return "\n".join(p.get_text() for p in doc)
