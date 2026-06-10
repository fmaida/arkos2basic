"""Unit tests for note conversion and channel building (cvbasic module)."""

from arkos2basic.arkostracker.cell import Cell
from arkos2basic.cvbasic import (
    build_channel,
    build_drum_channel,
    note_to_cvbasic,
)


def uniform_row_start(height: int, steps: int) -> list[int]:
    """Build a row_start list with the same number of steps per row.

    Args:
        height: number of rows in the pattern.
        steps: steps per row.

    Returns:
        List of length height + 1 with the cumulative step indexes.
    """
    result = [r * steps for r in range(height + 1)]

    return result


class TestNoteToCvbasic:
    """Tests for the MIDI number -> CVBasic note name conversion."""

    def test_natural_note(self) -> None:
        """48 is C in octave 4."""
        assert note_to_cvbasic(48) == "C4"


    def test_sharp_goes_after_octave(self) -> None:
        """58 is A#4: CVBasic wants the sharp after the octave."""
        assert note_to_cvbasic(58) == "A4#"


    def test_octave_clamped_low(self) -> None:
        """Octaves below 2 are clamped to 2."""
        assert note_to_cvbasic(12) == "C2"


    def test_octave_clamped_high(self) -> None:
        """Octaves above 6 are clamped to 6."""
        assert note_to_cvbasic(96) == "C6"


class TestBuildChannel:
    """Tests for the melodic channel expansion."""

    def test_note_without_effect_holds_until_end(self) -> None:
        """No sXX anywhere: the note sounds until the end of the pattern."""
        cells = [Cell(row=0, note=48, instrument=1)]
        row_start = uniform_row_start(4, 2)

        tokens, last = build_channel(cells, 4, row_start, 3.0, False, {})

        assert tokens == ["C4", "S", "S", "S", "S", "S", "S", "S"]
        assert last is None


    def test_explicit_speed_limits_duration(self) -> None:
        """s01 with scale 3.0 gives 3 audible steps."""
        cells = [Cell(row=0, note=48, speed=1, instrument=1)]
        row_start = uniform_row_start(4, 2)

        tokens, last = build_channel(cells, 4, row_start, 3.0, False, {})

        assert tokens == ["C4", "S", "S", "-", "-", "-", "-", "-"]
        assert last == 1


    def test_speed_zero_means_full_hold(self) -> None:
        """s00 is not zero length: the note holds until the next note."""
        cells = [Cell(row=0, note=48, speed=0, instrument=1)]
        row_start = uniform_row_start(4, 2)

        tokens, _ = build_channel(cells, 4, row_start, 3.0, False, {})

        assert tokens == ["C4", "S", "S", "S", "S", "S", "S", "S"]


    def test_note_inherits_previous_effect(self) -> None:
        """A note without sXX inherits the last sXX on the channel."""
        cells = [
            Cell(row=0, note=48, speed=1, instrument=1),
            Cell(row=2, note=50, instrument=1),
        ]
        row_start = uniform_row_start(4, 2)

        tokens, _ = build_channel(cells, 4, row_start, 3.0, False, {})

        assert tokens[4:] == ["D4", "S", "S", "-"]


    def test_initial_effect_carries_from_previous_pattern(self) -> None:
        """initial_effect plays the role of an sXX seen in a past pattern."""
        cells = [Cell(row=0, note=48, instrument=1)]
        row_start = uniform_row_start(4, 2)

        tokens, last = build_channel(
            cells, 4, row_start, 3.0, False, {}, initial_effect=1,
        )

        assert tokens == ["C4", "S", "S", "-", "-", "-", "-", "-"]
        assert last == 1


    def test_next_note_clips_duration(self) -> None:
        """The audible portion never overlaps the next note."""
        cells = [
            Cell(row=0, note=48, speed=9, instrument=1),
            Cell(row=1, note=50, speed=9, instrument=1),
        ]
        row_start = uniform_row_start(2, 2)

        tokens, _ = build_channel(cells, 2, row_start, 3.0, False, {})

        assert tokens == ["C4", "S", "D4", "S"]


    def test_invert_speed(self) -> None:
        """With --invert a high sXX gives a short note."""
        cells = [Cell(row=0, note=48, speed=10, instrument=1)]
        row_start = uniform_row_start(8, 2)

        tokens, _ = build_channel(cells, 8, row_start, 3.0, True, {})

        # base = max(1, 12 - 10) = 2 -> length = 6
        assert tokens[:7] == ["C4", "S", "S", "S", "S", "S", "-"]


    def test_rst_silences_channel(self) -> None:
        """Instrument 0 (RST) suppresses the note."""
        cells = [Cell(row=0, note=48, instrument=0)]
        row_start = uniform_row_start(2, 2)

        tokens, _ = build_channel(cells, 2, row_start, 3.0, False, {})

        assert tokens == ["-", "-", "-", "-"]


    def test_percussion_removed_from_melodic_channel(self) -> None:
        """Notes with a drum instrument stay silent in the melodic channel."""
        cells = [Cell(row=0, note=48, instrument=5)]
        row_start = uniform_row_start(2, 2)

        tokens, _ = build_channel(cells, 2, row_start, 3.0, False, {5: "M1"})

        assert tokens == ["-", "-", "-", "-"]


    def test_speed_only_cell_updates_last_effect(self) -> None:
        """A cell with only an sXX effect updates the returned state."""
        cells = [Cell(row=3, note=-1, speed=4)]
        row_start = uniform_row_start(4, 2)

        tokens, last = build_channel(cells, 4, row_start, 3.0, False, {})

        assert tokens == ["-"] * 8
        assert last == 4


class TestBuildDrumChannel:
    """Tests for the percussion (fourth) channel."""

    def test_drum_hit_repeated_for_drum_length(self) -> None:
        """The drum token is repeated drum_length consecutive steps."""
        cells = [[Cell(row=1, note=48, instrument=5)]]
        row_start = uniform_row_start(4, 2)

        tokens = build_drum_channel(cells, row_start, 4, {5: "M1"}, 2)

        assert tokens == ["-", "-", "M1", "M1", "-", "-", "-", "-"]


    def test_drum_hit_clipped_at_pattern_end(self) -> None:
        """A long hit near the end never writes past the pattern."""
        cells = [[Cell(row=3, note=48, instrument=5)]]
        row_start = uniform_row_start(4, 1)

        tokens = build_drum_channel(cells, row_start, 4, {5: "M3"}, 4)

        assert tokens == ["-", "-", "-", "M3"]


    def test_last_channel_wins_on_same_row(self) -> None:
        """Two drums on the same row: the last channel overwrites."""
        cells = [
            [Cell(row=0, note=48, instrument=5)],
            [Cell(row=0, note=50, instrument=6)],
        ]
        row_start = uniform_row_start(2, 1)

        tokens = build_drum_channel(cells, row_start, 2, {5: "M1", 6: "M2"}, 1)

        assert tokens == ["M2", "-"]
