"""Decimal calculation context and exact arithmetic helpers (standard library only).

Decisions: CA-1 (precision 60, ``ROUND_HALF_UP``, plain strings) and O-16.

Every helper here runs on an **explicit** context that is built fresh by
``make_context()``. The ambient ``decimal`` context (``getcontext()``) is never
read and never modified, so a caller (or another library) that changed the
ambient precision or rounding cannot change any money result.

The context traps ``InvalidOperation``, ``DivisionByZero`` and ``Overflow``.
It deliberately does **not** trap ``Inexact`` or ``Rounded``: a division such as
100.00 / 3 is expected to be inexact at precision 60 and is rounded later, by
the rounding module, to the scale the caller asks for.

Exact multiplication: a 19-digit amount times a 21-digit FX rate has 40
significant digits, which fits inside precision 60, so ``mul`` is exact for
every value that passes the grammar limits (CL-06).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)

#: Significant digits of the calculation context (CA-1).
PRECISION = 60

#: Rounding of the calculation context itself (CA-1). This is the *context*
#: default only; the rounding of a particular amount is chosen by the rounding
#: module through ``quantize``.
CONTEXT_ROUNDING = ROUND_HALF_UP

_TRAPS = (InvalidOperation, DivisionByZero, Overflow)

# Exponent limits are the CPython defaults, written out so they cannot drift
# with the ambient context.
_EMIN = -999999
_EMAX = 999999


def make_context() -> Context:
    """Return a **new** calculation context.

    It is built from constants, never copied from the ambient context, and a
    distinct object is returned on every call so callers cannot share state.
    """
    return Context(
        prec=PRECISION,
        rounding=CONTEXT_ROUNDING,
        Emin=_EMIN,
        Emax=_EMAX,
        capitals=1,
        clamp=0,
        flags=[],
        traps=list(_TRAPS),
    )


@contextmanager
def calc_context() -> Iterator[Context]:
    """Install a fresh calculation context as the current one for a block.

    Use it when third-party code inside the block must see the calculation
    context. The previous ambient context is restored on exit, also when the
    block raises. The helpers in this module do not need it: they take an
    explicit context.
    """
    with localcontext(make_context()) as ctx:
        yield ctx


def _require_decimal(name: str, value: object) -> Decimal:
    """Reject anything that is not a ``Decimal`` (no float, int, str or bool)."""
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal, not {type(value).__name__}")
    return value


def mul(a: Decimal, b: Decimal, ctx: Context | None = None) -> Decimal:
    """Return ``a * b`` on the calculation context."""
    ctx = ctx if ctx is not None else make_context()
    return ctx.multiply(_require_decimal("a", a), _require_decimal("b", b))


def div(a: Decimal, b: Decimal, ctx: Context | None = None) -> Decimal:
    """Return ``a / b`` on the calculation context (60 significant digits).

    Division by zero raises ``decimal.DivisionByZero`` (or ``InvalidOperation``
    for 0 / 0) because both are trapped.
    """
    ctx = ctx if ctx is not None else make_context()
    return ctx.divide(_require_decimal("a", a), _require_decimal("b", b))


def add(a: Decimal, b: Decimal, ctx: Context | None = None) -> Decimal:
    """Return ``a + b`` on the calculation context."""
    ctx = ctx if ctx is not None else make_context()
    return ctx.add(_require_decimal("a", a), _require_decimal("b", b))


def total(values: Iterable[Decimal], ctx: Context | None = None) -> Decimal:
    """Return the exact sum of ``values`` on the calculation context.

    The sum of no values is ``Decimal("0")``. Values are added in order; the
    result keeps the largest scale of its inputs (``1.00 + 2.00`` is ``3.00``).
    """
    ctx = ctx if ctx is not None else make_context()
    result = Decimal(0)
    for index, value in enumerate(values):
        result = ctx.add(result, _require_decimal(f"values[{index}]", value))
    return result
