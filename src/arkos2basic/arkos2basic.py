"""Convertitore da Arkos Tracker text format (V1.0) a musica CVBasic.

Legge un file .txt esportato da Arkos Tracker, ignora le definizioni
degli strumenti e produce un file BASIC con un blocco DATA BYTE / MUSIC
pronto per essere riprodotto da CVBasic con PLAY FULL.

Vengono ricostruiti due aspetti temporali del tracker:
- la velocita' di riproduzione (speed track): ogni riga dura un numero
  di passi proporzionale alla velocita' corrente, che si propaga da un
  pattern all'altro; un valore 0 nel speed track significa "nessun
  cambio";
- la durata variabile delle note (effetto forceInstrumentSpeed): un
  valore alto allunga la parte in suono, un valore 0 (s00) significa
  nessuna forzatura e rende la nota tenuta fino alla successiva.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated

import typer


# Nomi delle 12 note cromatiche. In CVBasic il diesis va DOPO l'ottava
# (es. "A4#"), quindi qui memorizzo solo lettera + flag di diesis.
NOTE_NAMES: list[tuple[str, bool]] = [
    ("C", False),
    ("C", True),
    ("D", False),
    ("D", True),
    ("E", False),
    ("F", False),
    ("F", True),
    ("G", False),
    ("G", True),
    ("A", False),
    ("A", True),
    ("B", False),
]

MIN_OCTAVE: int = 2
MAX_OCTAVE: int = 6


@dataclass
class Cell:
    """Una cella del tracker.

    Attributes:
        row: indice di riga nel pattern (posizione verticale).
        note: numero di nota in stile MIDI, oppure -1 se assente.
        speed: valore forceInstrumentSpeed della cella, o None.
        instrument: indice dello strumento (-1 se non specificato).
            Lo strumento 0 ("Empty") indica un RST: il canale va
            in silenzio a quella riga.
    """

    row: int
    note: int
    speed: int | None = None
    instrument: int = -1


@dataclass
class Song:
    """Rappresentazione intermedia della canzone estratta dal file.

    Attributes:
        positions: ordine di riproduzione come (patternIndex, height).
        patterns: per ogni patternIndex la lista dei 3 trackIndex.
        pattern_speed: per ogni patternIndex l'indice del speed track.
        tracks: per ogni trackIndex la lista delle sue celle.
        speed_tracks: per ogni speed track la mappa riga -> velocita'.
        initial_speed: velocita' iniziale prima di ogni cambio.
    """

    positions: list[tuple[int, int]] = field(default_factory=list)
    patterns: dict[int, list[int]] = field(default_factory=dict)
    pattern_speed: dict[int, int] = field(default_factory=dict)
    tracks: dict[int, list[Cell]] = field(default_factory=dict)
    speed_tracks: dict[int, dict[int, int]] = field(default_factory=dict)
    initial_speed: int = 6


def parse_arkos(text: str) -> Song:
    """Analizza il testo Arkos Tracker e ne estrae la struttura utile.

    Args:
        text: contenuto completo del file Arkos Tracker.

    Returns:
        Un oggetto Song con positions, patterns, tracks, velocita'.
    """
    song = Song()
    lines = text.replace("\r\n", "\n").split("\n")

    stack: list[str] = []
    track_index: int | None = None
    cell: Cell | None = None
    in_effect = False
    in_track_indexes = False
    in_speed_index = False
    pattern_tracks: list[int] = []
    pattern_speed_index: int | None = None
    pattern_count = 0
    pos_pattern: int | None = None
    pos_height: int | None = None
    st_index: int | None = None
    st_row: int | None = None

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        begin = re.match(r"^(-*)SECTION\s+(\w+)", line)
        end = re.match(r"^(-*)ENDSECTION\s+(\w+)", line)

        if begin:
            name = begin.group(2)
            stack.append(name)

            if name == "track":
                track_index = None
            elif name == "cell" and "track" in stack and "speedTrack" not in stack:
                cell = Cell(row=0, note=-1)
            elif name == "cell" and "speedTrack" in stack:
                st_row = None
            elif name == "effect":
                in_effect = True
            elif name == "trackIndexes":
                in_track_indexes = True
            elif name == "speedTrackIndex":
                in_speed_index = True
            elif name == "speedTrack":
                st_index = None
            elif name == "pattern":
                pattern_tracks = []
                pattern_speed_index = None
            elif name == "position":
                pos_pattern = None
                pos_height = None
            continue

        if end:
            name = end.group(2)

            if name == "cell" and "speedTrack" in stack:
                st_row = None
            elif name == "cell" and cell is not None and "track" in stack:
                keep = cell.note >= 0 or cell.speed is not None
                if keep and track_index is not None:
                    song.tracks.setdefault(track_index, []).append(cell)
                cell = None
            elif name == "effect":
                in_effect = False
            elif name == "trackIndexes":
                in_track_indexes = False
            elif name == "speedTrackIndex":
                in_speed_index = False
            elif name == "pattern":
                song.patterns[pattern_count] = pattern_tracks
                if pattern_speed_index is not None:
                    song.pattern_speed[pattern_count] = pattern_speed_index
                pattern_count += 1
            elif name == "position":
                if pos_pattern is not None and pos_height is not None:
                    song.positions.append((pos_pattern, pos_height))

            if stack:
                stack.pop()
            continue

        parts = line.split(None, 1)
        key = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        top = stack[-1] if stack else ""

        if "speedTrack" in stack and top == "speedTrack" and key == "index":
            st_index = int(value)
            song.speed_tracks.setdefault(st_index, {})
        elif "speedTrack" in stack and top == "cell" and key == "index":
            st_row = int(value)
        elif "speedTrack" in stack and top == "cell" and key == "value":
            if st_index is not None and st_row is not None:
                song.speed_tracks[st_index][st_row] = int(value)
        elif top == "track" and key == "index":
            track_index = int(value)
            song.tracks.setdefault(track_index, [])
        elif top == "cell" and cell is not None and key == "index":
            cell.row = int(value)
        elif top == "cell" and cell is not None and key == "note":
            cell.note = int(value)
        elif top == "cell" and cell is not None and key == "instrument":
            cell.instrument = int(value)
        elif in_effect and cell is not None and key == "logicalValue":
            cell.speed = int(value)
        elif in_speed_index and key == "trackIndex":
            pattern_speed_index = int(value)
        elif in_track_indexes and key == "trackIndex":
            pattern_tracks.append(int(value))
        elif top == "position" and key == "patternIndex":
            pos_pattern = int(value)
        elif top == "position" and key == "height":
            pos_height = int(value)
        elif top == "subsong" and key == "initialSpeed":
            song.initial_speed = int(value)

    return song


def note_to_cvbasic(note: int, octave_offset: int) -> str:
    """Converte un numero di nota Arkos nel nome nota CVBasic.

    Args:
        note: numero di nota in stile MIDI (0 = C-0).
        octave_offset: ottave da aggiungere per rientrare nel range 2-6.

    Returns:
        Il nome della nota in formato CVBasic, es. "A4#".
    """
    letter, sharp = NOTE_NAMES[note % 12]
    octave = note // 12 + octave_offset

    if octave < MIN_OCTAVE:
        octave = MIN_OCTAVE
    elif octave > MAX_OCTAVE:
        octave = MAX_OCTAVE

    suffix = "#" if sharp else ""

    return f"{letter}{octave}{suffix}"


def build_channel(
    cells: list[Cell],
    height: int,
    row_start: list[int],
    octave_offset: int,
    length_scale: float,
    invert_speed: bool,
) -> list[str]:
    """Espande un canale in token CVBasic seguendo il layout dei passi.

    Args:
        cells: celle del canale (note ed eventuali soli effetti speed).
        height: numero di righe del pattern.
        row_start: per ogni riga il passo iniziale (lungo height + 1).
        octave_offset: ottave da aggiungere in conversione.
        length_scale: fattore che allunga la parte in suono delle note.
        invert_speed: se True, forceInstrumentSpeed alto = nota piu' corta.

    Returns:
        Lista di token CVBasic lunga row_start[height].
    """
    total = row_start[height]
    tokens: list[str] = ["-"] * total

    note_cells = [c for c in cells if c.note >= 0 and c.row < height]
    speed_at_row = {
        c.row: c.speed for c in cells if c.speed is not None and c.row < height
    }

    for i, current in enumerate(note_cells):
        last_speed: int | None = None
        for r in range(current.row + 1):
            if r in speed_at_row:
                last_speed = speed_at_row[r]

        effective = current.speed if current.speed is not None else last_speed

        next_row = note_cells[i + 1].row if i + 1 < len(note_cells) else height
        start = row_start[current.row]
        gap = row_start[next_row] - start

        if effective is None or effective == 0:
            audible = gap
        else:
            base = effective
            if invert_speed:
                base = max(1, 12 - effective)
            length = max(1, round(base * length_scale))
            audible = min(length, gap)

        if current.instrument != 0:
            tokens[start] = note_to_cvbasic(current.note, octave_offset)
            for k in range(1, audible):
                tokens[start + k] = "S"

    return tokens


def convert(
    song: Song,
    octave_offset: int,
    label: str,
    data_byte: int,
    length_scale: float,
    invert_speed: bool,
    stop: bool = False,
) -> tuple[str, set[int]]:
    """Genera il sorgente CVBasic completo della musica.

    Args:
        song: struttura della canzone gia' analizzata.
        octave_offset: ottave da aggiungere per il range CVBasic.
        label: etichetta da assegnare al blocco musicale.
        data_byte: frame per passo MUSIC (il valore DATA BYTE).
        length_scale: fattore che allunga la parte in suono.
        invert_speed: se True, forceInstrumentSpeed alto = nota piu' corta.
        stop: se True, termina con MUSIC STOP; altrimenti con MUSIC REPEAT.

    Returns:
        Una tupla (sorgente BASIC, insieme delle velocita' incontrate).
    """
    out: list[str] = []
    out.append(f"{label}:")
    out.append(
        f"\tDATA BYTE {data_byte}\t' frame per passo "
        f"(passi/riga = velocita' tracker / {data_byte})"
    )

    current_speed = song.initial_speed
    speeds_seen: set[int] = set()

    for pattern_index, height in song.positions:
        track = song.speed_tracks.get(song.pattern_speed.get(pattern_index, -1), {})

        steps_per_row: list[int] = []
        for r in range(height):
            if r in track and track[r] != 0:
                current_speed = track[r]
            speeds_seen.add(current_speed)
            steps_per_row.append(max(1, round(current_speed / data_byte)))

        row_start = [0] * (height + 1)
        for r in range(height):
            row_start[r + 1] = row_start[r] + steps_per_row[r]
        total = row_start[height]

        track_ids = song.patterns.get(pattern_index, [])
        channels: list[list[str]] = []
        for tid in track_ids:
            channels.append(
                build_channel(
                    song.tracks.get(tid, []), height, row_start,
                    octave_offset, length_scale, invert_speed,
                )
            )
        while len(channels) < 3:
            channels.append(["-"] * total)

        out.append(
            f"\t' --- pattern {pattern_index} ({height} righe, "
            f"velocita' {steps_per_row and current_speed}) ---"
        )
        for s in range(total):
            out.append(
                f"\tMUSIC {channels[0][s]},{channels[1][s]},{channels[2][s]}"
            )

    ending = "STOP" if stop else "REPEAT"
    out.append(f"\tMUSIC {ending}")

    return "\n".join(out) + "\n", speeds_seen


app = typer.Typer(help="Converte un file Arkos Tracker (.txt) in musica CVBasic.")


@app.command()
def main(
    input_file: Annotated[
        Path,
        typer.Argument(help="File Arkos Tracker di ingresso"),
    ],
    output_file: Annotated[
        Path,
        typer.Argument(help="File .bas di uscita"),
    ],
    octaves: Annotated[
        int,
        typer.Option(
            help="Delta di ottave rispetto al base +1 (es. --octaves 1 → +2, "
                 "--octaves -1 → 0)"
        ),
    ] = 0,
    data_byte: Annotated[
        int,
        typer.Option(help="Frame per passo MUSIC: più basso = più fedele "
                          "ma più righe (1 = tempo esatto)"),
    ] = 2,
    length_scale: Annotated[
        float,
        typer.Option(help="Allunga la durata in suono delle note (1.0 = base)"),
    ] = 3.0,
    invert: Annotated[
        bool,
        typer.Option(help="Inverte la scala: forceInstrumentSpeed alto = "
                          "nota più corta"),
    ] = False,
    label: Annotated[
        str,
        typer.Option(help="Etichetta del blocco musicale nel sorgente"),
    ] = "musica",
    stop: Annotated[
        bool,
        typer.Option("--stop", help="Termina con MUSIC STOP anziché MUSIC REPEAT"),
    ] = False,
) -> None:
    """Punto di ingresso da riga di comando."""
    if data_byte < 1:
        typer.echo("Errore: --data-byte deve essere almeno 1", err=True)
        raise typer.Exit(1)

    with open(input_file, encoding="utf-8") as handle:
        text = handle.read()

    song = parse_arkos(text)
    source, speeds = convert(
        song, 1 + octaves, label, data_byte, length_scale, invert, stop,
    )

    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write(source)

    music_lines = source.count("\tMUSIC ")
    print(f"Convertito: {len(song.positions)} pattern.")
    print(f"Velocita' incontrate (frame/riga nel tracker): {sorted(speeds)}")
    print(f"DATA BYTE: {data_byte}  ->  righe MUSIC: {music_lines}")
    print(f"Output scritto in: {output_file}")


if __name__ == "__main__":
    app()
