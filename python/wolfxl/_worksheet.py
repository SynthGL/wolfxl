"""Worksheet proxy — provides ``ws['A1']`` access and tracks dirty cells."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from wolfxl._cell import Cell
from wolfxl._utils import a1_to_rowcol, rowcol_to_a1

if TYPE_CHECKING:
    from wolfxl._workbook import Workbook


class Worksheet:
    """Proxy for a single worksheet in a Workbook."""

    __slots__ = ("_workbook", "_title", "_cells", "_dirty", "_dimensions")

    def __init__(self, workbook: Workbook, title: str) -> None:
        self._workbook = workbook
        self._title = title
        self._cells: dict[tuple[int, int], Cell] = {}
        self._dirty: set[tuple[int, int]] = set()
        self._dimensions: tuple[int, int] | None = None

    @property
    def title(self) -> str:
        return self._title

    # ------------------------------------------------------------------
    # Cell access
    # ------------------------------------------------------------------

    def __getitem__(self, key: str) -> Cell:
        """``ws['A1']`` -> Cell."""
        row, col = a1_to_rowcol(key)
        return self._get_or_create_cell(row, col)

    def __setitem__(self, key: str, value: Any) -> None:
        """``ws['A1'] = 42`` — shorthand for setting a cell's value."""
        cell = self[key]
        cell.value = value

    def cell(self, row: int, column: int, value: Any = None) -> Cell:
        """Get or create a cell by 1-based (row, column). Matches openpyxl API."""
        c = self._get_or_create_cell(row, column)
        if value is not None:
            c.value = value
        return c

    def _get_or_create_cell(self, row: int, col: int) -> Cell:
        key = (row, col)
        if key not in self._cells:
            self._cells[key] = Cell(self, row, col)
        return self._cells[key]

    def _mark_dirty(self, row: int, col: int) -> None:
        self._dirty.add((row, col))

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def iter_rows(
        self,
        min_row: int | None = None,
        max_row: int | None = None,
        min_col: int | None = None,
        max_col: int | None = None,
        values_only: bool = False,
    ) -> Iterator[tuple[Any, ...]]:
        """Iterate over rows in a range. Matches openpyxl's iter_rows API."""
        r_min = min_row or 1
        r_max = max_row or self._max_row()
        c_min = min_col or 1
        c_max = max_col or self._max_col()

        for r in range(r_min, r_max + 1):
            if values_only:
                yield tuple(
                    self._get_or_create_cell(r, c).value for c in range(c_min, c_max + 1)
                )
            else:
                yield tuple(
                    self._get_or_create_cell(r, c) for c in range(c_min, c_max + 1)
                )

    def _read_dimensions(self) -> tuple[int, int]:
        """Discover sheet dimensions from the Rust backend (read mode only)."""
        if self._dimensions is not None:
            return self._dimensions
        wb = self._workbook
        if wb._rust_reader is None:  # noqa: SLF001
            self._dimensions = (1, 1)
            return self._dimensions
        rows = wb._rust_reader.read_sheet_values(self._title, None)  # noqa: SLF001
        if not rows or not isinstance(rows, list):
            self._dimensions = (1, 1)
            return self._dimensions
        max_r = len(rows)
        max_c = max((len(row) for row in rows), default=1)
        self._dimensions = (max_r, max_c)
        return self._dimensions

    def _max_row(self) -> int:
        if self._workbook._rust_reader is not None:  # noqa: SLF001
            return self._read_dimensions()[0]
        if not self._cells:
            return 1
        return max(k[0] for k in self._cells)

    def _max_col(self) -> int:
        if self._workbook._rust_reader is not None:  # noqa: SLF001
            return self._read_dimensions()[1]
        if not self._cells:
            return 1
        return max(k[1] for k in self._cells)

    # ------------------------------------------------------------------
    # Write-mode helpers
    # ------------------------------------------------------------------

    def merge_cells(self, range_string: str) -> None:
        """Merge cells (write mode only). Example: ``ws.merge_cells('A1:B2')``."""
        wb = self._workbook
        if wb._rust_writer is None:  # noqa: SLF001
            raise RuntimeError("merge_cells requires write mode")
        wb._rust_writer.merge_cells(self._title, range_string)  # noqa: SLF001

    # ------------------------------------------------------------------
    # Flush pending writes to Rust
    # ------------------------------------------------------------------

    def _flush(self) -> None:
        """Write all dirty cells to the Rust backend. Called by Workbook.save()."""
        from wolfxl._cell import (
            alignment_to_format_dict,
            border_to_rust_dict,
            fill_to_format_dict,
            font_to_format_dict,
            python_value_to_payload,
        )

        wb = self._workbook
        patcher = wb._rust_patcher  # noqa: SLF001
        writer = wb._rust_writer  # noqa: SLF001

        if patcher is not None:
            self._flush_to_patcher(patcher, python_value_to_payload,
                                   font_to_format_dict, fill_to_format_dict,
                                   alignment_to_format_dict, border_to_rust_dict)
        elif writer is not None:
            self._flush_to_writer(writer, python_value_to_payload,
                                  font_to_format_dict, fill_to_format_dict,
                                  alignment_to_format_dict, border_to_rust_dict)

        self._dirty.clear()

    def _flush_to_writer(
        self, writer: Any, python_value_to_payload: Any,
        font_to_format_dict: Any, fill_to_format_dict: Any,
        alignment_to_format_dict: Any, border_to_rust_dict: Any,
    ) -> None:
        """Flush dirty cells to the RustXlsxWriterBook backend (write mode)."""
        from wolfxl._cell import _UNSET

        for row, col in self._dirty:
            cell = self._cells.get((row, col))
            if cell is None:
                continue
            coord = rowcol_to_a1(row, col)

            if cell._value_dirty:  # noqa: SLF001
                payload = python_value_to_payload(cell._value)  # noqa: SLF001
                writer.write_cell_value(self._title, coord, payload)

            if cell._format_dirty:  # noqa: SLF001
                fmt: dict[str, Any] = {}

                if cell._font is not _UNSET and cell._font is not None:  # noqa: SLF001
                    fmt.update(font_to_format_dict(cell._font))  # noqa: SLF001
                if cell._fill is not _UNSET and cell._fill is not None:  # noqa: SLF001
                    fmt.update(fill_to_format_dict(cell._fill))  # noqa: SLF001
                if cell._alignment is not _UNSET and cell._alignment is not None:  # noqa: SLF001
                    fmt.update(alignment_to_format_dict(cell._alignment))  # noqa: SLF001
                if cell._number_format is not _UNSET and cell._number_format is not None:  # noqa: SLF001
                    fmt["number_format"] = cell._number_format  # noqa: SLF001

                if fmt:
                    writer.write_cell_format(self._title, coord, fmt)

                if cell._border is not _UNSET and cell._border is not None:  # noqa: SLF001
                    bdict = border_to_rust_dict(cell._border)  # noqa: SLF001
                    if bdict:
                        writer.write_cell_border(self._title, coord, bdict)

    def _flush_to_patcher(
        self, patcher: Any, python_value_to_payload: Any,
        font_to_format_dict: Any, fill_to_format_dict: Any,
        alignment_to_format_dict: Any, border_to_rust_dict: Any,
    ) -> None:
        """Flush dirty cells to the XlsxPatcher backend (modify mode)."""
        from wolfxl._cell import _UNSET

        for row, col in self._dirty:
            cell = self._cells.get((row, col))
            if cell is None:
                continue
            coord = rowcol_to_a1(row, col)

            if cell._value_dirty:  # noqa: SLF001
                payload = python_value_to_payload(cell._value)  # noqa: SLF001
                patcher.queue_value(self._title, coord, payload)

            if cell._format_dirty:  # noqa: SLF001
                fmt: dict[str, Any] = {}

                if cell._font is not _UNSET and cell._font is not None:  # noqa: SLF001
                    fmt.update(font_to_format_dict(cell._font))  # noqa: SLF001
                if cell._fill is not _UNSET and cell._fill is not None:  # noqa: SLF001
                    fmt.update(fill_to_format_dict(cell._fill))  # noqa: SLF001
                if cell._alignment is not _UNSET and cell._alignment is not None:  # noqa: SLF001
                    fmt.update(alignment_to_format_dict(cell._alignment))  # noqa: SLF001
                if cell._number_format is not _UNSET and cell._number_format is not None:  # noqa: SLF001
                    fmt["number_format"] = cell._number_format  # noqa: SLF001

                if fmt:
                    patcher.queue_format(self._title, coord, fmt)

                if cell._border is not _UNSET and cell._border is not None:  # noqa: SLF001
                    bdict = border_to_rust_dict(cell._border)  # noqa: SLF001
                    if bdict:
                        patcher.queue_border(self._title, coord, bdict)

    def __repr__(self) -> str:
        return f"<Worksheet [{self._title}]>"
