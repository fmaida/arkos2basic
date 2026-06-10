"""Tests for the Arkos Tracker text format parser (TXTImport)."""

from pathlib import Path

from arkos2basic.arkostracker.cell import Cell
from arkos2basic.arkostracker.txtimport import TXTImport


EXAMPLE_FILE = Path(__file__).parent.parent / "examples" / "music_01.txt"

# Minimal but well-formed Arkos Tracker text export: three instruments
# (Empty, a melodic lead, a noise-based drum), one melodic track with a
# note + effect, a percussion note and an RST, one speed track, one
# pattern and two positions with a loop on the second one.
FIXTURE = """Arkos Tracker text format V1.0

SECTION song
formatVersion 3.0
title Test

-SECTION instruments

--SECTION instrument
name Empty

---SECTION cells

----SECTION cell
volume 0
noise 0
----ENDSECTION cell
---ENDSECTION cells
--ENDSECTION instrument

--SECTION instrument
name Lead

---SECTION cells

----SECTION cell
volume 15
noise 0
----ENDSECTION cell
---ENDSECTION cells
--ENDSECTION instrument

--SECTION instrument
name Drum

---SECTION cells

----SECTION cell
volume 15
noise 10
----ENDSECTION cell

----SECTION cell
volume 10
noise 0
----ENDSECTION cell
---ENDSECTION cells
--ENDSECTION instrument
-ENDSECTION instruments

-SECTION subsongs

--SECTION subsong
title Main
initialSpeed 6
loopStartPosition 1
endPosition 1
replayFrequencyHz 50

---SECTION tracks

----SECTION track
index 0

-----SECTION cell
index 0
note 40
instrument 1

------SECTION effect
index 0
name forceInstrumentSpeed
logicalValue 3
------ENDSECTION effect
-----ENDSECTION cell

-----SECTION cell
index 2
note 42
instrument 2
-----ENDSECTION cell

-----SECTION cell
index 4
note 43
instrument 0
-----ENDSECTION cell
----ENDSECTION track

----SECTION track
index 1
----ENDSECTION track

----SECTION track
index 2
----ENDSECTION track
---ENDSECTION tracks

---SECTION speedTracks

----SECTION speedTrack
index 0

-----SECTION cell
index 1
value 4
-----ENDSECTION cell
----ENDSECTION speedTrack
---ENDSECTION speedTracks

---SECTION patterns

----SECTION pattern

-----SECTION trackIndexes
trackIndex 0
-----ENDSECTION trackIndexes

-----SECTION trackIndexes
trackIndex 1
-----ENDSECTION trackIndexes

-----SECTION trackIndexes
trackIndex 2
-----ENDSECTION trackIndexes

-----SECTION speedTrackIndex
trackIndex 0
-----ENDSECTION speedTrackIndex
----ENDSECTION pattern
---ENDSECTION patterns

---SECTION positions

----SECTION position
patternIndex 0
height 8
----ENDSECTION position

----SECTION position
patternIndex 0
height 8
----ENDSECTION position
---ENDSECTION positions
--ENDSECTION subsong
-ENDSECTION subsongs
ENDSECTION song
"""


def parse_fixture(tmp_path: Path) -> TXTImport:
    """Write the fixture to disk and parse it.

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        The importer with the parsed song.
    """
    source = tmp_path / "fixture.txt"
    source.write_text(FIXTURE, encoding="utf-8")

    return TXTImport(input_file=source)


class TestParseFixture:
    """Tests on the synthetic fixture."""

    def test_subsong_header(self, tmp_path: Path) -> None:
        """initialSpeed, loopStartPosition and endPosition are read."""
        song = parse_fixture(tmp_path)._song

        assert song.initial_speed == 6
        assert song.loop_start_position == 1
        assert song.end_position == 1


    def test_positions_and_patterns(self, tmp_path: Path) -> None:
        """Positions, pattern track indexes and speed track are mapped."""
        song = parse_fixture(tmp_path)._song

        assert song.positions == [(0, 8), (0, 8)]
        assert song.patterns == {0: [0, 1, 2]}
        assert song.pattern_speed == {0: 0}
        assert song.speed_tracks == {0: {1: 4}}


    def test_track_cells(self, tmp_path: Path) -> None:
        """Notes, instruments and forceInstrumentSpeed land in the cells."""
        song = parse_fixture(tmp_path)._song

        assert song.tracks[0] == [
            Cell(row=0, note=40, speed=3, instrument=1),
            Cell(row=2, note=42, speed=None, instrument=2),
            Cell(row=4, note=43, speed=None, instrument=0),
        ]
        assert song.tracks[1] == []
        assert song.tracks[2] == []


    def test_drum_detection(self, tmp_path: Path) -> None:
        """Only the noise-based instrument is detected, with type M1."""
        song = parse_fixture(tmp_path)._song

        assert song.drum_instruments == {2: "M1"}


    def test_playback_end(self, tmp_path: Path) -> None:
        """playback_end is end_position + 1 when set."""
        song = parse_fixture(tmp_path)._song

        assert song.playback_end == 2


class TestNoiseToDrumType:
    """Tests for the noise period -> CVBasic drum type mapping."""

    def test_thresholds(self, tmp_path: Path) -> None:
        """1-5 -> M2, 6-15 -> M1, 16+ -> M3."""
        importer = parse_fixture(tmp_path)

        assert importer._noise_to_drum_type(3.0) == "M2"
        assert importer._noise_to_drum_type(5.0) == "M2"
        assert importer._noise_to_drum_type(6.0) == "M1"
        assert importer._noise_to_drum_type(15.0) == "M1"
        assert importer._noise_to_drum_type(16.0) == "M3"


class TestParseExampleFile:
    """Smoke tests on the real Arkos Tracker export in examples/."""

    def test_song_structure(self) -> None:
        """The example file parses with the expected global structure."""
        song = TXTImport(input_file=EXAMPLE_FILE)._song

        assert song.initial_speed == 6
        assert song.loop_start_position == 0
        assert song.end_position == 4
        assert len(song.positions) == 5
        assert song.speed_tracks == {3: {0: 7}}
        assert song.drum_instruments == {}
