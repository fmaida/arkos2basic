"""CVBasic music source generator.

Contains all functions needed to emit a CVBasic DATA BYTE / MUSIC block
from the parsed song structure (Cell, Song).
"""

from arkos2basic.arkostracker.cell import Cell  # noqa: F401
from arkos2basic.arkostracker.song import Song  # noqa: F401


# CVBasic places the sharp AFTER the octave number (e.g. "A4#"),
# so each entry stores just the letter and a sharp flag.
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


def note_to_cvbasic(note: int) -> str:
    """Convert a MIDI note number to a CVBasic note name.

    The note number must already include any transposition (semitone
    shift + octave offset) before calling this function. The octave is
    clamped to the 2-6 range if out of bounds.

    Args:
        note: MIDI-style note number (0 = C-0), already transposed.

    Returns:
        The note name in CVBasic format, e.g. "A4#".
    """
    letter, sharp = NOTE_NAMES[note % 12]
    octave = note // 12

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
    length_scale: float,
    invert_speed: bool,
    drum_instruments: dict[int, str],
    transpose: int = 0,
) -> list[str]:
    """Expand a channel into CVBasic tokens following the step layout.

    Notes played with instrument 0 (RST) or with a percussion instrument
    are omitted from the melodic channel (left as silence "-"); percussion
    notes are collected separately by build_drum_channel.

    Args:
        cells: channel cells (notes and speed-only effects).
        height: number of rows in the pattern.
        row_start: starting step index for each row (length height + 1).
        length_scale: factor that lengthens the sounding portion of notes.
        invert_speed: if True, high forceInstrumentSpeed = shorter note.
        drum_instruments: map instrument_idx -> CVBasic type; notes with
            these instruments are silenced in the melodic channel.
        transpose: total semitones to add to the MIDI note number
            (includes octave shift and fine semitone adjustment).

    Returns:
        List of CVBasic tokens of length row_start[height].
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

        is_silent = current.instrument == 0 or current.instrument in drum_instruments
        if not is_silent:
            tokens[start] = note_to_cvbasic(current.note + transpose)
            for k in range(1, audible):
                tokens[start + k] = "S"

    return tokens


def build_drum_channel(
    channels_cells: list[list[Cell]],
    row_start: list[int],
    height: int,
    drum_instruments: dict[int, str],
    drum_length: int = 1,
) -> list[str]:
    """Build the percussion track (fourth MUSIC channel).

    Scans all melodic channels of the pattern and places the percussion
    type token at the step corresponding to the note's row, repeating it
    for drum_length consecutive steps to make the hit more audible. If
    more than one channel has a percussion note on the same row, the last
    channel in the list overwrites the previous ones.

    Args:
        channels_cells: cells from each melodic channel of the pattern.
        row_start: starting step index for each row.
        height: number of rows in the pattern.
        drum_instruments: map instrument_idx -> CVBasic type (M1/M2/M3).
        drum_length: number of consecutive steps per percussion hit.

    Returns:
        List of tokens for the fourth channel, of length row_start[height].
    """
    total = row_start[height]
    tokens: list[str] = ["-"] * total

    for cells in channels_cells:
        drum_cells = [
            c for c in cells
            if c.instrument in drum_instruments and c.row < height
        ]
        for cell in drum_cells:
            drum_type = drum_instruments[cell.instrument]
            start = row_start[cell.row]
            for k in range(drum_length):
                if start + k < total:
                    tokens[start + k] = drum_type

    return tokens


def convert(
    song: Song,
    label: str,
    data_byte: int,
    length_scale: float,
    invert_speed: bool,
    stop: bool = False,
    drum_length: int = 1,
    pos_start: int = 0,
    pos_end: int | None = None,
    exclude_channels: set[int] | None = None,
    transpose: int = 0,
) -> tuple[str, set[int]]:
    """Generate the complete CVBasic music source.

    Args:
        song: the parsed song structure.
        label: label to assign to the music block.
        data_byte: frames per MUSIC step (the DATA BYTE value).
        length_scale: factor that lengthens the sounding portion.
        invert_speed: if True, high forceInstrumentSpeed = shorter note.
        stop: if True, end with MUSIC STOP; otherwise with MUSIC REPEAT.
        drum_length: consecutive steps per percussion hit.
        pos_start: index of the first position to include.
        pos_end: exclusive index of the last position; None uses
            end_position of the song (or the full list).
        exclude_channels: set of 1-based source channel indices to exclude
            (1, 2, or 3). Remaining channels are packed left; empty
            right-hand slots become '-'.
        transpose: total semitones to add to all melodic notes.

    Returns:
        A tuple (BASIC source string, set of speeds encountered).
    """
    excluded: set[int] = exclude_channels if exclude_channels is not None else set()

    song_end = song.end_position + 1 if song.end_position >= 0 else len(song.positions)
    end = pos_end if pos_end is not None else song_end
    positions_to_play = song.positions[pos_start:end]

    out: list[str] = []
    out.append(f"{label}:")
    out.append(
        f"\tDATA BYTE {data_byte}"
        f"\t' frames per step (steps/row = tracker speed / {data_byte})"
    )

    current_speed = song.initial_speed
    speeds_seen: set[int] = set()

    for pattern_index, height in positions_to_play:
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
        all_cells = [song.tracks.get(tid, []) for tid in track_ids]

        # Filter excluded channels (1-based); remaining ones pack left,
        # empty right-hand slots stay '-'.
        channels_cells = [
            cells for i, cells in enumerate(all_cells)
            if (i + 1) not in excluded
        ]

        channels: list[list[str]] = []
        for cells in channels_cells:
            channels.append(
                build_channel(
                    cells, height, row_start,
                    length_scale, invert_speed,
                    song.drum_instruments, transpose,
                )
            )
        while len(channels) < 3:
            channels.append(["-"] * total)

        has_drums = bool(song.drum_instruments)
        if has_drums:
            drums = build_drum_channel(
                channels_cells, row_start, height,
                song.drum_instruments, drum_length,
            )

        out.append(
            f"\t' --- pattern {pattern_index} ({height} rows, "
            f"speed {steps_per_row and current_speed}) ---"
        )
        for s in range(total):
            if has_drums:
                out.append(
                    f"\tMUSIC {channels[0][s]},{channels[1][s]},"
                    f"{channels[2][s]},{drums[s]}"
                )
            else:
                out.append(
                    f"\tMUSIC {channels[0][s]},{channels[1][s]},{channels[2][s]}"
                )

    ending = "STOP" if stop else "REPEAT"
    out.append(f"\tMUSIC {ending}")

    return "\n".join(out) + "\n", speeds_seen
