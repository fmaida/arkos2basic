# Arkos Tracker → CVBasic Converter

Documentation for the `arkos2basic` project: reads a music file
exported from **Arkos Tracker 3** (text format) and produces one or two
music blocks in **CVBasic**, ready for ColecoVision, MSX and Sega SG-1000.

---

## 1. Purpose

Arkos Tracker and CVBasic use two incompatible formats:

| | Arkos Tracker | CVBasic |
|---|---|---|
| Notes | MIDI-style numbers (`note 40`) | literal names (`E3`) |
| Duration | speed track + `forceInstrumentSpeed` effect | count of `S` on a fixed `DATA BYTE` |
| Structure | multiple patterns/tracks | linear sequence of `MUSIC` |
| Chip | AY-3-8910 (PSG) | SN76489 / AY abstracted by CVBasic |

The converter translates mechanically, **ignoring instrument definitions**
(except for percussion detection), and reconstructs two temporal aspects
of the song: playback speed and variable note duration.

---

## 2. Arkos Tracker file structure

The file is text with nested sections (`SECTION` / `ENDSECTION`, with
the number of leading dashes indicating depth). The parts relevant to
conversion are:

- **subsong** → `initialSpeed` (starting speed in frames per row),
  `replayFrequencyHz` (50 Hz), `loopStartPosition` (0-based index of
  the position where the song loops from), and `endPosition` (last
  included position).
- **instruments** → each instrument's cells are inspected only to detect
  the `noise` field: if present and > 0, the instrument is classified
  as percussion (M1/M2/M3).
- **tracks** → each track has an `index` and a list of **cells**.
  Each cell has:
  - `index`: the **row** in the pattern (vertical position);
  - `note`: MIDI-style note number (0 = C-0), absent if the cell
    contains only an effect;
  - `instrument`: 0 = RST (note cut, channel goes silent), > 0 =
    instrument index;
  - optional `forceInstrumentSpeed` effect with `logicalValue`
    (the `sXX` column in the tracker).
- **speedTracks** → speed tracks; each cell has `index` (row) and
  `value` (new speed; **`0` means "no change"**).
- **positions** → playback order: each position points to a
  `patternIndex` and has a `height` (number of rows).
- **patterns** → each pattern points to **3 `trackIndex`** values
  (PSG channels A, B, C) and a `speedTrackIndex`.

---

## 3. Conversion logic

### 3.1 Notes and octaves

```
octave = note // 12
note_index = note % 12   →  C, C#, D, D#, E, F, F#, G, G#, A, A#, B
```

CVBasic places the sharp **after** the octave number, e.g. `A4#`.
With the default `--octaves 0` (effective offset +1), the Arkos note
numbering is raised by one octave. Octaves outside the CVBasic range
(2–6) are clamped to the nearest limit.

### 3.2 Speed (speed track)

CVBasic has **a single `DATA BYTE`** for the whole song, so the tick
cannot change mid-song. The converter resolves this as follows:

1. starts from `initialSpeed`;
2. scanning rows in playback order, updates the current speed when the
   speed track has a non-zero value; speed **propagates** from one
   pattern to the next;
3. each row generates `steps = max(1, round(speed / data_byte))`
   `MUSIC` instructions.

A speed change thus becomes "more (or fewer) steps per row" and remains
faithful even with multiple mid-song changes.

### 3.3 Variable note duration (articulation)

The perceived duration in the tracker comes not from note position (many
passages have one note per row) but from the `forceInstrumentSpeed`
effect (`sXX`), which controls the instrument envelope. Applied mapping:

- `s00` or no effect → **no override**: the note sounds full until
  the next note (held);
- `sNN` with N > 0 → the sounding portion lasts
  `round(N × length_scale)` steps, clipped by the next note
  (no overlap);
- a note without an effect **inherits** the last `sXX` value on that
  channel.

Each step becomes a token: note name on attack, `S` for sustain,
`-` for silence.

**Articulation resolution and clipping.** The sounding portion is
always clipped by the next note on the channel, so the differentiation
between `sXX` values is limited by the gap *measured in steps*. With
`--data-byte 2` and speed 6 a row is only 3 steps: any `sXX ≥ 1` fills
it and s01…s06 all sound identical (and `--length` appears to do
nothing, because the clip happens first). Two remedies:

- **`--length` negative (free)**: compresses the durations inside the
  existing gaps without adding any rows. On a typical song at speed 7
  `--length -2` maps s01…s04 to 1…4 distinct steps even on adjacent
  rows. Notes get shorter overall, quantised to `data_byte`-frame
  steps. Prefer this when ROM space matters (16/32K games).
- **`--data-byte 1`**: doubles the steps per row (double output size,
  DATA BYTE 1 = one step per frame, same musical tempo) for finer
  quantisation. Not possible to go below 1 (the CVBasic player
  advances at most once per frame).

The converter prints how many `sXX` notes were clipped (e.g.
`Articulation: 239 of 382 sXX notes clipped`): tune `--length` (and
`--data-byte` if affordable) until the ratio is low.

### 3.4 RST (note cut)

Cells with `instrument = 0` (the "Empty" instrument) signal an RST:
the channel goes silent from that row. In the melodic channel the note
is suppressed and the corresponding steps remain `-`.

### 3.5 Percussion (fourth channel)

Instruments with at least one cell where `noise > 0` are classified as
percussion. The CVBasic type is assigned based on the average noise
period:

- ≤ 5 → `M2` (snare/hi-hat)
- 6–15 → `M1` (bass drum)
- ≥ 16 → `M3` (low noise)

Notes played with percussion instruments are removed from the melodic
channels and placed in the fourth `MUSIC` channel:

```
MUSIC <voice0>,<voice1>,<voice2>,<drum>
```

### 3.6 Instrument mapping (W/X/Y)

Arkos instruments are mapped **positionally** to the CVBasic instrument
suffixes, regardless of what the instrument actually is in the tracker:

| Arkos instrument | CVBasic suffix |
|---|---|
| 1 | `W` (piano) |
| 2 | `X` (clarinet — the player also raises it one octave) |
| 3 | `Y` (flute) |
| ≥ 4 (melodic) | `W` |

`Z` (bass) is not used because the CVBasic player transposes it two
octaves down. Percussion detection has priority: a noise-based
instrument goes to the fourth MUSIC channel even if its index is 1-3.

Since CVBasic carries the instrument over per channel, the suffix is
emitted only when it changes (e.g. `E3X`), with an explicit suffix on
the first note of each channel of each generated file so the loop file
always starts from a known state. The suffix lives in the same byte as
the note, so it costs no ROM. Disable with `--no-instruments`.

### 3.7 Intro/loop split

If the Arkos file contains `loopStartPosition > 0` and `--stop` was not
requested, the converter generates **two files**:

- `OUTPUT.bas` — intro (positions 0 … loopStart-1), ends with
  `MUSIC STOP`;
- `OUTPUT_loop.bas` — loop section (positions loopStart … endPosition),
  ends with `MUSIC REPEAT`.

---

## 4. Command-line parameters

```
arkos2basic INPUT.txt OUTPUT.bas [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--octaves N` | `0` | octave delta relative to base +1 (e.g. `--octaves 1` → +2 octaves) |
| `--transpose N` | `0` | fine semitone shift (+/-); 12 semitones = 1 octave |
| `--data-byte N` | `2` | frames per `MUSIC` step; lower = more faithful but more rows; `1` = exact timing |
| `--length F` | `0.0` | delta from base 3.0 for note sounding duration (`--length 1` → 4.0) |
| `--drum-length N` | `0` | delta from base 2 steps per percussion hit |
| `--invert` | off | invert the scale: high `sXX` = shorter note |
| `--label NAME` | `musica` | label for the music block |
| `--stop` | off | always end with `MUSIC STOP` (disables intro/loop split) |
| `--no-instruments` | off | do not map Arkos instruments 1-3 to W/X/Y (all piano) |
| `--exclude-channels "N[,M]"` | `""` | source channels to skip (1–3); remaining channels pack left |

At the end of execution the script prints the speeds found in the
tracker, any percussion instruments detected, the number of `sXX`
notes clipped by the next note (see §3.3), and the path(s) of the
generated file(s).

### Effective transpose

`--octaves N` and `--transpose M` are combined into a single shift:

```
effective_transpose = (1 + N) * 12 + M
```

This means `--octaves 1` = `--transpose 12`, `--octaves -1` = `--transpose -12`.

### Examples

```
arkos2basic musica.txt musica.bas                       # balanced default
arkos2basic musica.txt musica.bas --data-byte 1         # exact timing
arkos2basic musica.txt musica.bas --octaves 1           # everything +2 octaves
arkos2basic musica.txt musica.bas --transpose 3         # +3 semitones
arkos2basic musica.txt musica.bas --length -1           # shorter notes
arkos2basic musica.txt musica.bas --stop                # single file, MUSIC STOP
arkos2basic musica.txt musica.bas --exclude-channels 2  # skip source channel 2
```

---

## 5. Using the output in CVBasic

### 5.1 Song without split (MUSIC STOP or simple MUSIC REPEAT)

```basic
    PLAY FULL
    PLAY musica
    DO : WAIT : LOOP WHILE 1

    INCLUDE musica.bas
```

### 5.2 Song with intro + loop (most common case)

The converter produces `musica.bas` (intro, MUSIC STOP) and
`musica_loop.bas` (loop, MUSIC REPEAT). The CVBasic code must detect
the end of the intro and switch to the loop **exactly once**.

**Note**: in CVBasic the `NOT` operator is bitwise, so `NOT 1 = -2`
(non-zero = truthy). Always use explicit `= 0` comparisons instead of
`NOT` on flags or on `MUSIC.PLAYING`.

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

The `loop_on` flag is necessary because `MUSIC.PLAYING` may remain `0`
for several frames after `MUSIC STOP`, and calling `PLAY musica_loop`
multiple times would reset the loop to the first step on every frame.

Use `PLAY FULL` because the song uses multiple voices. With `PLAY SIMPLE`
only the first two voices play, freeing one channel for sound effects.
Data is stored in ROM (does not use RAM) but occupies cartridge space:
watch out if you are close to the bank limit.

---

## 6. Design choices and assumptions

- **`s00` = full hold**, not zero length: this was the cause of notes
  appearing too short and `length_scale` seeming ineffective.
- **Speed propagates** between patterns, with `0 = no change`, as in
  Arkos. The same holds for the inherited `sXX` value (per channel).
  When generating the loop section of a split song, both states are
  first replayed through the intro positions (`state_at_position` in
  `cvbasic.py`), so the loop starts from the correct speed and `sXX`.
- **Chip abstraction**: both Arkos and CVBasic are tuned to A = 440 Hz.
  CVBasic generates the correct periods for SN76489 and AY from the
  note name, so conversion at the name level is chip- and
  AY-clock-independent.
- **Instrument mapping is positional** (§3.6): Arkos 1/2/3 → `W/X/Y`
  by index, ignoring the actual instrument definition (except for the
  noise field, used for percussion detection). `--no-instruments`
  restores the old all-piano behaviour.
- **Direction of `sXX`** (high = longer) inferred by listening;
  invertible with `--invert`.

---

## 7. Known limitations

- **Single `DATA BYTE` per song**: with speeds not divisible by
  `--data-byte` there is a small timing rounding error (e.g. speed 7
  with `--data-byte 2` → 8 frames/row). Use `--data-byte 1` for exact
  timing.
- **Volume envelope**: not replicable; note duration is an approximation,
  not the original curve.
- **Articulation resolution**: `sXX` durations are quantised to steps
  and clipped by the next note; with `--data-byte 2` and notes 1-2 rows
  apart most `sXX` values collapse to the same duration. Use a negative
  `--length` (free) or `--data-byte 1` (~double size) — see §3.3.
- **SN76489 frequency range (ColecoVision)**: the period register is
  10 bits (max 1023), corresponding to about 109 Hz (~A2). Notes below
  G#2 are out of range and the chip produces silence. On MSX
  (AY-3-8910, 12-bit prescaler) this problem does not occur. If low
  notes are silent on ColecoVision, increase `--octaves` by 1.
- **Hardware frequency quantisation**: in lower octaves periods are less
  granular; a note may be slightly out of tune, differently between AY
  and SN76489. This is a chip limitation.
- **Percussion — same-row overlap**: if two channels have a percussion
  note on the same row, the last channel read overwrites the previous
  one in the fourth `MUSIC` slot.

---

## 8. Quick file map

- `src/arkos2basic/cli.py` — typer CLI (Poetry entry point:
  `arkos2basic`).
- `src/arkos2basic/cvbasic.py` — CVBasic source generator
  (`note_to_cvbasic`, `build_channel`, `build_drum_channel`,
  `state_at_position`, `convert`).
- `src/arkos2basic/arkostracker/txtimport.py` — parser for the Arkos
  Tracker text export (V1.0).
- `src/arkos2basic/arkostracker/baseimport.py` — abstract base importer
  (transpose, intro/loop split, output writing).
- `src/arkos2basic/arkostracker/song.py`, `cell.py` — data models.
- `tests/` — pytest suite (run with `poetry run pytest`).
- `examples/music_01.txt` — sample Arkos Tracker export.

---

## Metadata
- Ultima modifica: 2026-06-10
- Modello: claude-fable-5
