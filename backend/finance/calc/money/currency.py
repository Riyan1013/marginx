"""Currency model and lookup interface (decision Q5, U1, U7).

Standard library plus the sibling ``errors`` and ``rounding`` modules only.

This module defines only the *shape* of currency metadata and how to look it
up. It contains **no currency records and no default instance**: rules and
reference values are data, rule types and algorithms are code. The actual
records (the initial MVP currencies) are supplied by the reference-data
fixture provider in M1-5, which builds a ``CurrencyTable`` from them.

A currency's ``rounding_mode`` is one level of the rounding precedence (Q1).
This module does not resolve modes: callers pass ``currency.rounding_mode`` to
``resolve_rounding_mode(currency=...)``.

Invalid ``Currency`` fields raise ``TypeError`` (wrong type) or ``ValueError``
(right type, unacceptable value), like the helpers in ``rounding``. They are
not decimal-grammar errors and carry no registry code (U5).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from .errors import UnknownCurrencyError
from .rounding import RoundingMode

#: Three uppercase ASCII letters. Matched with ``fullmatch`` so a trailing
#: newline or any non-ASCII letter is rejected.
_CODE_PATTERN = re.compile(r"[A-Z]{3}")


@dataclass(frozen=True)
class Currency:
    """Immutable, validated currency metadata.

    ``code``            three uppercase ASCII letters.
    ``minor_units``     number of decimal places of the minor unit; an ``int``
                        of 0 or more (``bool`` is rejected).
    ``rounding_mode``   a ``RoundingMode``, or ``None`` meaning "no
                        currency-level setting" (U1). It is never defaulted
                        here: ``None`` falls through to the next level.
    ``price_increment`` a finite ``Decimal`` greater than zero.
    """

    code: str
    minor_units: int
    rounding_mode: RoundingMode | None
    price_increment: Decimal

    def __post_init__(self) -> None:
        code = self.code
        if type(code) is not str:
            raise TypeError(f"code must be a str, not {type(code).__name__}")
        if _CODE_PATTERN.fullmatch(code) is None:
            raise ValueError(f"code must be three uppercase ASCII letters, not {code!r}")

        minor_units = self.minor_units
        if type(minor_units) is not int:
            raise TypeError(
                f"minor_units must be an int, not {type(minor_units).__name__}"
            )
        if minor_units < 0:
            raise ValueError(f"minor_units must be 0 or more, not {minor_units}")

        mode = self.rounding_mode
        if mode is not None and not isinstance(mode, RoundingMode):
            raise TypeError(
                f"rounding_mode must be a RoundingMode or None, not {type(mode).__name__}"
            )

        increment = self.price_increment
        if not isinstance(increment, Decimal):
            raise TypeError(
                f"price_increment must be a Decimal, not {type(increment).__name__}"
            )
        if not increment.is_finite():
            raise ValueError(f"price_increment must be finite, not {increment}")
        if not increment > 0:
            raise ValueError(f"price_increment must be greater than zero, not {increment}")


@runtime_checkable
class CurrencyProvider(Protocol):
    """Anything that can look a currency up by code (U7).

    ``get`` raises ``UnknownCurrencyError`` for a code it does not know. M1-5
    provides the fixture-backed implementation.
    """

    def get(self, code: str) -> Currency: ...


class CurrencyTable:
    """An immutable lookup table built from records the caller supplies (U7).

    Construction validates that every item is a ``Currency`` and that no code
    appears twice. Codes are matched exactly: there is no case folding and no
    trimming. The table has no mutating method, and its records cannot be
    changed after construction. An empty table is allowed.
    """

    __slots__ = ("_records",)

    def __init__(self, records: Iterable[Currency]) -> None:
        table: dict[str, Currency] = {}
        for record in records:
            if not isinstance(record, Currency):
                raise TypeError(
                    f"records must be Currency objects, not {type(record).__name__}"
                )
            if record.code in table:
                raise ValueError(f"duplicate currency code {record.code!r}")
            table[record.code] = record
        records_view: Mapping[str, Currency] = MappingProxyType(table)
        object.__setattr__(self, "_records", records_view)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("CurrencyTable is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CurrencyTable is immutable")

    def get(self, code: str) -> Currency:
        """Return the record for ``code`` or raise ``UnknownCurrencyError``."""
        if type(code) is str:
            record = self._records.get(code)
            if record is not None:
                return record
        raise UnknownCurrencyError(f"unknown currency code {code!r}")

    def __contains__(self, code: object) -> bool:
        return type(code) is str and code in self._records

    def __len__(self) -> int:
        return len(self._records)
