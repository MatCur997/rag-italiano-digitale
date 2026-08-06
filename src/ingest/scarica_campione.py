# -*- coding: utf-8 -*-
"""Passo 4 — Scaricamento del campione di verifica (20 schede).

Scarica, per ciascuna delle 20 schede selezionate da `seleziona_campione.py`,
la pagina-scheda in HTML e il PDF della singola scheda. Archivia i byte grezzi
senza alcuna conversione e ne registra l'impronta.

Non estrae testo e non confronta nulla: e' solo l'acquisizione dell'input del
protocollo di verifica HTML<->PDF (Dossier §4.4). La separazione fra
scaricamento e confronto e' voluta: il confronto va poter essere rieseguito
molte volte, cambiando la normalizzazione, senza toccare la rete.

Uscite:
  data/raw/campione/<id>_<stamp>.html     pagina-scheda, byte grezzi
  data/raw/campione/<id>_<stamp>.pdf      PDF della scheda, byte grezzi
  manifest/checksum_campione_<stamp>.csv  impronte e dimensioni (versionato)
  manifest/verbale_campione_<stamp>.txt   verbale di scaricamento (versionato)

Idempotente: rieseguirlo sovrascrive i file della stessa data.

Uso:  python -m src.ingest.scarica_campione     (dalla radice del progetto)
"""
from __future__ import annotations

import csv
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pandas as pd

from src.config import carica

CAMPIONE = Path("config/campione_verifica.csv")
DEST = Path("data/raw/campione")
DIR_MANIFEST = Path("manifest")


def preleva(client: httpx.Client, url: str, percorso: Path) -> dict:
    """Scarica un URL e archivia i byte come ricevuti."""
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        return {"esito": f"errore di rete: {type(e).__name__}", "byte": 0,
                "sha256": "", "url_finale": "", "tipo": ""}
    if r.status_code != 200:
        return {"esito": f"HTTP {r.status_code}", "byte": 0,
                "sha256": "", "url_finale": str(r.url), "tipo": ""}
    percorso.write_bytes(r.content)
    return {"esito": "ok", "byte": len(r.content),
            "sha256": hashlib.sha256(r.content).hexdigest(),
            "url_finale": str(r.url),
            "tipo": r.headers.get("content-type", "?")}


def main() -> None:
    conf = carica()
    momento = datetime.now(timezone.utc).astimezone()
    stamp = momento.strftime("%Y%m%d")
    DEST.mkdir(parents=True, exist_ok=True)
    DIR_MANIFEST.mkdir(exist_ok=True)

    df = pd.read_csv(CAMPIONE, encoding="utf-8", dtype=str)
    righe: list[dict] = []
    verbale = [
        "SCARICAMENTO DEL CAMPIONE DI VERIFICA",
        f"Momento dell'accesso: {momento.isoformat(timespec='seconds')}",
        f"User-Agent: {conf['user_agent']}",
        f"Ritardo fra le richieste: {conf['ritardo_secondi']} s",
        f"Schede nel campione: {len(df)}",
        "",
    ]

    with httpx.Client(headers={"User-Agent": conf["user_agent"]},
                      timeout=conf["timeout_secondi"],
                      follow_redirects=True) as client:

        for n, (_, s) in enumerate(df.iterrows(), 1):
            ids = s["id_scheda"]
            print(f"[{n:>2}/{len(df)}] {ids}  {str(s['titolo'])[:44]}")

            h = preleva(client, s["url"], DEST / f"{ids}_{stamp}.html")
            time.sleep(conf["ritardo_secondi"])
            p = preleva(client, s["url_pdf_scheda"], DEST / f"{ids}_{stamp}.pdf")
            time.sleep(conf["ritardo_secondi"])

            for fonte, r, url in (("html", h, s["url"]),
                                  ("pdf", p, s["url_pdf_scheda"])):
                righe.append({
                    "id_scheda": ids, "fonte": fonte, "url": url,
                    "url_finale": r["url_finale"], "esito": r["esito"],
                    "byte": r["byte"], "content_type": r["tipo"],
                    "sha256": r["sha256"], "data_accesso": momento.isoformat(
                        timespec="seconds"),
                })
                verbale.append(f"{ids}  {fonte:<4}  {r['esito']:<12}  "
                               f"{r['byte']:>8} byte  {r['sha256'][:16]}…  "
                               f"{r['tipo']}")
            if h["esito"] != "ok" or p["esito"] != "ok":
                print(f"        ATTENZIONE  html={h['esito']}  pdf={p['esito']}")

    falliti = [r for r in righe if r["esito"] != "ok"]
    verbale += ["", f"Richieste inviate: {len(righe)}",
                f"Scaricamenti riusciti: {len(righe) - len(falliti)}",
                f"Falliti: {len(falliti)}"]
    if falliti:
        verbale.append("Schede da riesaminare: "
                       + ", ".join(sorted({r['id_scheda'] for r in falliti})))

    with (DIR_MANIFEST / f"checksum_campione_{stamp}.csv").open(
            "w", newline="", encoding="utf-8") as fo:
        w = csv.DictWriter(fo, fieldnames=list(righe[0].keys()))
        w.writeheader()
        w.writerows(righe)
    (DIR_MANIFEST / f"verbale_campione_{stamp}.txt").write_text(
        "\n".join(verbale) + "\n", encoding="utf-8", newline="\n")

    print("\n".join(verbale[-4:]))
    print(f"\nFile in {DEST}  |  impronte in {DIR_MANIFEST}")


if __name__ == "__main__":
    main()
