# -*- coding: utf-8 -*-
"""Selezione stratificata delle schede per la verifica HTML<->PDF.
 
Produce due campioni, entrambi dai soli fascicoli CHIUSI (gli unici con PDF):
 
  A) VERIFICA — 20 schede su cui eseguire il confronto testuale HTML<->PDF
     con soglia di similarita' >= 0,98 (Dossier §4.4);
  B) ISPEZIONE — 30 schede su cui condurre l'ispezione manuale del parsing
     prevista dal Quadro §14, giorni 4-7.
 
La stratificazione non e' casuale: il Quadro avverte che un campione casuale
contiene quasi solo casi facili. Si impongono quote esplicite.
 
Criteri per il campione di VERIFICA (20):
  - copertura di tutte le epoche: almeno 2 schede per ciascuna fascia
    2017-2019 / 2020-2022 / 2023-2025;
  - almeno 4 schede degli anni 2017-2019, dove la presenza dell'etichetta
    «Quesito:» nelle pagine-scheda non e' mai stata verificata;
  - almeno 3 schede di *La Crusca rispose*, rubrica mai controllata;
  - almeno 2 di *Parole nuove* (profilo A2 ancora da decidere);
  - estremi di lunghezza: le 2 schede piu' brevi e le 2 piu' lunghe del
    nucleo, misurate sull'intervallo di pagine;
  - il resto distribuito sulle consulenze, con anni distinti.
 
Il campione e' deterministico: seme fisso, ordinamento stabile. Rieseguire lo
script produce la stessa selezione, che e' cio' che rende ripetibile la
verifica dichiarata in tesi.
 
Uscite (versionate: contengono identificatori e URL, non testi):
  config/campione_verifica.csv     20 schede
  config/campione_ispezione.csv    30 schede
 
Uso:  python -m src.ingest.seleziona_campione
"""
from __future__ import annotations
 
import re
from pathlib import Path
 
import pandas as pd
 
MANIFEST = Path("manifest")
DEST = Path("config")
SEME = 20260806
 
RE_PAGINE = re.compile(r"Pagine\s*\|\s*(\d+)(?:\s*-\s*(\d+))?")
COLONNE = ["id_scheda", "url", "titolo", "rubrica_norm", "fascicolo", "anno",
           "pagine", "lunghezza", "url_pdf_scheda", "motivo_selezione"]
 
 
def anno(fascicolo: str) -> int:
    m = re.search(r"(20\d\d)/", str(fascicolo))
    return int(m.group(1)) if m else 0
 
 
def lunghezza(contesto: str) -> int:
    m = RE_PAGINE.search(str(contesto))
    if not m:
        return 0
    a = int(m.group(1))
    b = int(m.group(2)) if m.group(2) else a
    return b - a + 1
 
 
def pagine(contesto: str) -> str:
    m = RE_PAGINE.search(str(contesto))
    if not m:
        return ""
    return m.group(1) if not m.group(2) else f"{m.group(1)}-{m.group(2)}"
 
 
def prendi(pool: pd.DataFrame, scelte: dict, filtro, quanti: int, motivo: str,
           ordina: str | None = None, crescente: bool = True) -> None:
    """Aggiunge alla selezione, senza ripescare cio' che c'e' gia'."""
    cand = pool[filtro(pool) & ~pool["id_scheda"].isin(scelte)]
    if cand.empty:
        print(f"  ATTENZIONE: nessun candidato per «{motivo}»")
        return
    if ordina:
        cand = cand.sort_values(ordina, ascending=crescente)
    else:
        cand = cand.sample(frac=1, random_state=SEME)
    for _, r in cand.head(quanti).iterrows():
        scelte[r["id_scheda"]] = motivo
    presi = min(quanti, len(cand))
    if presi < quanti:
        print(f"  ATTENZIONE: «{motivo}» richiedeva {quanti}, disponibili {presi}")
 
 
def main() -> None:
    df = pd.read_csv(sorted(MANIFEST.glob("manifest_v0_prelim_*.csv"))[-1],
                     encoding="utf-8-sig", dtype=str)
    df["anno"] = df["fascicolo"].map(anno)
    df["lunghezza"] = df["contesto_riga"].map(lunghezza)
    df["pagine"] = df["contesto_riga"].map(pagine)
 
    # solo fascicoli chiusi, con PDF della scheda, e dentro il perimetro
    perimetro = {"CONSULENZA LINGUISTICA", "LA CRUSCA RISPOSE", "PAROLE NUOVE"}
    pool = df[(df["stato_fascicolo"] == "chiuso")
              & (df["url_pdf_scheda"].fillna("") != "")
              & (df["rubrica_norm"].isin(perimetro))
              & (df["lunghezza"] > 0)].copy()
    print(f"Pool: {len(pool)} schede di fascicoli chiusi, con PDF, entro il perimetro\n")
 
    # ---------- campione di VERIFICA ----------
    print("Campione di verifica (20):")
    v: dict[str, str] = {}
    prendi(pool, v, lambda d: d["anno"].between(2017, 2019), 4,
           "epoca 2017-2019: etichetta «Quesito:» mai verificata nell'HTML")
    prendi(pool, v, lambda d: d["rubrica_norm"] == "LA CRUSCA RISPOSE", 3,
           "rubrica La Crusca rispose: mai controllata")
    prendi(pool, v, lambda d: d["rubrica_norm"] == "PAROLE NUOVE", 2,
           "Parole nuove: profilo A2 da decidere")
    prendi(pool, v, lambda d: d["rubrica_norm"] == "CONSULENZA LINGUISTICA", 2,
           "scheda fra le piu' brevi", ordina="lunghezza", crescente=True)
    prendi(pool, v, lambda d: d["rubrica_norm"] == "CONSULENZA LINGUISTICA", 2,
           "scheda fra le piu' lunghe", ordina="lunghezza", crescente=False)
    prendi(pool, v, lambda d: d["anno"].between(2020, 2022), 3,
           "epoca 2020-2022")
    prendi(pool, v, lambda d: d["anno"].between(2023, 2025), 3,
           "epoca 2023-2025")
    prendi(pool, v, lambda d: d["rubrica_norm"] == "CONSULENZA LINGUISTICA", 1,
           "consulenza di completamento")
 
    ver = pool[pool["id_scheda"].isin(v)].copy()
    ver["motivo_selezione"] = ver["id_scheda"].map(v)
    ver = ver.sort_values(["anno", "id_scheda"])
 
    # ---------- campione di ISPEZIONE ----------
    print("\nCampione di ispezione (30):")
    i: dict[str, str] = dict(v)  # il campione di verifica ne fa parte
    prendi(pool, i, lambda d: d["rubrica_norm"] == "CONSULENZA LINGUISTICA", 6,
           "consulenza, distribuzione libera")
    prendi(pool, i, lambda d: d["lunghezza"] >= 6, 2, "scheda molto lunga",
           ordina="lunghezza", crescente=False)
    prendi(pool, i, lambda d: d["lunghezza"] == 1, 2, "scheda di una sola pagina")
    ins = pool[pool["id_scheda"].isin(i)].copy()
    ins["motivo_selezione"] = ins["id_scheda"].map(i)
    ins = ins.sort_values(["anno", "id_scheda"])
 
    DEST.mkdir(exist_ok=True)
    ver[COLONNE].to_csv(DEST / "campione_verifica.csv", index=False,
                        encoding="utf-8", lineterminator="\n")
    ins[COLONNE].to_csv(DEST / "campione_ispezione.csv", index=False,
                        encoding="utf-8", lineterminator="\n")
 
    print("\n" + "=" * 72)
    print(f"VERIFICA: {len(ver)} schede")
    print("=" * 72)
    print(ver[["id_scheda", "anno", "rubrica_norm", "pagine", "lunghezza",
               "titolo"]].to_string(index=False, max_colwidth=46))
    print(f"\nAnni coperti: {sorted(ver['anno'].unique())}")
    print(f"Rubriche: {dict(ver['rubrica_norm'].value_counts())}")
    print(f"Lunghezze: min {ver['lunghezza'].min()}, max {ver['lunghezza'].max()}")
    print(f"\nISPEZIONE: {len(ins)} schede  ->  {DEST/'campione_ispezione.csv'}")
 
 
if __name__ == "__main__":
    main()