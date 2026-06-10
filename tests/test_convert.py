"""Tests for the full song conversion (convert and state_at_position)."""

import logging

import pytest

from arkos2basic.arkostracker.cell import Cell
from arkos2basic.arkostracker.song import Song
from arkos2basic.cvbasic import convert, state_at_position


def make_split_song() -> Song:
    """Build a two-position song with state changes in the intro.

    Pattern 0 (intro) raises the speed from 6 to 4 via its speed track
    and plays a note with s02 on channel 1; pattern 1 (loop) has a note
    without any effect, which must inherit both states.

    Returns:
        The synthetic Song.
    """
    song = Song()
    song.initial_speed = 6
    song.positions = [(0, 4), (1, 4)]
    song.patterns = {0: [0, 1, 2], 1: [3, 4, 5]}
    song.pattern_speed = {0: 0}
    song.speed_tracks = {0: {1: 4}}
    song.tracks = {
        0: [Cell(row=0, note=48, speed=2, instrument=1)],
        1: [],
        2: [],
        3: [Cell(row=0, note=50, instrument=1)],
        4: [],
        5: [],
    }
    song.loop_start_position = 1
    song.end_position = 1

    return song


def music_lines(source: str) -> list[str]:
    """Extract the MUSIC note lines from a generated source.

    Args:
        source: the generated CVBasic source.

    Returns:
        The stripped MUSIC lines, excluding MUSIC STOP/REPEAT.
    """
    lines = [
        line.strip() for line in source.splitlines()
        if line.strip().startswith("MUSIC ")
    ]
    result = [
        line for line in lines
        if line not in ("MUSIC STOP", "MUSIC REPEAT")
    ]

    return result


class TestStateAtPosition:
    """Tests for the intro state replay used by the loop section."""

    def test_initial_state(self) -> None:
        """At position 0 the state is the song default."""
        song = make_split_song()

        speed, effects = state_at_position(song, 0)

        assert speed == 6
        assert effects == {}


    def test_state_after_intro(self) -> None:
        """The intro changes speed to 4 and leaves s02 on channel 1."""
        song = make_split_song()

        speed, effects = state_at_position(song, 1)

        assert speed == 4
        assert effects == {0: 2}


class TestConvert:
    """Tests for the CVBasic source generation."""

    def test_steps_per_row_follow_speed(self) -> None:
        """Speed 6 with data_byte 2 gives 3 steps per row."""
        song = make_split_song()

        source, speeds = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, pos_end=1,
        )

        # Pattern 0: row 0 at speed 6 (3 steps), rows 1-3 at speed 4
        # (2 steps each) -> 9 MUSIC lines.
        assert len(music_lines(source)) == 9
        assert speeds == {6, 4}


    def test_loop_section_starts_with_propagated_speed(self) -> None:
        """The loop section uses the speed reached in the intro (4, not 6)."""
        song = make_split_song()

        source, speeds = convert(
            song, label="m_loop", data_byte=2, length_scale=3.0,
            invert_speed=False, pos_start=1,
        )

        # 4 rows at speed 4 -> 2 steps each -> 8 MUSIC lines.
        assert len(music_lines(source)) == 8
        assert speeds == {4}


    def test_loop_section_inherits_sxx_from_intro(self) -> None:
        """A note without sXX in the loop inherits the intro's s02."""
        song = make_split_song()

        source, _ = convert(
            song, label="m_loop", data_byte=2, length_scale=3.0,
            invert_speed=False, pos_start=1,
        )

        lines = music_lines(source)
        # s02 with scale 3.0 -> 6 audible steps out of 8.
        assert lines[0] == "MUSIC D4W,-,-"
        assert lines[1:6] == ["MUSIC S,-,-"] * 5
        assert lines[6:] == ["MUSIC -,-,-"] * 2


    def test_stop_and_repeat_endings(self) -> None:
        """stop=True ends with MUSIC STOP, otherwise MUSIC REPEAT."""
        song = make_split_song()

        with_stop, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, stop=True,
        )
        with_repeat, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, stop=False,
        )

        assert with_stop.rstrip().endswith("MUSIC STOP")
        assert with_repeat.rstrip().endswith("MUSIC REPEAT")


    def test_label_and_data_byte_header(self) -> None:
        """The output starts with the label and the DATA BYTE line."""
        song = make_split_song()

        source, _ = convert(
            song, label="tune", data_byte=1, length_scale=3.0,
            invert_speed=False,
        )

        lines = source.splitlines()
        assert lines[0] == "tune:"
        assert lines[1].startswith("\tDATA BYTE 1")


    def test_excluded_channels_pack_left(self) -> None:
        """Excluding channel 1 moves channel 2 into the first MUSIC slot."""
        song = make_split_song()
        song.tracks[4] = [Cell(row=0, note=52, speed=1, instrument=1)]

        source, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, pos_start=1, exclude_channels={1},
        )

        lines = music_lines(source)
        assert lines[0] == "MUSIC E4W,-,-"


    def test_instrument_suffix_carries_across_patterns(self) -> None:
        """The suffix is emitted once and inherited by later patterns."""
        song = make_split_song()

        source, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False,
        )

        lines = music_lines(source)
        # Pattern 0 is 9 steps long (3 at speed 6 + 3x2 at speed 4):
        # its first note carries W, the note in pattern 1 does not.
        assert lines[0] == "MUSIC C4W,-,-"
        assert lines[9] == "MUSIC D4,-,-"


    def test_instrument_mapping_disabled(self) -> None:
        """map_instruments=False produces plain note names."""
        song = make_split_song()

        source, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, map_instruments=False,
        )

        lines = music_lines(source)
        assert lines[0] == "MUSIC C4,-,-"


    def test_articulation_diagnostic_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """convert logs how many sXX notes were clipped by the next note."""
        song = make_split_song()

        with caplog.at_level(logging.INFO, logger="arkos2basic.cvbasic"):
            convert(
                song, label="m", data_byte=2, length_scale=3.0,
                invert_speed=False,
            )

        messages = [r.getMessage() for r in caplog.records]
        assert any("sXX notes clipped" in m for m in messages)


    def test_drums_add_fourth_music_column(self) -> None:
        """Percussion notes move to the fourth channel as M-types."""
        song = make_split_song()
        song.drum_instruments = {9: "M1"}
        song.tracks[3] = [Cell(row=0, note=50, instrument=9)]

        source, _ = convert(
            song, label="m", data_byte=2, length_scale=3.0,
            invert_speed=False, pos_start=1, drum_length=1,
        )

        lines = music_lines(source)
        assert lines[0] == "MUSIC -,-,-,M1"
        assert lines[1] == "MUSIC -,-,-,-"
