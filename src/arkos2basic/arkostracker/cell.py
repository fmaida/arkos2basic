"""Data model for a single Arkos Tracker cell."""

from dataclasses import dataclass


@dataclass
class Cell:
    """A single tracker cell.

    Attributes:
        row: row index in the pattern (vertical position).
        note: MIDI-style note number, or -1 if absent.
        speed: forceInstrumentSpeed value of the cell, or None.
        instrument: instrument index (-1 if unspecified).
            Instrument 0 ("Empty") signals an RST: the channel goes
            silent from that row onward.
    """

    row: int
    note: int
    speed: int | None = None
    instrument: int = -1
