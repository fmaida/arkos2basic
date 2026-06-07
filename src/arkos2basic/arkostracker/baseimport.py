"""Base class for Arkos Tracker file importers."""

import logging
from pathlib import Path

from arkos2basic.arkostracker.song import Song
from arkos2basic.cvbasic import convert


logger = logging.getLogger(__name__)


class BaseImport:
    """Base importer for Arkos Tracker source files.

    Subclasses implement parse() to read a specific file format and return
    a Song. Everything else — transpose, split logic, CVBasic output — is
    handled here and is available to every future importer for free.

    Typical usage::

        importer = TXTImport(input_file=path)
        importer.transpose(effective_semitones)
        importer.export(output_file=out, ...)

    Attributes:
        input_file: path to the source file.
    """

    def __init__(self, input_file: Path) -> None:
        """Parse the source file and prepare the importer.

        Args:
            input_file: path to the source file to import.
        """
        self.input_file = input_file
        self._song: Song = self.parse()
        self._transpose: int = 0


    def parse(self) -> Song:
        """Read self.input_file and return the parsed Song.

        Subclasses must override this method.

        Returns:
            A Song object with positions, patterns, tracks, and speeds.
        """
        raise NotImplementedError


    def transpose(self, notes: int) -> None:
        """Set the semitone shift applied to all melodic notes on export.

        Args:
            notes: total semitones to add (positive = up, negative = down;
                12 = one octave up).
        """
        self._transpose = notes


    def export(
        self,
        output_file: Path,
        label: str,
        data_byte: int,
        length_scale: float,
        invert_speed: bool,
        stop: bool,
        drum_length: int,
        exclude_channels: set[int] | None = None,
    ) -> None:
        """Convert the song to CVBasic and write the output file(s).

        Handles the intro/loop split automatically: if loop_start_position
        > 0 and stop is False, two files are written (intro + loop).
        Otherwise a single file is written. Status messages are emitted
        via the module logger at INFO level.

        Args:
            output_file: path for the main output .bas file.
            label: label assigned to the music block.
            data_byte: frames per MUSIC step.
            length_scale: factor for note sounding duration.
            invert_speed: if True, high forceInstrumentSpeed = shorter note.
            stop: if True, always end with MUSIC STOP (no split).
            drum_length: consecutive steps per percussion hit.
            exclude_channels: 1-based source channel indices to skip.
        """
        song = self._song
        do_split = song.loop_start_position > 0 and not stop

        conv_args: dict = dict(
            data_byte=data_byte,
            length_scale=length_scale,
            invert_speed=invert_speed,
            drum_length=drum_length,
            exclude_channels=exclude_channels,
            transpose=self._transpose,
        )

        if do_split:
            song_end = (
                song.end_position + 1 if song.end_position >= 0
                else len(song.positions)
            )
            source_intro, speeds_intro = convert(
                song, label=label, stop=True,
                pos_start=0, pos_end=song.loop_start_position,
                **conv_args,
            )
            loop_label = f"{label}_loop"
            source_loop, speeds_loop = convert(
                song, label=loop_label, stop=False,
                pos_start=song.loop_start_position, pos_end=song_end,
                **conv_args,
            )
            speeds = speeds_intro | speeds_loop

            output_file.write_text(source_intro, encoding="utf-8")
            loop_path = output_file.with_stem(output_file.stem + "_loop")
            loop_path.write_text(source_loop, encoding="utf-8")

            intro_patterns = song.loop_start_position
            loop_patterns = song_end - song.loop_start_position
            logger.info(
                "Split intro/loop: %d pattern(s) intro, %d pattern(s) loop.",
                intro_patterns,
                loop_patterns,
            )
            logger.info("  Intro  -> %s  (label: %s)", output_file, label)
            logger.info("  Loop   -> %s  (label: %s)", loop_path, loop_label)
        else:
            source, speeds = convert(
                song, label=label, stop=stop, pos_start=0, **conv_args,
            )
            output_file.write_text(source, encoding="utf-8")

            music_lines = source.count("\tMUSIC ")
            logger.info("Converted: %d patterns.", len(song.positions))
            logger.info(
                "DATA BYTE: %d  ->  MUSIC rows: %d", data_byte, music_lines
            )
            logger.info("Output written to: %s", output_file)

        logger.info(
            "Speeds found (tracker frames/row): %s", sorted(speeds)
        )
        if song.drum_instruments:
            logger.info(
                "Percussion instruments detected: %s",
                dict(song.drum_instruments),
            )
        else:
            logger.info("No percussion instruments detected.")
