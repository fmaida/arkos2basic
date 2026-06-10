"""Arkos Tracker text format (V1.0) to CVBasic music converter — CLI entry point.

Receives command-line arguments, orchestrates the importer and the CVBasic
exporter, and writes status messages to stdout at the end of execution.
"""

import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from arkos2basic.arkostracker.txtimport import TXTImport


app = typer.Typer(help="Convert an Arkos Tracker (.txt) file to CVBasic music.")


@app.command()
def main(
    input_file: Annotated[
        Path,
        typer.Argument(
            help="Input Arkos Tracker file",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    output_file: Annotated[
        Path,
        typer.Argument(help="Output .bas file"),
    ],
    octaves: Annotated[
        int,
        typer.Option(
            help="Octave delta relative to base +1 "
                 "(e.g. --octaves 1 → +2 octaves, --octaves -1 → 0)"
        ),
    ] = 0,
    data_byte: Annotated[
        int,
        typer.Option(
            help="Frames per MUSIC step: lower = more faithful but more rows "
                 "(1 = exact timing)"
        ),
    ] = 2,
    length_scale: Annotated[
        float,
        typer.Option(
            "--length",
            help="Delta from base 3.0 for note sounding duration "
                 "(e.g. --length 1 → 4.0, --length -1 → 2.0)",
        ),
    ] = 0.0,
    invert: Annotated[
        bool,
        typer.Option(
            help="Invert the scale: high forceInstrumentSpeed = shorter note"
        ),
    ] = False,
    label: Annotated[
        str,
        typer.Option(help="Label for the music block in the output source"),
    ] = "musica",
    stop: Annotated[
        bool,
        typer.Option("--stop", help="End with MUSIC STOP instead of MUSIC REPEAT"),
    ] = False,
    drum_length: Annotated[
        int,
        typer.Option(
            help="Delta from base 2 steps per percussion hit "
                 "(e.g. --drum-length 1 → 3, --drum-length -1 → 1)",
        ),
    ] = 0,
    exclude_channels: Annotated[
        str,
        typer.Option(
            "--exclude-channels",
            help="Source channels to exclude, comma-separated "
                 "(1-3, e.g. '2' or '2,3'). Remaining channels pack left.",
        ),
    ] = "",
    transpose: Annotated[
        int,
        typer.Option(
            help="Chromatic semitones to add to all notes "
                 "(positive = up, negative = down; 12 = +1 octave).",
        ),
    ] = 0,
    no_instruments: Annotated[
        bool,
        typer.Option(
            "--no-instruments",
            help="Do not map Arkos instruments 1-3 to CVBasic W/X/Y; "
                 "all melodic notes use the default piano.",
        ),
    ] = False,
) -> None:
    """Command-line entry point."""
    if data_byte < 1:
        typer.echo("Error: --data-byte must be at least 1", err=True)
        raise typer.Exit(1)

    excluded: set[int] = set()
    for part in exclude_channels.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            val = int(part)
        except ValueError:
            typer.echo(
                f"Error: --exclude-channels only accepts values 1, 2, 3 "
                f"(got: '{part}')",
                err=True,
            )
            raise typer.Exit(1)
        if val not in (1, 2, 3):
            typer.echo(
                f"Error: --exclude-channels only accepts values 1, 2, 3 "
                f"(got: {val})",
                err=True,
            )
            raise typer.Exit(1)
        excluded.add(val)

    importer = TXTImport(input_file=input_file)

    # --octaves N contributes (1 + N) * 12 semitones (base 1 octave + delta).
    # --transpose M adds M fine semitones on top.
    effective_transpose = (1 + octaves) * 12 + transpose
    importer.transpose(effective_transpose)

    log_handler = logging.StreamHandler(sys.stdout)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    pkg_logger = logging.getLogger("arkos2basic")
    pkg_logger.addHandler(log_handler)
    pkg_logger.setLevel(logging.INFO)

    exclude_set: set[int] | None = None
    if excluded:
        exclude_set = excluded

    try:
        importer.export(
            output_file=output_file,
            label=label,
            data_byte=data_byte,
            length_scale=3.0 + length_scale,
            invert_speed=invert,
            stop=stop,
            drum_length=2 + drum_length,
            exclude_channels=exclude_set,
            map_instruments=not no_instruments,
        )
    finally:
        pkg_logger.removeHandler(log_handler)


if __name__ == "__main__":
    app()
