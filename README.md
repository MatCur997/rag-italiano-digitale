# Sistema RAG di consulenza linguistica su *Italiano digitale*

Apparato sperimentale di una tesi magistrale in Linguistica Computazionale.
Studio sperimentale di un sistema di Retrieval-Augmented Generation fondato
sulle schede della rivista *Italiano digitale*. Non è un'applicazione né un
servizio: il codice serve a condurre e a rendere riproducibili gli esperimenti
descritti nella tesi.

## Fonte dei dati

I testi provengono da *Italiano digitale*, rivista dell'Accademia della Crusca
(e-ISSN 2532-9006), https://id.accademiadellacrusca.org.

Titolarità dei contenuti: **Accademia della Crusca**.
Licenza dei contenuti: **CC BY-NC-ND 4.0**, verificata e registrata per singola
scheda. Alcune rubriche di servizio non ricadono sotto licenza aperta e sono
escluse dal corpus.

## Che cosa questo repository non contiene

In ottemperanza alle clausole NC e ND, **non** sono versionati né ridistribuiti:

- i testi delle schede, in qualunque forma;
- i loro derivati: testo normalizzato, segmenti, rappresentazioni vettoriali, indici.

Il corpus è ricostruibile in locale a partire dal manifest, che riporta
identificatori stabili, DOI, URL, data di accesso e checksum, tramite gli script
di acquisizione qui inclusi.

## Che cosa contiene

Script di acquisizione e preprocessing, indicizzazione, retrieval, generazione e
valutazione; configurazioni di ogni esperimento; manifest del corpus; insieme dei
quesiti; giudizi di rilevanza espressi come riferimenti a identificatori di scheda;
linee guida di annotazione e griglia di valutazione; risultati aggregati.

## Ambiente

- Python 3.12.10
- PyTorch 2.11.0+cu128, CUDA 12.8 (GPU NVIDIA RTX 5070 Ti, sm_120, bf16)
- Dipendenze in `requirements.txt`

`torch` va installato dall'indice dedicato:
`pip install torch --index-url https://download.pytorch.org/whl/cu128`

## Licenza del codice

Apache License 2.0 (vedi `LICENSE`). La licenza del codice non si estende ai
contenuti di *Italiano digitale*, che restano soggetti a CC BY-NC-ND 4.0.

## Citazione della fonte

Ogni scheda utilizzata è citata con autore, titolo, rivista, fascicolo e DOI,
secondo il riquadro «Cita come» della fonte.