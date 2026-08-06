"""Ispezione e segmentazione dei fascicoli di *Italiano digitale* (PDF).
 
Per ogni PDF nella cartella indicata:
  - identifica il fascicolo (anno/numero) e conta le pagine;
  - individua le schede tramite i riquadri "Cita come:" (uno per scheda);
  - assegna a ogni scheda rubrica, licenza, data di pubblicazione, DOI (dal 2020),
    pagine (layout 2017-2019), titolo e autori (best effort, due epoche di layout);
  - scrive un CSV con una riga per scheda e stampa un riepilogo.
 
Uso:  python ispeziona_corpus.py --dir cartella_pdf --csv schede.csv
Richiede:  pip install pymupdf
 
Note verificate sul campione 2017-2025:
  * Epoca A (2017-2023): riquadro «Autori, "Titolo", Italiano digitale, AAAA, N, (mesi), pp. X-Y»
    oppure «"Titolo", a cura di X, ...»; etichetta "Quesito:" presente nelle consulenze.
  * Epoca B (2024-): riquadro multilinea con DOI, titolo senza virgolette; l'etichetta
    "Quesito:" scompare (il quesito e' il blocco fra la data e il capolettera della risposta);
    font Type3 anonimi: il corsivo non e' piu' leggibile dai flag, solo per euristica.
  * I nomi di rubrica variano negli anni: normalizzati tramite ALIAS.
"""
import argparse, bisect, csv, os, re
import fitz  # PyMuPDF
 
HDR = re.compile(r"(?m)^([A-Z\u00c0-\u00d9][A-Z\u00c0-\u00d9 '\u2019&\-]{3,})\s*\|")
ALIAS = {
    "CONSULENZE LINGUISTICHE": "CONSULENZA",
    "CONSULENZA LINGUISTICA": "CONSULENZA",
    "GLI ARTICOLI": "ARTICOLI",
}
 
 
def identifica_fascicolo(doc):
    testa = "".join(doc[i].get_text() for i in range(min(4, doc.page_count)))
    m = re.search(r"(20\d\d)\s*/\s*(\d+)", testa)
    return f"{m.group(1)}/{m.group(2)}" if m else "?"
 
 
def analizza_pdf(percorso):
    doc = fitz.open(percorso)
    nome = os.path.basename(percorso)
    full = "\n".join(p.get_text() for p in doc)
    fasc = identifica_fascicolo(doc)
 
    hdrs = [(m.start(), m.group(1).strip()) for m in HDR.finditer(full)]
    hpos = [h[0] for h in hdrs]
    dates = [(m.start(), m.group(1)) for m in
             re.finditer(r"PUBBLICATO:\s*(\d{1,2}\s+[A-Z\u00c0-\u00d9]+\s+\d{4})", full)]
    dpos = [x[0] for x in dates]
 
    righe = []
    for m in re.finditer(r"Cita come:", full):
        w_raw = full[m.start():m.start() + 700]
        w = re.sub(r"\s+", " ", w_raw)
        lic = ("CC BY-NC-ND" if "Pubblicato con licenza" in w
               else "riservati" if "Tutti i diritti riservati" in w else "?")
        mdoi = re.search(r"DOI:\s*(10\.\S+)", w)
        doi = mdoi.group(1) if mdoi else None
 
        aut = tit = pag = None
        ok = False
        mA = re.search(r'Cita come:\s*([^\u201c\u201d"]+?),\s*[\u201c"](.+?)[\u201d"],\s*Italiano digitale,\s*20\d\d', w)
        mB = re.search(r'Cita come:\s*[\u201c"](.+?)[\u201d"],\s*(a cura d[^,]+),\s*Italiano digitale', w)
        if mA:
            aut, tit, ok = mA.group(1).strip(), mA.group(2).strip(), True
        elif mB:
            tit, aut, ok = mB.group(1).strip(), mB.group(2).strip(), True
        elif doi or '\u201cItaliano' in w_raw or '"Italiano' in w_raw:
            # Epoca B: autore sulla prima riga, titolo sulle successive
            linee = [l.strip() for l in w_raw.split("\n")[1:] if l.strip()]
            if linee:
                aut = linee[0].rstrip(",")
                tl = []
                for l in linee[1:]:
                    if "Italiano digitale" in l:
                        break
                    tl.append(l)
                tit = re.sub(r"\s*,\s*$", "", " ".join(tl)) or None
                ok = bool(tit)
        mp = re.search(r"pp?\.\s*(\d+(?:-\d+)?)", w)
        if mp:
            pag = mp.group(1)
 
        i = bisect.bisect_right(hpos, m.start()) - 1
        rubrica = hdrs[i][1] if i >= 0 else "?"
        j = bisect.bisect_right(dpos, m.start()) - 1
        data = dates[j][1] if j >= 0 else None
 
        righe.append(dict(
            file=nome, fascicolo=fasc, pagine_fascicolo=doc.page_count,
            rubrica=rubrica, rubrica_norm=ALIAS.get(rubrica, rubrica),
            titolo=tit, autori=aut, data_pubblicazione=data,
            pagine=pag, doi=doi, licenza=lic, parse_ok=ok,
        ))
    return righe
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="cartella con i PDF dei fascicoli")
    ap.add_argument("--csv", default="schede.csv", help="file CSV di uscita")
    args = ap.parse_args()
 
    righe = []
    for f in sorted(os.listdir(args.dir)):
        if f.lower().endswith(".pdf"):
            righe.extend(analizza_pdf(os.path.join(args.dir, f)))
 
    if not righe:
        print("Nessun PDF trovato in", args.dir)
        return
 
    with open(args.csv, "w", newline="", encoding="utf-8-sig") as fo:
        wcsv = csv.DictWriter(fo, fieldnames=list(righe[0].keys()))
        wcsv.writeheader()
        wcsv.writerows(righe)
 
    from collections import Counter
    per_file = Counter(r["file"] for r in righe)
    per_rub = Counter(r["rubrica_norm"] for r in righe)
    cons = [r for r in righe if r["rubrica_norm"] == "CONSULENZA"]
    print("Schede totali:", len(righe))
    print("Per fascicolo:", dict(per_file))
    print("Per rubrica:", dict(per_rub.most_common()))
    print("Consulenze:", len(cons),
          "| con data:", sum(1 for r in cons if r["data_pubblicazione"]),
          "| con DOI:", sum(1 for r in cons if r["doi"]),
          "| titolo/autori estratti:", sum(1 for r in cons if r["parse_ok"]))
    print("Licenze (tutte le schede):", dict(Counter(r["licenza"] for r in righe)))
    print("CSV scritto in:", args.csv)
 
 
if __name__ == "__main__":
    main()