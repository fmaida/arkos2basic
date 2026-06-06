# Convertitore Arkos Tracker → CVBasic

Documentazione del progetto `arkos2basic`: legge un file musicale
esportato da **Arkos Tracker 3** (formato testo) e produce uno o due
blocchi di musica in **CVBasic**, pronti per ColecoVision, MSX e
Sega SG-1000.

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
degli strumenti** (salvo il rilevamento delle percussioni), e
ricostruisce due aspetti temporali del brano: la velocità di
riproduzione e la durata variabile delle singole note.

---

## 2. Struttura del file Arkos Tracker

Il file è un testo a sezioni annidate (`SECTION` / `ENDSECTION`, con il
numero di trattini iniziali a indicare la profondità). Le parti che
contano per la conversione sono:

- **subsong** → `initialSpeed` (velocità di partenza, in frame per
  riga), `replayFrequencyHz` (50 Hz), `loopStartPosition` (indice
  della posizione da cui il brano ricomincia) e `endPosition` (ultima
  posizione inclusa).
- **instruments** → le celle di ogni strumento vengono ispezionate
  solo per rilevare il campo `noise`: se presente e > 0, lo strumento
  è classificato come percussione (M1/M2/M3).
- **tracks** → ogni traccia ha un `index` e una lista di **celle**.
  Ogni cella ha:
  - `index`: la **riga** del pattern (posizione verticale);
  - `note`: numero di nota in stile MIDI (0 = C-0), assente se la
    cella contiene solo un effetto;
  - `instrument`: 0 = RST (nota cut, canale in silenzio), > 0 =
    indice strumento;
  - eventuale effetto `forceInstrumentSpeed` con `logicalValue`
    (la colonna `sXX` del tracker).
- **speedTracks** → tracce di velocità; ogni cella ha `index` (riga)
  e `value` (nuova velocità; **`0` significa "nessun cambio"**).
- **positions** → l'ordine di riproduzione: ogni posizione punta a un
  `patternIndex` e ha una `height` (numero di righe).
- **patterns** → ogni pattern punta a **3 `trackIndex`** (i canali PSG
  A, B, C) e a uno `speedTrackIndex`.

---

## 3. Logica di conversione

### 3.1 Note e ottave

```
ottava = note // 12 + offset
indice_nota = note % 12   →  C, C#, D, D#, E, F, F#, G, G#, A, A#, B
```

Il nome CVBasic mette il diesis **dopo** l'ottava, es. `A4#`. Con
`offset 1` (default) la numerazione Arkos viene alzata di un'ottava.
Le ottave fuori dal range CVBasic (2–6) vengono agganciate al limite
più vicino.

### 3.2 Velocità (speed track)

CVBasic ha **un solo `DATA BYTE`** per tutto il brano, quindi non si
può cambiare il tick a metà. Il convertitore risolve così:

1. parte da `initialSpeed`;
2. scorrendo le righe in ordine di riproduzione, aggiorna la velocità
   corrente quando il speed track ha un valore diverso da 0; la
   velocità **si propaga** da un pattern al successivo;
3. ogni riga genera `passi = max(1, round(velocità / data_byte))`
   istruzioni `MUSIC`.

Così un cambio di velocità diventa "più (o meno) passi per riga" e
resta fedele anche con cambi multipli a metà brano.

### 3.3 Durata variabile delle note (articolazione)

La durata percepita nel tracker non viene dalla posizione delle note
(in molti passaggi c'è una nota per riga) ma dall'effetto
`forceInstrumentSpeed` (`sXX`), che regola l'inviluppo dello
strumento. Mappa applicata:

- `s00` o effetto assente → **nessuna forzatura**: la nota suona
  piena fino alla nota successiva (tenuta);
- `sNN` con N > 0 → la parte in suono dura
  `round(N × length_scale)` passi, comunque **tagliata** dalla nota
  successiva (non si sovrappone);
- una nota senza effetto **eredita** l'ultimo valore `sXX` del canale.

Ogni passo diventa un token: nome nota all'attacco, `S` per il
prolungamento, `-` per il silenzio.

### 3.4 RST (note cut)

Le celle con `instrument = 0` (strumento "Empty") indicano un RST:
il canale va in silenzio da quella riga. Nel canale melodico la nota
viene soppressa e i passi corrispondenti restano `-`.

### 3.5 Percussioni (quarto canale)

Gli strumenti con almeno una cella `noise > 0` vengono classificati
come percussioni. Il tipo CVBasic viene assegnato in base al periodo
medio di rumore:

- ≤ 5 → `M2` (snare/hi-hat)
- 6–15 → `M1` (cassa)
- ≥ 16 → `M3` (rumore basso)

Le note suonate con strumenti percussivi vengono rimosse dai canali
melodici e collocate nel quarto canale `MUSIC`:

```
MUSIC <voce0>,<voce1>,<voce2>,<drum>
```

### 3.6 Split intro/loop

Se il file Arkos contiene `loopStartPosition > 0` e non è stato
richiesto `--stop`, il convertitore genera **due file**:

- `OUTPUT.bas` — intro (posizioni 0 … loopStart-1), termina con
  `MUSIC STOP`;
- `OUTPUT_loop.bas` — sezione in loop (posizioni loopStart …
  endPosition), termina con `MUSIC REPEAT`.

---

## 4. Parametri da riga di comando

```
arkos2basic INPUT.txt OUTPUT.bas [opzioni]
```

| Opzione | Default | Significato |
|---|---|---|
| `--octaves N` | `0` | delta di ottave rispetto al base +1 (es. `--octaves 1` → offset 2, `--octaves -1` → offset 0) |
| `--data-byte N` | `2` | frame per passo `MUSIC`; più basso = più fedele ma più righe; `1` = tempo esatto |
| `--length F` | `0.0` | delta rispetto al base 3.0 per la durata in suono delle note (`--length 1` → 4.0) |
| `--drum-length N` | `0` | delta rispetto al base 2 step per colpo percussivo |
| `--invert` | off | inverte la scala: `sXX` alto = nota più corta |
| `--label NOME` | `musica` | etichetta del blocco musicale |
| `--stop` | off | termina sempre con `MUSIC STOP` (disabilita lo split intro/loop) |

A fine esecuzione lo script stampa le velocità trovate nel tracker,
gli eventuali strumenti percussivi rilevati e il percorso dei file
prodotti.

### Esempi

```
arkos2basic musica.txt musica.bas                   # default bilanciato
arkos2basic musica.txt musica.bas --data-byte 1     # tempo esatto
arkos2basic musica.txt musica.bas --octaves 1       # tutto +2 ottave
arkos2basic musica.txt musica.bas --length -1       # note più corte
arkos2basic musica.txt musica.bas --stop            # un solo file, MUSIC STOP
```

---

## 5. Uso dell'output in CVBasic

### 5.1 Brano senza split (MUSIC STOP o MUSIC REPEAT semplice)

```basic
    PLAY FULL
    PLAY musica
    DO : WAIT : LOOP WHILE 1

    INCLUDE musica.bas
```

### 5.2 Brano con intro + loop (caso più comune)

Il convertitore produce `musica.bas` (intro, MUSIC STOP) e
`musica_loop.bas` (loop, MUSIC REPEAT). Il codice CVBasic deve
rilevare la fine dell'intro e passare al loop **una sola volta**.

**Attenzione**: in CVBasic l'operatore `NOT` è bitwise, quindi
`NOT 1 = -2` (non zero = vero). Usare sempre confronti espliciti
`= 0` invece di `NOT` su variabili flag o su `MUSIC.PLAYING`.

```basic
    DIM loop_on
    loop_on = 0
    PLAY FULL
    PLAY musica
    DO
        WAIT
        IF MUSIC.PLAYING = 0 AND loop_on = 0 THEN
            loop_on = 1
            PLAY musica_loop
        END IF
    LOOP WHILE 1

    INCLUDE musica.bas
    INCLUDE musica_loop.bas
```

Il flag `loop_on` è necessario perché `MUSIC.PLAYING` può restare
`0` per più frame dopo `MUSIC STOP`, e chiamare `PLAY musica_loop`
più volte resetterebbe il loop al primo step ad ogni frame.

Usa `PLAY FULL` perché il brano usa più voci. Con `PLAY SIMPLE`
suonano solo le prime due, liberando un canale per gli effetti sonori.
I dati stanno in ROM (non intaccano la RAM) ma occupano spazio
cartuccia: attenzione se sei vicino al limite del banco.

---

## 6. Scelte progettuali e assunzioni

- **`s00` = tenuta piena**, non lunghezza zero: era la causa per cui
  le note risultavano troppo corte e `length_scale` sembrava
  inefficace.
- **Velocità che si propaga** tra pattern, con `0 = nessun cambio`,
  come in Arkos.
- **Astrazione del chip**: sia Arkos sia CVBasic sono tarati su
  La = 440 Hz. CVBasic genera i periodi corretti per SN76489 e AY a
  partire dal nome nota, quindi la conversione a livello di nome è
  indipendente dal chip e dal clock dell'AY.
- **Strumenti ignorati** salvo il rilevamento noise: nessun `W/X/Y/Z`,
  tutte le voci melodiche usano il piano di default.
- **Direzione di `sXX`** (alto = più lungo) dedotta all'ascolto;
  invertibile con `--invert`.

---

## 7. Limiti noti

- **Un solo `DATA BYTE` per brano**: con velocità non divisibili per
  `--data-byte` c'è un piccolo arrotondamento del tempo (es. velocità
  7 con `--data-byte 2` → 8 frame/riga). Usa `--data-byte 1` per il
  tempo esatto.
- **Inviluppo di volume**: non è replicabile; la durata delle note è
  un'approssimazione, non la curva originale.
- **Range frequenze SN76489 (ColecoVision)**: il registro di periodo
  è a 10 bit (max 1023), il che corrisponde a circa 109 Hz (~A2).
  Le note sotto G#2 sono fuori range e il chip le produce in silenzio.
  Su MSX (AY-3-8910, prescaler a 12 bit) il problema non si presenta.
  Se le note basse non si sentono su ColecoVision, aumentare
  `--octaves` di 1.
- **Quantizzazione hardware delle frequenze**: nelle ottave gravi i
  periodi sono meno granulari; la nota può risultare leggermente
  scordata, in modo diverso tra AY e SN76489. È un limite del chip.
- **Percussioni — sovrapposizione su stessa riga**: se due canali
  hanno una nota percussiva sulla stessa riga, l'ultimo canale letto
  sovrascrive il precedente nel quarto slot `MUSIC`.

---

## 8. Mappa rapida dei file

- `src/arkos2basic/arkos2basic.py` — il convertitore (entry point
  Poetry: `arkos2basic`).
- `musica.bas` — output intro con `--data-byte 2` (bilanciato).
- `musica_loop.bas` — output loop con `--data-byte 2`.
- `musica_tempo_esatto.bas` — output con `--data-byte 1`.

---

## Metadata
- Ultima modifica: 2026-06-06
- Modello: claude-sonnet-4-6
