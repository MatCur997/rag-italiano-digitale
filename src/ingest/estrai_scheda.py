# -*- coding: utf-8 -*-
"""Estrattore definitivo della pagina-scheda HTML (schede dal 2019).

Produce un `Documento`: metadati letti dalla fonte, struttura argomentativa
segmentata, testo con gli span di formattazione conservati come intervalli.

CONTRATTO DEL TESTO. Il testo e' piatto; la formattazione e' una lista di
`(inizio, fine, tipo)` sugli indici di quel testo. Non si inseriscono marcatori
nel testo: cio' che viene indicizzato resta pulito, e l'informazione tipografica
resta disponibile a parte. Si conserva la **tipografia**, non la **semantica**:
il corsivo marca la menzione, ma anche titoli, latinismi, citazioni ed enfasi
(Dossier §4.3).

CONTRATTO STRUTTURALE, rilevato il 7/8 su cinque schede:
  - `div.col-md-4` e' il blocco «Nella stessa rubrica»: si elimina per primo,
    altrimenti ogni documento porta i titoli di altri cinque (rischio 13);
  - il corpo sta in `div.col-md-8`; il blocco di metadati si chiude con `<hr>`;
  - il corpo e' una sequenza piatta di `<p>`, `<blockquote class="cit">` e
    liste; i `blockquote.cit` isolano attestazioni ed esempi;
  - chiude un `h4` «Parole chiave» seguito da `ul`;
  - il quesito e' introdotto dall'etichetta «Quesito:», riconosciuta **sul
    testo** e non sul markup: e' `h4` solo dal 2020, semplice `<p>` nel 2019
    (decisione 7/8);
  - il confine fra quesito e corpo e' dato dalla ripetizione del titolo.

Segmentazione A2, tripartita (decisione 7/8): quesito | corpo argomentativo |
esempi. Risposta sintetica e spiegazione non sono distinguibili nel markup e
restano fuse nel corpo. *Parole nuove* non ha quesito: profilo a due parti.

Uso come modulo:
    from src.ingest.estrai_scheda import documento_da_html
Collaudo sul campione gia' scaricato (nessuna richiesta di rete):
    python -m src.ingest.estrai_scheda
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag

BOILERPLATE = "div.col-md-4"
CORPO = "div.col-md-8"
SCARTA = ("script", "style", "noscript")
CORSIVO = {"i", "em"}
GRASSETTO = {"b", "strong"}
BLOCCHI = ("p", "blockquote", "ul", "ol", "h1", "h2", "h3", "h4", "h5",
           "table", "figure", "hr")
RE_QUESITO = re.compile(r"^\s*quesito\s*:", re.I)


@dataclass
class Blocco:
    """Unita' minima del corpo: un paragrafo, un esempio, un elenco."""
    tipo: str                    # paragrafo | esempio | elenco | altro
    testo: str
    span: list[tuple[int, int, str]] = field(default_factory=list)


@dataclass
class Documento:
    id_scheda: str
    url: str = ""
    titolo: str = ""
    autori: str = ""
    data_pubblicazione: str = ""
    doi: str = ""
    fascicolo: str = ""
    pagina_iniziale: str = ""
    issn: str = ""
    editore: str = ""
    licenza_testo: str = ""
    licenza_url: str = ""
    quesito: str = ""
    quesito_span: list[tuple[int, int, str]] = field(default_factory=list)
    corpo: list[Blocco] = field(default_factory=list)
    parole_chiave: list[str] = field(default_factory=list)
    qualita_parsing: list[str] = field(default_factory=list)

    @property
    def esempi(self) -> list[Blocco]:
        return [b for b in self.corpo if b.tipo == "esempio"]

    @property
    def testo_corpo(self) -> str:
        return "\n\n".join(b.testo for b in self.corpo)


# --------------------------------------------------------------- testo e span

def _fondi(span: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Unisce gli intervalli contigui dello stesso tipo.

    Il markup della fonte spezza i run di corsivo anche a meta' parola: senza
    questa fusione un'unica forma menzionata risulterebbe in tre intervalli.
    """
    fusi: list[tuple[int, int, str]] = []
    for inizio, fine, tipo in sorted(span, key=lambda s: (s[2], s[0])):
        if fusi and fusi[-1][2] == tipo and inizio <= fusi[-1][1]:
            a, b, t = fusi[-1]
            fusi[-1] = (a, max(b, fine), t)
        else:
            fusi.append((inizio, fine, tipo))
    return sorted(fusi)


def testo_e_span(el: Tag) -> tuple[str, list[tuple[int, int, str]]]:
    """Percorre il DOM restituendo testo normalizzato negli spazi e intervalli."""
    pezzi: list[str] = []
    span: list[tuple[int, int, str]] = []
    lunghezza = 0

    def aggiungi(t: str, stili: frozenset[str]) -> None:
        nonlocal lunghezza
        t = re.sub(r"\s+", " ", t)
        if not t:
            return
        if t == " " and (not pezzi or pezzi[-1].endswith(" ")):
            return
        if pezzi and pezzi[-1].endswith(" ") and t.startswith(" "):
            t = t.lstrip()
            if not t:
                return
        inizio = lunghezza
        pezzi.append(t)
        lunghezza += len(t)
        for s in stili:
            span.append((inizio, lunghezza, s))

    def cammina(nodo: Tag, stili: frozenset[str]) -> None:
        for figlio in nodo.children:
            if isinstance(figlio, NavigableString):
                aggiungi(str(figlio), stili)
            elif isinstance(figlio, Tag):
                nuovi = set(stili)
                if figlio.name in CORSIVO:
                    nuovi.add("corsivo")
                if figlio.name in GRASSETTO:
                    nuovi.add("grassetto")
                if figlio.name in ("li", "br"):
                    aggiungi(" ", stili)
                cammina(figlio, frozenset(nuovi))

    cammina(el, frozenset())
    testo = "".join(pezzi)
    testo = unicodedata.normalize("NFC", testo)
    scarto = len(testo) - len(testo.lstrip())
    testo = testo.strip()
    corretti = [(max(0, a - scarto), min(len(testo), b - scarto), t)
                for a, b, t in span if b - scarto > 0 and a - scarto < len(testo)]
    return testo, _fondi([s for s in corretti if s[0] < s[1]])


# ------------------------------------------------------------------ metadati

def metadati(z: BeautifulSoup) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in z.find_all("meta"):
        nome = (m.get("name") or m.get("property") or "").strip()
        if nome:
            out[nome] = " ".join(str(m.get("content", "")).split())
    return out


def licenza(corpo: Tag) -> tuple[str, str]:
    """Stringa letterale della licenza e URL, letti dalla fonte.

    Il valore non va mai assunto: il portale dichiara CC BY 4.0 per il sito e
    CC BY-NC-ND 4.0 per gli articoli (decisione 6/8), e il campo deve
    registrare cio' che la singola scheda afferma.
    """
    testo = ""
    for p in corpo.find_all("p"):
        t = " ".join(p.get_text(" ", strip=True).split())
        if t.lower().startswith("licenza"):
            testo = t
            testo = re.split(r"\bCopyright\b", testo)[0].strip()
            break
    url = ""
    for a in corpo.find_all("a", href=True):
        if "creativecommons.org" in a["href"]:
            url = a["href"]
            break
    return testo, url


# ------------------------------------------------------------------ struttura

def _blocchi_del_corpo(corpo: Tag) -> list[Tag]:
    """Elementi di blocco in ordine di documento, senza annidati."""
    fuori: list[Tag] = []
    for el in corpo.find_all(BLOCCHI):
        if any(a in fuori for a in el.parents):
            continue
        fuori.append(el)
    return fuori


def _confronta(a: str, b: str) -> bool:
    pulisci = lambda s: re.sub(r"[^\w]+", "", s.lower())
    return bool(a) and pulisci(a) == pulisci(b)


def _tipo(el: Tag) -> str:
    if el.name == "blockquote":
        return "esempio"
    if el.name in ("ul", "ol"):
        return "elenco"
    if el.name == "p":
        return "paragrafo"
    return "altro"


def documento_da_html(dati: bytes, id_scheda: str, url: str = "") -> Documento:
    z = BeautifulSoup(dati, "lxml")
    for el in z.select(BOILERPLATE):
        el.decompose()
    for nome in SCARTA:
        for el in z.find_all(nome):
            el.decompose()

    m = metadati(z)
    d = Documento(
        id_scheda=id_scheda,
        url=url or m.get("DC.Identifier.URI", ""),
        titolo=m.get("citation_title", "").strip(),
        autori=m.get("citation_author", "").strip(),
        data_pubblicazione=m.get("citation_publication_date", ""),
        doi=m.get("citation_doi", ""),
        fascicolo=m.get("DC.Source", ""),
        pagina_iniziale=m.get("citation_firstpage", ""),
        issn=m.get("citation_issn", ""),
        editore=m.get("citation_publisher", ""),
    )

    corpo = z.select_one(CORPO)
    if corpo is None:
        d.qualita_parsing.append("contenitore del corpo non trovato")
        return d
    d.licenza_testo, d.licenza_url = licenza(corpo)
    if not d.licenza_testo:
        d.qualita_parsing.append("licenza non letta dalla pagina")

    blocchi = _blocchi_del_corpo(corpo)

    # confine superiore: primo <hr>, che chiude il blocco di metadati
    inizio = next((i for i, el in enumerate(blocchi) if el.name == "hr"), None)
    if inizio is None:
        d.qualita_parsing.append("<hr> di apertura assente: confine presunto")
        inizio = 0
    else:
        inizio += 1

    # confine inferiore: h4 «Parole chiave»
    fine = len(blocchi)
    for i in range(inizio, len(blocchi)):
        if blocchi[i].name.startswith("h") and \
                blocchi[i].get_text(strip=True).lower().startswith("parole chiave"):
            fine = i
            if i + 1 < len(blocchi) and blocchi[i + 1].name in ("ul", "ol"):
                d.parole_chiave = [" ".join(li.get_text(" ", strip=True).split())
                                   for li in blocchi[i + 1].find_all("li")]
            break
    else:
        d.qualita_parsing.append("blocco «Parole chiave» assente")
    if not d.parole_chiave and m.get("citation_keywords"):
        d.parole_chiave = [k.strip() for k in m["citation_keywords"].split(";")
                           if k.strip()]

    utili = blocchi[inizio:fine]

    # quesito: riconosciuto sul testo dell'etichetta, non sul markup
    i_q = next((i for i, el in enumerate(utili)
                if RE_QUESITO.match(el.get_text(" ", strip=True))), None)
    i_corpo = 0
    if i_q is not None:
        # il confine con il corpo e' la ripetizione del titolo
        i_t = next((i for i in range(i_q, len(utili))
                    if _confronta(d.titolo, utili[i].get_text(" ", strip=True))),
                   None)
        blocchi_q = utili[i_q:i_t] if i_t is not None else [utili[i_q]]
        if i_t is None:
            d.qualita_parsing.append("titolo ripetuto assente: quesito presunto "
                                     "al solo blocco dell'etichetta")
        testi, spans = [], []
        for el in blocchi_q:
            t, s = testo_e_span(el)
            t = RE_QUESITO.sub("", t).strip()
            if not t:
                continue
            base = sum(len(x) + 1 for x in testi)
            testi.append(t)
            spans += [(a + base, b + base, k) for a, b, k in s]
        d.quesito = " ".join(testi)
        d.quesito_span = _fondi(spans)
        i_corpo = (i_t + 1) if i_t is not None else (i_q + 1)
    else:
        i_a = next((i for i, el in enumerate(utili)
                    if el.name.startswith("h")
                    and el.get_text(strip=True).lower().startswith("abstract")),
                   None)
        if i_a is not None:
            testi, spans = [], []
            for el in utili[i_a + 1:]:
                if el.name.startswith("h") or el.name == "hr":
                    break
                t, s = testo_e_span(el)
                if not t:
                    continue
                base = sum(len(x) + 1 for x in testi)
                testi.append(t)
                spans += [(a + base, b + base, k) for a, b, k in s]
                i_corpo = utili.index(el) + 1
            d.quesito = " ".join(testi)
            d.quesito_span = _fondi(spans)
            d.qualita_parsing.append(
                "quesito ricavato dal blocco «Abstract» (La Crusca rispose)")
        else:
            d.qualita_parsing.append(
                "etichetta «Quesito:» assente: profilo a due parti")

    for el in utili[i_corpo:]:
        if el.name == "hr":
            continue
        t, s = testo_e_span(el)
        if not t:
            continue
        d.corpo.append(Blocco(_tipo(el), t, s))

    if not d.corpo:
        d.qualita_parsing.append("corpo vuoto")
    return d


# ------------------------------------------------------------------ collaudo

def _collaudo() -> None:
    import pandas as pd
    df = pd.read_csv("config/campione_verifica.csv", encoding="utf-8", dtype=str)
    print(f"{'id':>7} {'blocchi':>7} {'esempi':>6} {'car_q':>6} {'car_corpo':>9} "
          f"{'corsivi':>7} {'chiavi':>6}  licenza / note")
    for _, r in df.iterrows():
        f = next(Path("data/raw/campione").glob(f"{r['id_scheda']}_*.html"), None)
        if f is None:
            continue
        d = documento_da_html(f.read_bytes(), r["id_scheda"], r["url"])
        corsivi = sum(1 for b in d.corpo for s in b.span if s[2] == "corsivo")
        note = d.licenza_testo or "—"
        if d.qualita_parsing:
            note += "  ||  " + "; ".join(d.qualita_parsing)
        print(f"{d.id_scheda:>7} {len(d.corpo):>7} {len(d.esempi):>6} "
              f"{len(d.quesito):>6} {len(d.testo_corpo):>9} {corsivi:>7} "
              f"{len(d.parole_chiave):>6}  {note}")


if __name__ == "__main__":
    _collaudo()
