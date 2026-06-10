"""CVBasic music source generator.

Contains all functions needed to emit a CVBasic DATA BYTE / MUSIC block
from the parsed song structure (Cell, Song).
"""

from operator import attrgetter

from arkos2basic.arkostracker.cell import Cell
from arkos2basic.arkostracker.song import Song


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

    suffix = ""
    if sharp:
        suffix = "#"

    return f"{letter}{octave}{suffix}"


def speed_track_for(song: Song, pattern_index: int) -> dict[int, int]:
    """Return the row -> speed mapping of the pattern's speed track.

    Args:
        song: the parsed song structure.
        pattern_index: index of the pattern to look up.

    Returns:
        The row -> speed dict, or an empty dict if the pattern has no
        speed track.
    """
    track_index = song.pattern_speed.get(pattern_index, -1)

    return song.speed_tracks.get(track_index, {})


def state_at_position(
    song: Song,
    pos_start: int,
) -> tuple[int, dict[int, int | None]]:
    """Replay the song state up to (excluding) the given position.

    Both the tracker speed and the forceInstrumentSpeed (sXX) effects
    propagate across patterns, so a section converted on its own (e.g.
    the loop after an intro) must start from the state reached at the
    end of the previous section, not from the song defaults.

    Args:
        song: the parsed song structure.
        pos_start: index of the first position the caller will convert.

    Returns:
        A tuple (current_speed, last_effects) where last_effects maps
        each channel slot (0-based) to the last sXX value seen on it,
        or None if the channel never had one.
    """
    current_speed = song.initial_speed
    last_effects: dict[int, int | None] = {}

    for pattern_index, height in song.positions[:pos_start]:
        track = speed_track_for(song, pattern_index)
        for row in range(height):
            value = track.get(row, 0)
            if value != 0:
                current_speed = value

        track_ids = song.patterns.get(pattern_index, [])
        for slot, track_id in enumerate(track_ids):
            cells = song.tracks.get(track_id, [])
            speed_cells = [
                c for c in cells if c.speed is not None and c.row < height
            ]
            if speed_cells:
                speed_cells.sort(key=attrgetter("row"))
                last_effects[slot] = speed_cells[-1].speed

    return current_speed, last_effects


def build_channel(
    cells: list[Cell],
    height: int,
    row_start: list[int],
    length_scale: float,
    invert_speed: bool,
    drum_instruments: dict[int, str],
    transpose: int = 0,
    initial_effect: int | None = None,
) -> tuple[list[str], int | None]:
    """Expand a channel into CVBasic tokens following the step layout.

    Notes played with instrument 0 (RST) or with a percussion instrument
    are omitted from the melodic channel (left as silence "-"); percussion
    notes are collected separately by build_drum_channel.

    A note without a forceInstrumentSpeed effect inherits the last sXX
    value seen on the channel, including values inherited from previous
    patterns via initial_effect.

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
        initial_effect: last sXX value inherited from previous patterns,
            or None if the channel never had one.

    Returns:
        A tuple (tokens, last_effect): the CVBasic tokens of length
        row_start[height] and the last sXX value on the channel, to be
        carried over into the next pattern.
    """
    total = row_start[height]
    tokens: list[str] = ["-"] * total

    in_range = [c for c in cells if c.row < height]
    note_cells = sorted(
        (c for c in in_range if c.note >= 0), key=attrgetter("row")
    )
    speed_events = sorted(
        (c for c in in_range if c.speed is not None), key=attrgetter("row")
    )

    last_effect = initial_effect
    event_pos = 0

    for i, current in enumerate(note_cells):
        while (
            event_pos < len(speed_events)
            and speed_events[event_pos].row <= current.row
        ):
            last_effect = speed_events[event_pos].speed
            event_pos += 1

        if current.speed is not None:
            effective = current.speed
        else:
            effective = last_effect

        if i + 1 < len(note_cells):
            next_row = note_cells[i + 1].row
        else:
            next_row = height
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

        is_silent = (
            current.instrument == 0 or current.instrument in drum_instruments
        )
        if not is_silent:
            tokens[start] = note_to_cvbasic(current.note + transpose)
            for k in range(1, audible):
                tokens[start + k] = "S"

    while event_pos < len(speed_events):
        last_effect = speed_events[event_pos].speed
        event_pos += 1

    return tokens, last_effect


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

    When pos_start > 0 (e.g. converting the loop section of a split
    song), the speed and the per-channel sXX state are first replayed
    through the skipped positions, so the section starts from the same
    state it would have during normal playback.

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
    excluded: set[int] = set()
    if exclude_channels is not None:
        excluded = exclude_channels

    end = pos_end
    if end is None:
        end = song.playback_end
    positions_to_play = song.positions[pos_start:end]

    out: list[str] = []
    out.append(f"{label}:")
    out.append(
        f"\tDATA BYTE {data_byte}"
        f"\t' frames per step (steps/row = tracker speed / {data_byte})"
    )

    current_speed, last_effects = state_at_position(song, pos_start)
    speeds_seen: set[int] = set()
    has_drums = bool(song.drum_instruments)

    for pattern_index, height in positions_to_play:
        track = speed_track_for(song, pattern_index)

        steps_per_row: list[int] = []
        for row in range(height):
            value = track.get(row, 0)
            if value != 0:
                current_speed = value
            speeds_seen.add(current_speed)
            steps_per_row.append(max(1, round(current_speed / data_byte)))

        row_start = [0] * (height + 1)
        for row in range(height):
            row_start[row + 1] = row_start[row] + steps_per_row[row]
        total = row_start[height]

        track_ids = song.patterns.get(pattern_index, [])
        all_cells = [song.tracks.get(tid, []) for tid in track_ids]

        # Filter excluded channels (1-based); remaining ones pack left,
        # empty right-hand slots stay '-'. The original slot index is
        # kept to carry the per-channel sXX state across patterns.
        kept = [
            (slot, cells) for slot, cells in enumerate(all_cells)
            if (slot + 1) not in excluded
        ]
        channels_cells = [cells for _, cells in kept]

        channels: list[list[str]] = []
        for slot, cells in kept:
            tokens, last_effects[slot] = build_channel(
                cells, height, row_start,
                length_scale, invert_speed,
                song.drum_instruments, transpose,
                initial_effect=last_effects.get(slot),
            )
            channels.append(tokens)
        while len(channels) < 3:
            channels.append(["-"] * total)

        if has_drums:
            drums = build_drum_channel(
                channels_cells, row_start, height,
                song.drum_instruments, drum_length,
            )

        out.append(
            f"\t' --- pattern {pattern_index} ({height} rows, "
            f"speed {current_speed}) ---"
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

    ending = "REPEAT"
    if stop:
        ending = "STOP"
    out.append(f"\tMUSIC {ending}")

    return "\n".join(out) + "\n", speeds_seen
