# Convertitore Arkos Tracker → CVBasic

Documentazione del progetto `arkos_to_cvbasic.py`: legge un file musicale
esportato da **Arkos Tracker 3** (formato testo) e produce un blocco di
musica in **CVBasic**, pronto per ColecoVision, MSX e Sega SG-1000.

---

## 1. Scopo

Arkos Tracker e CVBasic usano due formati incompatibili:

| | Arkos Tracker | CVBasic |
|---|---|---|
| Note | numeri tipo-MIDI (`note 40`) | nomi letterali (`E3`) |
| Durata | speed track + effetto `forceInstrumentSpeed` | conteggio di `S` su un `DATA BYTE` fisso |
| Struttura | pattern/tracce multipli | sequenza lineare di `MUSIC` |
| Chip | AY-3-8910 (PSG) | SN76489 / AY astratti da CVBasic |

Il convertitore traduce in modo meccanico, **ignorando le definizioni
degli strumenti**, e ricostruisce due aspetti temporali del brano: la
velocità di riproduzione e la durata variabile delle singole note.

---

## 2. Struttura del file Arkos Tracker

Il file è un testo a sezioni annidate (`SECTION` / `ENDSECTION`, con il
numero di trattini iniziali a indicare la profondità). Le parti che
contano per la conversione sono:

- **subsong** → `initialSpeed` (velocità di partenza, in frame per riga)
  e `replayFrequencyHz` (50 Hz).
- **tracks** → ogni traccia ha un `index` e una lista di **celle**. Ogni
  cella ha:
  - `index`: la **riga** del pattern (posizione verticale);
  - `note`: numero di nota in stile MIDI (0 = C-0), assente se la cella
    contiene solo un effetto;
  - `instrument`: ignorato;
  - eventuale effetto `forceInstrumentSpeed` con `logicalValue`
    (la colonna `sXX` del tracker).
- **speedTracks** → tracce di velocità; ogni cella ha `index` (riga) e
  `value` (nuova velocità; **`0` significa "nessun cambio"**).
- **positions** → l'ordine di riproduzione: ogni posizione punta a un
  `patternIndex` e ha una `height` (numero di righe).
- **patterns** → ogni pattern punta a **3 `trackIndex`** (i canali PSG
  A, B, C) e a uno `speedTrackIndex`.

> Nota: in questo brano solo 2 dei 3 canali per pattern contengono note;
> il terzo è silenzioso, ed è normale.

---

## 3. Logica di conversione

### 3.1 Note e ottave

```
ottava = note // 12 + offset
indice_nota = note % 12   →  C, C#, D, D#, E, F, F#, G, G#, A, A#, B
```

Il nome CVBasic mette il diesis **dopo** l'ottava, es. `A4#`. Con
`offset 0` il risultato combacia con la numerazione di Arkos (nota 52 =
`E-4` → `E4`). Le ottave fuori dal range CVBasic (2–6) vengono
agganciate al limite più vicino; solo le pochissime note sotto l'ottava
2 vengono perciò alzate, limite fisico di CVBasic.

### 3.2 Velocità (speed track)

CVBasic ha **un solo `DATA BYTE`** per tutto il brano, quindi non si può
cambiare il tick a metà. Il convertitore risolve così:

1. parte da `initialSpeed`;
2. scorrendo le righe in ordine di riproduzione, aggiorna la velocità
   corrente quando il speed track ha un valore diverso da 0; la velocità
   **si propaga** da un pattern al successivo;
3. ogni riga genera `passi = max(1, round(velocità / data_byte))`
   istruzioni `MUSIC`.

Così un cambio di velocità diventa "più (o meno) passi per riga" e resta
fedele anche con cambi multipli a metà brano.

### 3.3 Durata variabile delle note (articolazione)

La durata percepita nel tracker non viene dalla posizione delle note (in
molti passaggi c'è una nota per riga) ma dall'effetto
`forceInstrumentSpeed` (`sXX`), che regola l'inviluppo dello strumento.
Mappa applicata:

- `s00` o effetto assente → **nessuna forzatura**: la nota suona piena
  fino alla nota successiva (tenuta);
- `sNN` con N > 0 → la parte in suono dura `round(N × length_scale)`
  passi, comunque **tagliata** dalla nota successiva (non si sovrappone);
- una nota senza effetto **eredita** l'ultimo valore di velocità del
  canale (comportamento naturale del tracker).

Ogni passo diventa un token: nome nota all'attacco, `S` per il
prolungamento, `-` per il silenzio.

### 3.4 Composizione finale

I tre canali vengono affiancati passo per passo:

```
MUSIC <voce0>,<voce1>,<voce2>
```

---

## 4. Parametri da riga di comando

```
python arkos_to_cvbasic.py INPUT.txt OUTPUT.bas [opzioni]
```

| Opzione | Default | Significato |
|---|---|---|
| `--offset N` | `0` | ottave da aggiungere (0 = come Arkos) |
| `--data-byte N` | `2` | frame per passo `MUSIC`; più basso = più fedele ma più righe; `1` = tempo esatto |
| `--length-scale F` | `1.5` | allunga la parte in suono delle note (1.0 = base) |
| `--invert` | off | inverte la scala: `sXX` alto = nota più corta |
| `--label NOME` | `musica` | etichetta del blocco musicale |

A fine esecuzione lo script stampa le velocità trovate nel tracker e il
numero di righe `MUSIC` generate, utile per verificare la lettura.

### Esempi

```
python arkos_to_cvbasic.py musica.txt musica.bas --data-byte 1   # tempo esatto
python arkos_to_cvbasic.py musica.txt musica.bas                 # default bilanciato
python arkos_to_cvbasic.py musica.txt musica.bas --length-scale 2.5
```

---

## 5. Uso dell'output in CVBasic

```basic
    PLAY FULL
    PLAY musica
    WHILE 1: WEND

    INCLUDE "musica.bas"
```

Usa `PLAY FULL` perché il brano usa più voci. Con `PLAY SIMPLE` suonano
solo le prime due, liberando un canale per gli effetti sonori. I dati
stanno in ROM (non intaccano la RAM) ma occupano spazio cartuccia:
attenzione se sei vicino al limite del banco.

---

## 6. Scelte progettuali e assunzioni

- **`s00` = tenuta piena**, non lunghezza zero: era la causa per cui le
  note risultavano troppo corte e `length_scale` sembrava inefficace.
- **Velocità che si propaga** tra pattern, con `0 = nessun cambio`, come
  in Arkos.
- **Astrazione del chip**: sia Arkos sia CVBasic sono tarati su
  La = 440 Hz. CVBasic genera i periodi corretti per SN76489 e AY a
  partire dal nome nota, quindi la conversione a livello di nome è
  indipendente dal chip e dal clock dell'AY.
- **Strumenti ignorati**: nessun `W/X/Y/Z`, tutte le voci usano il piano
  di default; volendo si può differenziare appendendo la lettera dello
  strumento alla prima nota di ogni voce.
- **Direzione di `sXX`** (alto = più lungo) dedotta all'ascolto;
  invertibile con `--invert`.

---

## 7. Limiti noti

- Un solo `DATA BYTE` per brano: con velocità non divisibili per
  `--data-byte` c'è un piccolo arrotondamento del tempo (es. velocità 7
  con `--data-byte 2` → 8 frame/riga). Usa `--data-byte 1` per il tempo
  esatto.
- L'inviluppo di volume esatto dello strumento non è replicabile: la
  durata è un'approssimazione, non la curva originale.
- Quantizzazione hardware delle frequenze: le ottave gravi possono
  risultare scordate di pochi cent, in modo lievemente diverso tra AY e
  SN76489. È un limite del chip, non della conversione.

---

## 8. Mappa rapida dei file

- `arkos_to_cvbasic.py` — il convertitore.
- `musica.bas` — output con `--data-byte 2` (bilanciato).
- `musica_tempo_esatto.bas` — output con `--data-byte 1` (tempo esatto).

---

## Metadata
- Ultima modifica: 2026-06-06
- Modello: Claude Opus 4.8
