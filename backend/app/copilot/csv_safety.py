from __future__ import annotations

import csv
from typing import Any, Iterable, TextIO


_FORMULA_PREFIXES = ("=", "+", "-", "@")
_CONTROL_PREFIXES = ("\t", "\r", "\n")


def safe_spreadsheet_cell(value: Any) -> Any:
    """Neutralize formula-like *text* cells before CSV is opened by spreadsheet apps.

    Numeric values remain numeric. Text whose first non-whitespace character can start a
    formula receives a leading apostrophe, including cells with leading spaces/control
    characters. CSV remains otherwise unmodified.
    """
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip(" \t\r\n")
    if value.startswith(_CONTROL_PREFIXES) or stripped.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


class SpreadsheetSafeCSVWriter:
    """Small csv.writer wrapper that sanitizes each text cell before serialization."""

    def __init__(self, output: TextIO, **kwargs: Any) -> None:
        self._writer = csv.writer(output, **kwargs)

    def writerow(self, row: Iterable[Any]) -> Any:
        return self._writer.writerow([safe_spreadsheet_cell(cell) for cell in row])

    def writerows(self, rows: Iterable[Iterable[Any]]) -> Any:
        return self._writer.writerows(
            [safe_spreadsheet_cell(cell) for cell in row] for row in rows
        )
