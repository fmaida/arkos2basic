"""Data model for the parsed song extracted from an Arkos Tracker file."""

from dataclasses import dataclass, field

from arkos2basic.arkostracker.cell import Cell


@dataclass
class Song:
    """Intermediate representation of the song extracted from the file.

    Attributes:
        positions: playback order as (patternIndex, height) tuples.
        patterns: for each patternIndex the list of 3 trackIndexes.
        pattern_speed: for each patternIndex the speed track index.
        tracks: for each trackIndex the list of its cells.
        speed_tracks: for each speed track the row -> speed mapping.
        initial_speed: starting speed before any speed-track change.
        drum_instruments: map instrument_idx -> CVBasic type (M1/M2/M3)
            for instruments that use the noise generator.
        loop_start_position: 0-based index of the position from which
            the song loops; 0 means loop from the beginning.
        end_position: 0-based index of the last position to play
            (inclusive); -1 means use all positions.
    """

    positions: list[tuple[int, int]] = field(default_factory=list)
    patterns: dict[int, list[int]] = field(default_factory=dict)
    pattern_speed: dict[int, int] = field(default_factory=dict)
    tracks: dict[int, list[Cell]] = field(default_factory=dict)
    speed_tracks: dict[int, dict[int, int]] = field(default_factory=dict)
    initial_speed: int = 6
    drum_instruments: dict[int, str] = field(default_factory=dict)
    loop_start_position: int = 0
    end_position: int = -1


    @property
    def playback_end(self) -> int:
        """Exclusive index of the last position to play.

        Returns:
            end_position + 1 if set, otherwise the full positions length.
        """
        if self.end_position >= 0:
            return self.end_position + 1

        return len(self.positions)
