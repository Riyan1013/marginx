"""E1 dependency rules for finance/calc (M1-1, step 6).

Dependencies point downward only. ``money`` imports the standard library and
its own package, nothing else. Nothing under ``finance/calc/`` imports
``finance.engine``, ``finance.schemas`` or ``finance.routes`` (or any other
legacy module). The only allowed third-party package is Pydantic, and never in
``money``.

How this file is organised
--------------------------
* ``DEPENDS`` encodes the E1 table as data.
* ``find_violations`` is a pure function over a source string, so the scanner
  itself is tested on deliberately bad sources and cannot pass vacuously.
* The "real project" tests run the scanner over every file that exists under
  ``finance/calc/``. Today that is ``money`` only; each later package is held
  to its row as soon as it is created, and a package with no row fails.

Caveat on the table
-------------------
The extracted PDF text of E1 (Closure Pack, page 22-23) lost its column layout,
but the order of the packages and of the "may depend on" cells is preserved, so
the rows were reconstructed by position. ``money`` (standard library only) is
unambiguous. Rows other than ``money`` only take effect when that package is
first created; re-check them against the PDF at that step. Nothing here
enforces a row for a package that does not exist yet.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
CALC_DIR = BACKEND / "finance" / "calc"

STDLIB = sys.stdlib_module_names

# ------------------------------------------------------------ the E1 table
# package -> the calc packages it may import (own package always allowed).
DEPENDS: dict[str, frozenset[str]] = {
    "money": frozenset(),  # E1: standard library only (unambiguous)
    # ---- rows below are reconstructed by position from E1: re-check when created ----
    "errors": frozenset({"money"}),
    "costlines": frozenset({"money", "errors"}),
    "corridor": frozenset({"costlines", "errors"}),
    "refdata": frozenset({"money", "errors"}),
    "rules": frozenset({"money", "costlines", "refdata"}),  # refdata: interface only
    "engines": frozenset({"rules", "refdata", "corridor", "costlines"}),  # refdata: interface
    "pipeline": frozenset(
        {"money", "errors", "costlines", "corridor", "refdata", "rules", "engines"}
    ),  # "all of the above"
    "api": frozenset({"pipeline", "errors"}),  # M2 only
}

# Third-party packages allowed per package. E1: Pydantic is the only allowed
# third-party dependency, and money may not use it. ``None`` means the policy
# is not decided yet (the api package is an M2 decision), so it fails loudly.
THIRD_PARTY: dict[str, frozenset[str] | None] = {
    pkg: frozenset({"pydantic"}) for pkg in DEPENDS
}
THIRD_PARTY["money"] = frozenset()
THIRD_PARTY["api"] = None

FORBIDDEN_MODULE_NAMES = {"engine", "schemas", "routes"}


# ------------------------------------------------------------- the scanner
def _imported_modules(tree: ast.AST, package_parts: list[str]) -> list[tuple[int, str]]:
    """(line, absolute dotted name) for every import in a module.

    ``package_parts`` is the package that contains the module, for example
    ``["finance", "calc", "money"]`` for ``finance/calc/money/context.py``.
    """
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = (node.module or "").split(".") if node.module else []
            else:
                keep = len(package_parts) - (node.level - 1)
                if keep <= 0:
                    found.append((node.lineno, "<beyond-top-level>"))
                    continue
                base = package_parts[:keep] + (node.module.split(".") if node.module else [])
            dotted = ".".join(base)
            if dotted in {"finance", "finance.calc"} or not node.module:
                # "from <package> import name": the names are submodules.
                for alias in node.names:
                    found.append((node.lineno, f"{dotted}.{alias.name}"))
            else:
                found.append((node.lineno, dotted))
    return found


def find_violations(
    source: str,
    owner: str | None,
    package_parts: list[str],
) -> list[str]:
    """Rule breaches in one module. ``owner`` None means calc/__init__.py."""
    tree = ast.parse(source)
    problems: list[str] = []
    imports = _imported_modules(tree, package_parts)

    if owner is None:
        return [f"line {ln}: calc/__init__.py must not import ({name})" for ln, name in imports]

    allowed_calc = DEPENDS[owner] | {owner}
    third_party = THIRD_PARTY[owner]
    for lineno, dotted in imports:
        parts = dotted.split(".")
        root = parts[0]
        if root == "finance":
            if parts == ["finance", "calc"]:
                problems.append(f"line {lineno}: imports the calc package root")
            elif len(parts) >= 3 and parts[1] == "calc":
                if parts[2] not in allowed_calc:
                    problems.append(
                        f"line {lineno}: {owner} may not import calc package {parts[2]!r} "
                        f"({dotted})"
                    )
            else:
                problems.append(f"line {lineno}: imports legacy code ({dotted})")
        elif dotted == "<beyond-top-level>":
            problems.append(f"line {lineno}: relative import leaves the package tree")
        elif root in STDLIB:
            continue
        elif third_party is None:
            problems.append(f"line {lineno}: third-party policy for {owner!r} is undecided ({root})")
        elif root not in third_party:
            problems.append(f"line {lineno}: third-party import not allowed in {owner} ({root})")
    return problems


# ------------------------------------------------------ discovery of files
def _calc_packages() -> list[Path]:
    return sorted(
        p for p in CALC_DIR.iterdir() if p.is_dir() and p.name != "__pycache__"
    )


def _calc_files() -> list[tuple[str, Path]]:
    """(package name, file) for every module inside a calc subpackage."""
    out: list[tuple[str, Path]] = []
    for pkg in _calc_packages():
        for path in sorted(pkg.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            out.append((pkg.name, path))
    return out


def _package_parts(path: Path) -> list[str]:
    """The package that contains ``path`` (an ``__init__.py`` is its own package)."""
    rel = path.relative_to(BACKEND).with_suffix("")
    parts = list(rel.parts)
    return parts[:-1]


def _rel(path: Path) -> str:
    return path.relative_to(BACKEND).as_posix()


# ---------------------------------------------------------- the table itself
class TestTable:
    def test_money_depends_on_nothing_but_the_standard_library(self):
        assert DEPENDS["money"] == frozenset()
        assert THIRD_PARTY["money"] == frozenset()

    def test_every_dependency_names_a_known_package(self):
        for pkg, deps in DEPENDS.items():
            assert deps <= set(DEPENDS), (pkg, deps - set(DEPENDS))

    def test_no_package_depends_on_itself(self):
        for pkg, deps in DEPENDS.items():
            assert pkg not in deps

    def test_dependencies_point_downward_only(self):
        """No cycles: a depth can be assigned so every dependency is lower."""
        depth: dict[str, int] = {}
        remaining = dict(DEPENDS)
        while remaining:
            ready = [p for p, d in remaining.items() if all(x in depth for x in d)]
            assert ready, f"dependency cycle among {sorted(remaining)}"
            for pkg in ready:
                depth[pkg] = 1 + max((depth[x] for x in remaining[pkg]), default=-1)
                del remaining[pkg]
        for pkg, deps in DEPENDS.items():
            assert all(depth[d] < depth[pkg] for d in deps)

    def test_money_is_at_the_bottom_and_api_at_the_top(self):
        assert all("api" not in deps for deps in DEPENDS.values())
        assert all("pipeline" not in deps for pkg, deps in DEPENDS.items() if pkg != "api")

    def test_engines_never_depend_on_each_other(self):
        """Only pipeline sequences engines. No other row may import them."""
        for pkg, deps in DEPENDS.items():
            if pkg not in {"pipeline"}:
                assert "engines" not in deps

    def test_pydantic_is_the_only_third_party_name_in_the_table(self):
        names = set()
        for allowed in THIRD_PARTY.values():
            names |= set(allowed or ())
        assert names <= {"pydantic"}


# ------------------------------------------------- the scanner is not vacuous
MONEY = ["finance", "calc", "money"]


class TestScannerCatchesBadSources:
    @pytest.mark.parametrize(
        "source",
        [
            "import pydantic",
            "from pydantic import BaseModel",
            "import fastapi",
            "from fastapi import APIRouter",
            "import numpy",
            "import requests",
        ],
    )
    def test_money_rejects_every_third_party_package(self, source):
        assert find_violations(source, "money", MONEY)

    @pytest.mark.parametrize(
        "source",
        [
            "import finance.engine",
            "from finance import engine",
            "from finance import schemas",
            "from finance.routes import router",
            "from finance.schemas import X",
            "import finance",
        ],
    )
    def test_legacy_modules_are_rejected_in_every_form(self, source):
        # "import finance" alone is not a legacy *module* import, but it is
        # still the legacy package root and is not allowed under calc.
        assert find_violations(source, "money", MONEY), source

    @pytest.mark.parametrize(
        "source",
        [
            "from .. import engine",  # resolves to finance.calc.engine: no such package
            "from ..engine import x",
            "from ... import engine",  # resolves to finance.engine
            "from ...engine import x",  # resolves to finance.engine
            "from .... import x",  # leaves the tree
        ],
    )
    def test_relative_forms_that_escape_are_rejected(self, source):
        assert find_violations(source, "money", MONEY), source

    @pytest.mark.parametrize(
        "source",
        [
            "from finance.calc.errors import X",
            "from finance.calc import errors",
            "from .. import errors",
            "from ..errors import X",
            "import finance.calc.pipeline",
            "from ..rules import evaluate",
        ],
    )
    def test_money_may_not_import_any_other_calc_package(self, source):
        assert find_violations(source, "money", MONEY), source

    def test_money_may_not_import_the_calc_root(self):
        assert find_violations("import finance.calc", "money", MONEY)

    @pytest.mark.parametrize(
        "source",
        [
            "import decimal",
            "from decimal import Decimal",
            "from __future__ import annotations",
            "import re, enum, dataclasses",
            "from . import errors",
            "from .errors import MoneyError",
            "from .rounding import RoundingMode",
            "import finance.calc.money.errors",
            "from finance.calc.money import rounding",
            "from finance.calc.money.rounding import RoundingMode",
        ],
    )
    def test_allowed_forms_pass_for_money(self, source):
        assert find_violations(source, "money", MONEY) == [], source

    def test_a_higher_package_may_use_a_lower_one_but_not_the_reverse(self):
        pkg = ["finance", "calc", "errors"]
        assert find_violations("from ..money import rounding", "errors", pkg) == []
        assert find_violations("from finance.calc.money import x", "errors", pkg) == []
        # errors may not reach a sibling that is not in its row
        assert find_violations("from ..corridor import x", "errors", pkg)
        # money may not reach errors, though errors may reach money
        assert find_violations("from ..errors import x", "money", MONEY)

    def test_pydantic_is_allowed_above_money_only(self):
        assert find_violations("import pydantic", "errors", ["finance", "calc", "errors"]) == []
        assert find_violations("import pydantic", "money", MONEY)

    def test_api_third_party_policy_is_undecided_and_fails_loudly(self):
        assert find_violations("import fastapi", "api", ["finance", "calc", "api"])

    def test_calc_init_must_not_import_anything(self):
        assert find_violations("import decimal", None, ["finance", "calc"])
        assert find_violations("from . import money", None, ["finance", "calc"])
        assert find_violations('"""docstring only."""', None, ["finance", "calc"]) == []

    def test_imports_hidden_inside_functions_and_try_blocks_are_found(self):
        source = "def f():\n    import pydantic\n\ntry:\n    import fastapi\nexcept ImportError:\n    pass\n"
        assert len(find_violations(source, "money", MONEY)) == 2

    def test_violation_messages_carry_the_line_number(self):
        problems = find_violations("import decimal\nimport pydantic\n", "money", MONEY)
        assert problems and problems[0].startswith("line 2:")


# -------------------------------------------------------- the real project
class TestRealProject:
    def test_calc_directory_exists(self):
        assert CALC_DIR.is_dir()
        assert (CALC_DIR / "__init__.py").is_file()

    def test_money_package_exists_and_is_scanned(self):
        files = [p for pkg, p in _calc_files() if pkg == "money"]
        # __init__ + errors, context, rounding, grammar, currency
        assert len(files) >= 6, [p.name for p in files]

    def test_every_calc_package_has_an_init_and_a_row_in_the_table(self):
        for pkg in _calc_packages():
            assert (pkg / "__init__.py").is_file(), f"{pkg.name} has no __init__.py"
            assert pkg.name in DEPENDS, (
                f"calc/{pkg.name} has no row in the E1 table: add it (after "
                f"re-verifying against E1) before adding code"
            )

    def test_calc_init_has_no_imports(self):
        path = CALC_DIR / "__init__.py"
        problems = find_violations(path.read_text(encoding="utf-8"), None, ["finance", "calc"])
        assert problems == []

    @pytest.mark.parametrize(
        "pkg,path",
        _calc_files(),
        ids=[_rel(p) for _, p in _calc_files()],
    )
    def test_module_respects_its_dependency_row(self, pkg, path):
        if pkg not in DEPENDS:
            pytest.fail(f"calc/{pkg} has no row in the E1 table")
        source = path.read_text(encoding="utf-8")
        problems = find_violations(source, pkg, _package_parts(path))
        assert problems == [], f"{_rel(path)}: {problems}"

    def test_money_uses_the_standard_library_and_its_own_package_only(self):
        """The plain-language form of E1 for money, checked independently of
        ``find_violations``: every import is stdlib or a relative import inside
        the money package."""
        offenders = []
        for pkg, path in _calc_files():
            if pkg != "money":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0] not in STDLIB:
                            offenders.append((path.name, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.level == 0:
                        if (node.module or "").split(".")[0] not in STDLIB:
                            offenders.append((path.name, node.module))
                    elif node.level != 1:
                        offenders.append((path.name, "." * node.level + (node.module or "")))
        assert offenders == []

    def test_no_calc_module_is_named_like_a_legacy_module(self):
        """engine, schemas and routes are reserved for the untouched legacy
        files, and a clash would also break test collection."""
        clashes = [
            _rel(p)
            for p in CALC_DIR.rglob("*.py")
            if "__pycache__" not in p.parts and p.stem in FORBIDDEN_MODULE_NAMES
        ]
        assert clashes == []

    def test_no_calc_package_is_named_like_a_legacy_module(self):
        clashes = [p.name for p in _calc_packages() if p.name in FORBIDDEN_MODULE_NAMES]
        assert clashes == []

    def test_nothing_under_calc_imports_legacy_code(self):
        """Independent of the table: no file under calc/ may import
        finance.engine, finance.schemas, finance.routes or finance itself."""
        legacy = {"engine", "schemas", "routes"}
        offenders = []
        for path in CALC_DIR.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for lineno, dotted in _imported_modules(tree, _package_parts(path)):
                parts = dotted.split(".")
                if parts[0] == "finance" and not (len(parts) >= 2 and parts[1] == "calc"):
                    offenders.append(f"{_rel(path)}:{lineno}: {dotted}")
                if parts[:2] == ["finance", "calc"] and len(parts) >= 3 and parts[2] in legacy:
                    offenders.append(f"{_rel(path)}:{lineno}: {dotted}")
        assert offenders == []
