# -*- coding: utf-8 -*-
"""Passo 5 — Confronto HTML<->PDF sul campione di verifica (Dossier §4.4).

Per ciascuna scheda del campione confronta il testo estratto dalla pagina-scheda
con quello estratto dal PDF della scheda, dopo una normalizzazione **di
confronto** dichiarata piu' avanti. Soglia: similarita' >= 0,98.

    ATTENZIONE — la normalizzazione applicata qui e' deliberatamente piu'
    aggressiva di quella conservativa prevista dalla pipeline (Quadro §3).
    E' uno strumento di misura, non un passaggio dell'ingestion: serve a
    rendere confrontabili due rese tipografiche dello stesso testo. Nessuna
    delle trasformazioni qui applicate finisce nel corpus.

Che cosa viene tagliato, e perche':
  - HTML: l'intestazione di metadati (rubrica, autore, data, DOI, licenza) fino
    a «Copyright:», e il blocco «Parole chiave» in coda. Nessuno dei due
    compare nel PDF nella stessa forma.
  - PDF: l'intestazione fino alla riga «PUBBLICATO: <data>», il riquadro
    «Cita come:» in coda, e le testatine di pagina, che nell'HTML non esistono.
  - PDF: la sillabazione di fine riga viene ricomposta.
  - entrambi: NFC, unificazione di apostrofi e virgolette tipografiche,
    minuscolo, rimozione di ogni spaziatura. L'ultima elimina d'un colpo il
    capolettera staccato dal flusso e le differenze di andata a capo.

Il criterio di superamento non e' la sola soglia. Ogni scheda sotto 0,98 va
classificata a mano in una di tre classi:
  (a) artefatto di estrazione del PDF  -> non e' un fallimento
  (b) divergenza redazionale fra le due versioni -> si conta
  (c) sezione presente nel PDF e assente nell'HTML -> fallimento grave
Il campione passa se non si registra alcun caso (c) e al piu' un caso (b).

Uscite:
  manifest/confronto_html_pdf_<stamp>.csv
  manifest/verbale_confronto_<stamp>.txt

Uso:  python -m src.ingest.confronta_html_pdf     (dalla radice del progetto)
Richiede:  pip install rapidfuzz
"""
from __future__ import annotations

import csv
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz

from src.ingest.estrai import testo_html, testo_pdf, ha_quesito

CAMPIONE = Path("config/campione_verifica.csv")
DATI = Path("data/raw/campione")
DIR_MANIFEST = Path("manifest")
SOGLIA = 0.98

RE_PUBBLICATO = re.compile(r"PUBBLICATO:\s*\d{1,2}\s+\S+\s+\d{4}", re.I)
RE_TESTATINA = re.compile(
    r"^\s*(?:Italiano digitale\b.*|.*\b20\d\d/\d\s*\(.*\))\s*-\s*p\.\s*\d+\s*$",
    re.I)
APICI = {"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
         "\u201e": '"', "\u2013": "-", "\u2014": "-", "\u00a0": " ",
         "\u00ad": ""}


def pulisci_html(t: str) -> str:
    """Elimina intestazione di metadati e blocco delle parole chiave."""
    i = t.find("Copyright:")
    if i != -1:
        j = t.find("\n", i)
        t = t[j + 1:] if j != -1 else t[i:]
    k = t.rfind("Parole chiave")
    if k != -1:
        t = t[:k]
    return t


def pulisci_pdf(t: str) -> str:
    """Ricompone la sillabazione, elimina intestazione, testatine e colophon."""
    t = re.sub(r"-\n(?=\w)", "", t)          # sillabazione di fine riga
    m = RE_PUBBLICATO.search(t)
    if m:
        t = t[m.end():]
    k = t.rfind("Cita come:")
    if k != -1:
        t = t[:k]
    righe = [r for r in t.split("\n") if not RE_TESTATINA.match(r)]
    return "\n".join(righe)


def normalizza(t: str) -> str:
    """Normalizzazione di confronto: aggressiva e non riusabile altrove."""
    t = unicodedata.normalize("NFC", t)
    for a, b in APICI.items():
        t = t.replace(a, b)
    t = t.lower()
    return re.sub(r"\s+", "", t)


def divergenza(a: str, b: str, ampiezza: int = 45) -> str:
    """Posizione e contesto del primo carattere in cui le due stringhe differiscono."""
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    if i == n and len(a) == len(b):
        return "identiche"
    return (f"car {i}: html «…{a[max(0, i - ampiezza):i + ampiezza]}…» | "
            f"pdf «…{b[max(0, i - ampiezza):i + ampiezza]}…»")


def main() -> None:
    momento = datetime.now(timezone.utc).astimezone()
    stamp = momento.strftime("%Y%m%d")
    DIR_MANIFEST.mkdir(exist_ok=True)
    df = pd.read_csv(CAMPIONE, encoding="utf-8", dtype=str)

    righe: list[dict] = []
    for _, s in df.iterrows():
        ids = s["id_scheda"]
        fh = next(DATI.glob(f"{ids}_*.html"), None)
        fp = next(DATI.glob(f"{ids}_*.pdf"), None)
        if fh is None or fp is None:
            print(f"{ids}: file mancanti, scheda saltata")
            continue
        bh, bp = fh.read_bytes(), fp.read_bytes()
        h = normalizza(pulisci_html(testo_html(bh)))
        p = normalizza(pulisci_pdf(testo_pdf(bp)))
        sim = fuzz.ratio(h, p) / 100.0
        righe.append({
            "id_scheda": ids, "anno": s["anno"], "rubrica": s["rubrica_norm"],
            "pagine": s["pagine"], "quesito_html": ha_quesito(bh),
            "car_html": len(h), "car_pdf": len(p),
            "delta_car": len(p) - len(h),
            "similarita": round(sim, 4),
            "esito": "ok" if sim >= SOGLIA else "SOTTO SOGLIA",
            "prima_divergenza": divergenza(h, p),
        })

    righe.sort(key=lambda r: r["similarita"])
    sotto = [r for r in righe if r["esito"] != "ok"]

    verbale = [
        "CONFRONTO HTML<->PDF SUL CAMPIONE DI VERIFICA",
        f"Momento: {momento.isoformat(timespec='seconds')}",
        f"Soglia: {SOGLIA}",
        f"Schede confrontate: {len(righe)}",
        f"Sopra soglia: {len(righe) - len(sotto)}   Sotto soglia: {len(sotto)}",
        "",
        f"{'id':>7}  {'anno':>4}  {'sim':>6}  {'car_html':>8}  {'car_pdf':>8}  "
        f"{'delta':>6}  quesito  esito",
    ]
    for r in righe:
        verbale.append(
            f"{r['id_scheda']:>7}  {r['anno']:>4}  {r['similarita']:>6.4f}  "
            f"{r['car_html']:>8}  {r['car_pdf']:>8}  {r['delta_car']:>6}  "
            f"{str(r['quesito_html']):<7}  {r['esito']}")
    if sotto:
        verbale += ["", "--- schede sotto soglia: contesto della prima divergenza ---"]
        for r in sotto:
            verbale += [f"[{r['id_scheda']}]  {r['prima_divergenza']}", ""]

    with (DIR_MANIFEST / f"confronto_html_pdf_{stamp}.csv").open(
            "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(righe[0].keys()))
        w.writeheader()
        w.writerows(righe)
    (DIR_MANIFEST / f"verbale_confronto_{stamp}.txt").write_text(
        "\n".join(verbale) + "\n", encoding="utf-8", newline="\n")

    print("\n".join(verbale))
    print("\nLa soglia non basta: ogni scheda sotto 0,98 va classificata a mano "
          "in (a) artefatto di estrazione, (b) divergenza redazionale, "
          "(c) sezione mancante nell'HTML.")


if __name__ == "__main__":
    main()
