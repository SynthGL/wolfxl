"""Style dataclasses matching openpyxl's public names.

These are lightweight, frozen value objects. They mirror openpyxl's Font,
PatternFill, Border, Side, Alignment, and Color classes so that code written
for openpyxl can be ported with minimal changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Color:
    """An ARGB color. ``rgb`` uses the 8-char Excel convention (AARRGGBB)."""

    rgb: str = "FF000000"

    def to_hex(self) -> str:
        """Return '#RRGGBB' (strips the alpha channel)."""
        raw = self.rgb.lstrip("#")
        if len(raw) == 8:
            return f"#{raw[2:]}"
        return f"#{raw}"

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Create from '#RRGGBB' or 'RRGGBB' (assumes FF alpha)."""
        raw = hex_str.lstrip("#")
        if len(raw) == 6:
            return cls(rgb=f"FF{raw.upper()}")
        return cls(rgb=raw.upper())


@dataclass(frozen=True)
class Font:
    """Text font properties."""

    name: str | None = None
    size: float | None = None
    bold: bool = False
    italic: bool = False
    underline: str | None = None  # "single", "double", etc.
    strike: bool = False
    color: Color | str | None = None

    def _color_hex(self) -> str | None:
        """Resolve color to a '#RRGGBB' string or None."""
        if self.color is None:
            return None
        if isinstance(self.color, Color):
            return self.color.to_hex()
        raw = str(self.color).lstrip("#")
        if len(raw) == 8:
            return f"#{raw[2:]}"
        return f"#{raw}"


@dataclass(frozen=True, init=False)
class PatternFill:
    """Cell fill (solid pattern only for now).

    Accepts both ``patternType=`` and ``fill_type=`` for openpyxl compatibility.
    """

    patternType: str | None = None  # noqa: N815 — matches openpyxl name
    fgColor: Color | str | None = None  # noqa: N815

    def __init__(
        self,
        patternType: str | None = None,  # noqa: N803
        fgColor: Color | str | None = None,  # noqa: N803
        *,
        fill_type: str | None = None,
    ) -> None:
        # fill_type is openpyxl's alias for patternType
        object.__setattr__(self, "patternType", fill_type if patternType is None else patternType)
        object.__setattr__(self, "fgColor", fgColor)

    def _fg_hex(self) -> str | None:
        """Resolve fgColor to a '#RRGGBB' string or None."""
        if self.fgColor is None:
            return None
        if isinstance(self.fgColor, Color):
            return self.fgColor.to_hex()
        raw = str(self.fgColor).lstrip("#")
        if len(raw) == 8:
            return f"#{raw[2:]}"
        return f"#{raw}"


@dataclass(frozen=True)
class Side:
    """One edge of a border."""

    style: str | None = None  # "thin", "medium", "thick", etc.
    color: Color | str | None = None

    def _color_hex(self) -> str | None:
        if self.color is None:
            return None
        if isinstance(self.color, Color):
            return self.color.to_hex()
        raw = str(self.color).lstrip("#")
        if len(raw) == 8:
            return f"#{raw[2:]}"
        return f"#{raw}"


@dataclass(frozen=True)
class Border:
    """Cell borders."""

    left: Side = field(default_factory=Side)
    right: Side = field(default_factory=Side)
    top: Side = field(default_factory=Side)
    bottom: Side = field(default_factory=Side)


@dataclass(frozen=True)
class Alignment:
    """Cell alignment."""

    horizontal: str | None = None
    vertical: str | None = None
    wrap_text: bool = False
    text_rotation: int = 0
    indent: int = 0
