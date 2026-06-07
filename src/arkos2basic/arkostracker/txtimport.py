"""Importer for the Arkos Tracker text export format (V1.0)."""

import re

from arkos2basic.arkostracker.baseimport import BaseImport
from arkos2basic.arkostracker.cell import Cell
from arkos2basic.arkostracker.song import Song


class TXTImport(BaseImport):
    """Importer for the Arkos Tracker plain-text export (V1.0).

    Handles only what is specific to the TXT format: reading the
    SECTION/ENDSECTION tree and mapping it to a Song. Split logic,
    transpose and CVBasic output are inherited from BaseImport.
    """

    def parse(self) -> Song:
        """Read self.input_file and parse the Arkos Tracker text.

        Returns:
            A Song object with positions, patterns, tracks, and speeds.
        """
        text = self.input_file.read_text(encoding="utf-8")
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

        inst_index: int = 0
        in_inst_cells: bool = False
        inst_noise_values: list[int] = []
        inst_cell_noise: int = 0

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
                elif (name == "cells" and "instrument" in stack
                        and "track" not in stack):
                    in_inst_cells = True
                    inst_noise_values = []
                elif name == "cell" and in_inst_cells:
                    inst_cell_noise = 0
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
                elif name == "cell" and in_inst_cells:
                    inst_noise_values.append(inst_cell_noise)
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
                elif (name == "cells" and "instrument" in stack
                        and "track" not in stack):
                    in_inst_cells = False
                elif name == "instrument" and "instruments" in stack:
                    noise_only = [v for v in inst_noise_values if v > 0]
                    if noise_only:
                        avg = sum(noise_only) / len(noise_only)
                        song.drum_instruments[inst_index] = (
                            self._noise_to_drum_type(avg)
                        )
                    inst_index += 1

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
            elif top == "subsong" and key == "loopStartPosition":
                song.loop_start_position = int(value)
            elif top == "subsong" and key == "endPosition":
                song.end_position = int(value)
            elif in_inst_cells and top == "cell" and key == "noise":
                inst_cell_noise = int(value)

        return song


    def transpose(self, notes: int) -> None:
        """Set the semitone shift for all melodic notes on export.

        Args:
            notes: total semitones to add (positive = up, negative = down;
                12 = one octave up).
        """
        super().transpose(notes)


    def _noise_to_drum_type(self, avg_noise: float) -> str:
        """Map the average noise period of an instrument to a CVBasic drum type.

        The AY-3-8910 noise period ranges from 1 (high frequency) to 31
        (low frequency). The mapping is approximate:
        - 1-5   -> M2 (tap, snare / hi-hat)
        - 6-15  -> M1 (strong, bass drum)
        - 16+   -> M3 (roll, low noise)

        Args:
            avg_noise: average of the non-zero noise periods of the instrument.

        Returns:
            String "M1", "M2" or "M3" for use as the fourth MUSIC argument.
        """
        if avg_noise <= 5:
            return "M2"
        elif avg_noise <= 15:
            return "M1"

        return "M3"
