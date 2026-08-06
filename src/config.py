# -*- coding: utf-8 -*-
"""Lettura dei parametri di acquisizione da config/acquisizione.yaml.
 
Esiste per una ragione sola: i parametri della raccolta devono stare in un
posto solo. Prima di questo modulo erano duplicati in tre script, e il giorno
in cui il ritardo fosse cambiato ci si sarebbe dovuti ricordare di tre file.
 
Uso da altri moduli:
    from src.config import carica
    conf = carica()
    ua = conf["user_agent"]
 
Uso da riga di comando (stampa i parametri correnti):
    python src/config.py
"""
from __future__ import annotations
 
from datetime import datetime
from pathlib import Path
from typing import Any
 
import yaml
 
PERCORSO = Path("config/acquisizione.yaml")
 
 
def carica() -> dict[str, Any]:
    """Restituisce i parametri. Solleva errore se eseguito fuori dalla radice."""
    if not PERCORSO.exists():
        raise FileNotFoundError(
            f"{PERCORSO} non trovato. Gli script vanno eseguiti dalla radice "
            "del progetto, non dalla cartella in cui risiedono."
        )
    with PERCORSO.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
 
 
def scrivi_data_crawl(momento: datetime) -> None:
    """Registra il cutoff nel file di configurazione, una volta sola.
 
    Solleva un errore se il valore e' gia' presente: il cutoff e' la data
    dichiarata in tesi, un secondo crawl non e' previsto, e una sua modifica
    dev'essere una decisione annotata nel registro, non l'effetto collaterale
    di uno script rilanciato per sbaglio.
    """
    conf = carica()
    if conf.get("data_crawl"):
        raise ValueError(
            f"data_crawl e' gia' fissata a {conf['data_crawl']} e non va "
            "sovrascritta. Se la raccolta va davvero rifatta, la decisione "
            "va presa e annotata nel registro del Dossier."
        )
    testo = PERCORSO.read_text(encoding="utf-8")
    if "data_crawl: null" not in testo:
        raise ValueError("Riga 'data_crawl: null' non trovata nel file.")
    testo = testo.replace(
        "data_crawl: null",
        f'data_crawl: "{momento.isoformat(timespec="seconds")}"',
    )
    PERCORSO.write_text(testo, encoding="utf-8", newline="\n")
 
 
if __name__ == "__main__":
    conf = carica()
    larghezza = max(len(k) for k in conf)
    for chiave, valore in conf.items():
        print(f"{chiave:<{larghezza}}  {valore}")
 