"""M1 guard tests.

Every behaviour test runs against an isolated copy of a fake project tree in
pytest's tmp_path.  Only `test_real_project_is_clean` touches the real project,
and it only reads.
"""
import errno
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import check_m1_guards as g  # noqa: E402

REAL_ROOT = g.ROOT


# ------------------------------------------------------------- fixtures
def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture
def proj(tmp_path):
    """Fake project with every protected + guard file and a sealed baseline."""
    for rel in g.LEGACY + g.GUARDS:
        _write(tmp_path, rel, f"# fake {rel}\n")
    assert g.init_baseline(tmp_path, "fixture baseline") == []
    return tmp_path


def _calc(root, text, name="money.py"):
    _write(root, "finance/calc/" + name, text)
    return g.boundary_problems(root)


def _manifest(root):
    return json.loads((root / g.MANIFEST_REL).read_text(encoding="utf-8"))


def _put_manifest(root, data, reseal=True):
    if reseal:
        data["seal"] = g._seal(data)
    (root / g.MANIFEST_REL).write_text(json.dumps(data), encoding="utf-8")


# ------------------------------------------------- real project (read-only)
def _real_manifest_state():
    p = REAL_ROOT / g.MANIFEST_REL
    return p.read_bytes() if p.is_file() else None


def test_real_project_is_clean():
    """Pre-migration there is no active manifest: skip.  Once one exists (even a
    corrupt one - only a MISSING manifest skips) the full check must pass."""
    if not os.path.lexists(REAL_ROOT / g.MANIFEST_REL):
        pytest.skip("no active manifest yet (pre-migration); run the migration first")
    before = _real_manifest_state()
    assert g.check(REAL_ROOT) == []
    assert _real_manifest_state() == before


def test_real_project_legacy_files_exist():
    """Runs in every state, read-only: the files the baseline will protect exist."""
    assert g._missing(REAL_ROOT, g.LEGACY + g.GUARDS) == []


def test_missing_manifest_is_reported_not_skipped_by_the_guard(tmp_path):
    """Only the real-project TEST skips; the guard itself still reports it."""
    assert g.main([], tmp_path) == 1
    assert not (tmp_path / g.MANIFEST_REL).exists()


def test_fixture_is_not_the_real_project(proj):
    assert proj != REAL_ROOT and REAL_ROOT not in proj.parents


# ------------------------------------------------------ protected files
def test_clean_fixture_passes(proj):
    assert g.check(proj) == []


@pytest.mark.parametrize("rel", g.LEGACY)
def test_modified_legacy_file_detected(proj, rel):
    (proj / rel).write_text("tampered\n", encoding="utf-8")
    assert f"changed protected file: {rel}" in g.protected_problems(proj)


@pytest.mark.parametrize("rel", g.LEGACY)
def test_missing_legacy_file_detected(proj, rel):
    (proj / rel).unlink()
    assert f"missing protected file: {rel}" in g.protected_problems(proj)


@pytest.mark.parametrize("rel", g.GUARDS)
def test_modified_or_missing_guard_file_detected(proj, rel):
    (proj / rel).write_text("tampered\n", encoding="utf-8")
    assert f"changed guards file: {rel}" in g.protected_problems(proj)
    (proj / rel).unlink()
    assert f"missing guards file: {rel}" in g.protected_problems(proj)


# ------------------------------------------------------ manifest checks
def test_manifest_missing(tmp_path):
    errs = g.protected_problems(tmp_path)
    assert len(errs) == 1 and "file not found" in errs[0]


def test_manifest_malformed_json(proj):
    (proj / g.MANIFEST_REL).write_text("{not json", encoding="utf-8")
    assert "malformed JSON" in g.protected_problems(proj)[0]


def test_manifest_not_an_object(proj):
    (proj / g.MANIFEST_REL).write_text("[1, 2]", encoding="utf-8")
    assert "must be a JSON object" in g.protected_problems(proj)[0]


def test_manifest_missing_entry(proj):
    d = _manifest(proj)
    del d["protected"]["finance/engine.py"]
    _put_manifest(proj, d)
    assert any("missing entry 'finance/engine.py'" in e for e in g.protected_problems(proj))


def test_manifest_missing_section(proj):
    d = _manifest(proj)
    del d["guards"]
    _put_manifest(proj, d)
    assert any("section 'guards'" in e for e in g.protected_problems(proj))


def test_manifest_unexpected_entry(proj):
    d = _manifest(proj)
    d["protected"]["finance/extra.py"] = "0" * 64
    _put_manifest(proj, d)
    assert any("unexpected entry" in e for e in g.protected_problems(proj))


@pytest.mark.parametrize("bad", ["xyz", "A" * 64, "a" * 63, 123, None])
def test_manifest_invalid_hash(proj, bad):
    d = _manifest(proj)
    d["protected"]["finance/engine.py"] = bad
    _put_manifest(proj, d)
    assert any("invalid hash" in e for e in g.protected_problems(proj))


def test_manifest_hand_edit_breaks_seal(proj):
    d = _manifest(proj)
    d["protected"]["finance/engine.py"] = "0" * 64  # valid shape, no reseal
    _put_manifest(proj, d, reseal=False)
    assert any("seal mismatch" in e for e in g.protected_problems(proj))


def test_manifest_bad_version_and_history(proj):
    d = _manifest(proj)
    d["version"] = 99
    d["history"] = []
    _put_manifest(proj, d)
    errs = " ".join(g.protected_problems(proj))
    assert "unsupported version" in errs and "history" in errs


# ----------------------------------------------- direct / relative imports
@pytest.mark.parametrize("src", [
    "import finance.engine",
    "import finance.engine as e",
    "import finance.schemas",
    "import finance.routes.x",
    "from finance.engine import compute",
    "from finance import engine",
    "from finance import schemas, routes",
    "from finance.routes import router",
])
def test_direct_forbidden_import_detected(proj, src):
    probs = _calc(proj, src + "\n")
    assert probs and probs[0].startswith("finance/calc/money.py: line 1")


@pytest.mark.parametrize("src", [
    "from .. import engine",
    "from ..engine import compute",
    "from ..schemas import X",
    "from .. import routes",
])
def test_relative_forbidden_import_detected(proj, src):
    assert _calc(proj, src + "\n")


def test_relative_import_in_nested_package(proj):
    assert _calc(proj, "from ... import engine\n", name="sub/deep.py")  # finance.calc.sub -> finance
    assert _calc(proj, "from .. import engine\n", name="sub/deep.py") == []  # -> finance.calc


def test_allowed_imports_not_flagged(proj):
    src = ("import decimal\nimport importlib\nfrom decimal import Decimal\n"
           "from . import rounding\nfrom .rounding import x\nfrom finance import calc\n"
           "from finance.calc import money\nimport finance.calc.money\n"
           "importlib.import_module('decimal')\nm = __import__('json')\n")
    assert _calc(proj, src) == []


# --------------------------------------------------------- dynamic imports
@pytest.mark.parametrize("src", [
    "import importlib\nimportlib.import_module('finance.engine')",
    "import importlib as il\nil.import_module('finance.schemas')",
    "from importlib import import_module\nimport_module('finance.routes')",
    "from importlib import import_module as load\nload('finance.engine')",
    "import importlib\nimportlib.import_module(name='finance.engine')",
    "import importlib\nimportlib.import_module('.engine', 'finance')",
    "import importlib\nimportlib.import_module('..engine', package='finance.calc')",
    "x = __import__('finance.engine')",
    "x = __import__('finance', fromlist=['engine'])",
    "import importlib.util\nimportlib.util.find_spec('finance.engine')",
    "import runpy\nrunpy.run_module('finance.routes')",
])
def test_dynamic_forbidden_import_detected(proj, src):
    probs = _calc(proj, src + "\n")
    assert any("dynamically imports" in p for p in probs), probs


@pytest.mark.parametrize("src", [
    "import importlib\nimportlib.import_module(name)",
    "import importlib\nimportlib.import_module('finance.' + 'engine')",
    "import importlib\nimportlib.import_module(f'finance.{n}')",
    "import importlib\nimportlib.import_module('.engine')",
    "x = __import__(name)",
    "f = __import__",
    "import builtins\nf = builtins.__import__",
    "exec('import finance.engine')",
    "eval(code)",
])
def test_unprovable_dynamic_import_fails_closed(proj, src):
    assert _calc(proj, src + "\n"), src


def test_unparseable_calc_file_is_a_problem(proj):
    probs = _calc(proj, "def (:\n")
    assert probs and "cannot parse" in probs[0]


def test_no_calc_directory_is_clean(proj):
    assert g.boundary_problems(proj) == []


# ----------------------------------------------- baseline protection (CLI)
def test_record_flag_is_rejected_and_changes_nothing(proj, capsys):
    before = (proj / g.MANIFEST_REL).read_bytes()
    (proj / "finance/engine.py").write_text("tampered\n", encoding="utf-8")
    assert g.main(["--record"], proj) == 2
    assert (proj / g.MANIFEST_REL).read_bytes() == before
    assert "removed" in capsys.readouterr().out


def test_init_refuses_when_manifest_exists(proj):
    before = (proj / g.MANIFEST_REL).read_bytes()
    assert g.main(["--init", "--reason", "again"], proj) == 2
    assert (proj / g.MANIFEST_REL).read_bytes() == before


def test_init_refuses_over_a_corrupt_manifest(proj):
    (proj / g.MANIFEST_REL).write_text("garbage", encoding="utf-8")
    assert g.init_baseline(proj, "x")
    assert (proj / g.MANIFEST_REL).read_text() == "garbage"


def test_init_requires_reason_and_files(tmp_path):
    assert g.init_baseline(tmp_path, "") == ["--reason is required"]
    assert "missing" in g.init_baseline(tmp_path, "ok")[0]
    assert not (tmp_path / g.MANIFEST_REL).exists()


def test_reset_requires_confirm_token_and_reason(proj):
    before = (proj / g.MANIFEST_REL).read_bytes()
    assert g.main(["--reset-baseline", "--reason", "r"], proj) == 2
    assert g.main(["--reset-baseline", "--confirm", "yes", "--reason", "r"], proj) == 2
    assert g.main(["--reset-baseline", "--confirm", g.CONFIRM_TOKEN], proj) == 2
    assert (proj / g.MANIFEST_REL).read_bytes() == before


@pytest.mark.parametrize("corrupt", ["{bad", "[]"])
def test_reset_refuses_invalid_existing_baseline(proj, corrupt):
    (proj / g.MANIFEST_REL).write_text(corrupt, encoding="utf-8")
    errs = g.reset_baseline(proj, "r", g.CONFIRM_TOKEN)
    assert "not valid" in errs[0]
    assert (proj / g.MANIFEST_REL).read_text() == corrupt


def test_reset_refuses_when_seal_broken(proj):
    d = _manifest(proj)
    d["guards"]["tools/check_m1_guards.py"] = "0" * 64
    _put_manifest(proj, d, reseal=False)
    assert "not valid" in g.reset_baseline(proj, "r", g.CONFIRM_TOKEN)[0]


def test_reset_refuses_when_legacy_changed(proj):
    before = (proj / g.MANIFEST_REL).read_bytes()
    (proj / "finance/schemas.py").write_text("tampered\n", encoding="utf-8")
    errs = g.reset_baseline(proj, "r", g.CONFIRM_TOKEN)
    assert "may not be re-recorded" in errs[0]
    assert (proj / g.MANIFEST_REL).read_bytes() == before


def test_reset_refuses_when_boundary_dirty(proj):
    _calc(proj, "import finance.engine\n")
    assert "boundary" in g.reset_baseline(proj, "r", g.CONFIRM_TOKEN)[0]


def test_reset_rerecords_guards_only_and_logs_history(proj):
    old = _manifest(proj)
    (proj / "tools/check_m1_guards.py").write_text("# deliberate edit\n", encoding="utf-8")
    assert "changed guards file: tools/check_m1_guards.py" in g.check(proj)
    assert g.main(["--reset-baseline", "--confirm", g.CONFIRM_TOKEN,
                   "--reason", "improve scanner"], proj) == 0
    new = _manifest(proj)
    assert g.check(proj) == []
    assert new["protected"] == old["protected"]
    assert new["guards"]["tools/check_m1_guards.py"] != old["guards"]["tools/check_m1_guards.py"]
    assert [h["action"] for h in new["history"]] == ["init", "reset-guards"]
    assert new["history"][1]["reason"] == "improve scanner"
    assert new["history"][1]["previous_seal"] == old["seal"]


def test_plain_cli_run_reports_problems(proj, capsys):
    assert g.main([], proj) == 0
    (proj / "finance/engine.py").unlink()
    assert g.main([], proj) == 1
    assert "missing protected file: finance/engine.py" in capsys.readouterr().out


# ------------------------------------------- migration from the old manifest
@pytest.fixture
def mig(tmp_path):
    """Fake project WITHOUT an active manifest, plus an old flat manifest that
    sits outside tools/ (like the trash copy).  Returns (root, source_path)."""
    root = tmp_path / "backend"
    for rel in g.LEGACY + g.GUARDS:
        _write(root, rel, f"# fake {rel}\n")
    src = tmp_path / "old" / "protected_manifest.json"
    src.parent.mkdir()
    src.write_text(json.dumps({r: g.digest(root, r) for r in g.LEGACY}, indent=2),
                   encoding="utf-8")
    return root, src


def _src(src):
    return json.loads(src.read_text(encoding="utf-8"))


def _put_src(src, data):
    src.write_text(json.dumps(data), encoding="utf-8")


def _legacy_bytes(root):
    return {r: (root / r).read_bytes() for r in g.LEGACY}


def test_migration_success(mig):
    root, src = mig
    src_before = src.read_bytes()
    legacy_before = _legacy_bytes(root)
    assert g.migrate_legacy(root, src, "  move to sealed v1  ") == []
    data, errors = g.load_manifest(root)
    assert errors == [] and data["version"] == 1
    assert g.check(root) == []
    assert data["guards"] == {r: g.digest(root, r) for r in g.GUARDS}
    h = data["history"]
    assert len(h) == 1 and h[0]["action"] == "migrate-legacy"
    assert h[0]["reason"] == "move to sealed v1"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", h[0]["utc"])
    assert h[0]["source_manifest"] == str(src).replace("\\", "/")
    assert h[0]["source_sha256"] == hashlib.sha256(src_before).hexdigest()
    assert src.read_bytes() == src_before            # source only read
    assert _legacy_bytes(root) == legacy_before      # legacy files untouched
    assert not (root / (g.MANIFEST_REL + ".tmp")).exists()


def test_migration_preserves_original_legacy_hashes_verbatim(mig):
    root, src = mig
    original = _src(src)
    assert g.migrate_legacy(root, src, "r") == []
    protected = _manifest(root)["protected"]
    assert protected == original
    # JSON key order is not semantic (the manifest is written with
    # sort_keys=True), so compare the key SET and each value, never the order.
    assert set(protected) == set(g.LEGACY) and len(protected) == len(g.LEGACY)
    for rel in g.LEGACY:
        assert protected[rel] == original[rel]


def test_migration_via_cli(mig, capsys):
    root, src = mig
    assert g.main(["--from-legacy-manifest", str(src), "--reason", "cli"], root) == 0
    assert "sealed v1" in capsys.readouterr().out
    assert g.main([], root) == 0


@pytest.mark.parametrize("rel", g.LEGACY)
def test_migration_refuses_legacy_hash_mismatch(mig, rel):
    root, src = mig
    (root / rel).write_text("tampered\n", encoding="utf-8")
    errs = g.migrate_legacy(root, src, "r")
    assert f"mismatch: {rel} differs from the legacy manifest" in errs
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_mismatch_is_not_papered_over(mig):
    """The source hash is what counts: a wrong source hash must refuse, never be
    replaced by the freshly computed one."""
    root, src = mig
    d = _src(src)
    d["finance/engine.py"] = "0" * 64
    _put_src(src, d)
    assert any("finance/engine.py" in e for e in g.migrate_legacy(root, src, "r"))
    assert not (root / g.MANIFEST_REL).exists()


@pytest.mark.parametrize("rel", g.LEGACY + g.GUARDS)
def test_migration_refuses_missing_file(mig, rel):
    root, src = mig
    (root / rel).unlink()
    errs = g.migrate_legacy(root, src, "r")
    assert "missing" in errs[0] and rel in errs[0]
    assert not (root / g.MANIFEST_REL).exists()


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '"text"', ""])
def test_migration_refuses_malformed_legacy_manifest(mig, content):
    root, src = mig
    src.write_text(content, encoding="utf-8")
    errs = g.migrate_legacy(root, src, "r")
    assert "source manifest is not valid" in errs[0]
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_refuses_missing_source_file(mig):
    root, src = mig
    errs = g.migrate_legacy(root, src.with_name("nope.json"), "r")
    assert "file not found" in " ".join(errs)
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_refuses_missing_manifest_entry(mig):
    root, src = mig
    d = _src(src)
    del d["tests/test_api.py"]
    _put_src(src, d)
    errs = g.migrate_legacy(root, src, "r")
    assert "legacy manifest: missing entry 'tests/test_api.py'" in errs
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_refuses_unexpected_entry(mig):
    root, src = mig
    d = _src(src)
    d["finance/extra.py"] = "0" * 64
    _put_src(src, d)
    assert "legacy manifest: unexpected entry 'finance/extra.py'" in g.migrate_legacy(root, src, "r")


@pytest.mark.parametrize("bad", ["xyz", "A" * 64, "a" * 63, "a" * 65, 123, None])
def test_migration_refuses_invalid_hash(mig, bad):
    root, src = mig
    d = _src(src)
    d["finance/schemas.py"] = bad
    _put_src(src, d)
    errs = g.migrate_legacy(root, src, "r")
    assert any("invalid hash for 'finance/schemas.py'" in e for e in errs)
    assert not (root / g.MANIFEST_REL).exists()


@pytest.mark.parametrize("existing", [None, "garbage", "{}"])
def test_migration_never_overwrites_active_manifest(mig, existing):
    root, src = mig
    if existing is None:  # a valid, sealed manifest
        assert g.init_baseline(root, "first") == []
    else:                 # an invalid one
        (root / g.MANIFEST_REL).write_text(existing, encoding="utf-8")
    before = (root / g.MANIFEST_REL).read_bytes()
    errs = g.migrate_legacy(root, src, "r")
    assert "active manifest already exists" in errs[0]
    assert (root / g.MANIFEST_REL).read_bytes() == before


def test_migration_source_may_not_be_the_active_manifest_path(mig):
    root, _ = mig
    # an old-format file sitting at the active path counts as "exists" first
    (root / g.MANIFEST_REL).write_text("{}", encoding="utf-8")
    assert g.migrate_legacy(root, root / g.MANIFEST_REL, "r")
    assert (root / g.MANIFEST_REL).read_text() == "{}"


def test_migration_requires_reason_and_explicit_path(mig, capsys):
    root, src = mig
    assert g.migrate_legacy(root, src, "") == ["refused: --reason is required"]
    assert g.migrate_legacy(root, src, "   ") == ["refused: --reason is required"]
    assert "explicit file path" in g.migrate_legacy(root, None, "r")[0]
    assert g.main(["--from-legacy-manifest", "--reason", "r"], root) == 2
    assert g.main(["--from-legacy-manifest", str(src)], root) == 2
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_does_not_search_trash_or_restore(mig):
    root, src = mig
    trash = root.parent / ".quorx" / "trash" / "x" / "backend" / "tools"
    trash.mkdir(parents=True)
    (trash / "protected_manifest.json").write_bytes(src.read_bytes())
    assert g.main(["--from-legacy-manifest", "--reason", "r"], root) == 2  # no path given
    assert g.main(["--init"], root) == 2                                    # no reason given
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_cannot_be_combined_with_other_baseline_flags(mig):
    root, src = mig
    for flag in (["--init"], ["--reset-baseline"]):
        assert g.main(["--from-legacy-manifest", str(src), "--reason", "r"] + flag, root) == 2
    assert not (root / g.MANIFEST_REL).exists()


def test_migration_refuses_dirty_import_boundary(mig):
    root, src = mig
    _calc(root, "import finance.engine\n")
    assert "boundary" in g.migrate_legacy(root, src, "r")[0]
    assert not (root / g.MANIFEST_REL).exists()


def test_migrated_manifest_works_with_reset_baseline(mig):
    root, src = mig
    assert g.migrate_legacy(root, src, "r") == []
    (root / "tools/check_m1_guards.py").write_text("# edit\n", encoding="utf-8")
    assert g.reset_baseline(root, "after migration", g.CONFIRM_TOKEN) == []
    assert [h["action"] for h in _manifest(root)["history"]] == ["migrate-legacy", "reset-guards"]


# --------------------------------- atomic, no-overwrite manifest creation
def _tools_listing(root):
    return sorted(p.name for p in (root / "tools").iterdir())


def _race_link(monkeypatch, content=b"someone else's manifest"):
    """Make another 'process' create the active manifest at the last moment:
    just before the real os.link publishes our temp file."""
    real = os.link

    def racing(src, dst, *a, **k):
        Path(dst).write_bytes(content)
        return real(src, dst, *a, **k)  # real call now raises FileExistsError

    monkeypatch.setattr(g.os, "link", racing)
    return content


def test_init_race_at_final_step_keeps_existing_manifest(tmp_path, monkeypatch):
    for rel in g.LEGACY + g.GUARDS:
        _write(tmp_path, rel, f"# fake {rel}\n")
    other = _race_link(monkeypatch)
    errs = g.init_baseline(tmp_path, "r")
    assert "created by someone else" in errs[0]
    assert (tmp_path / g.MANIFEST_REL).read_bytes() == other
    assert not [n for n in _tools_listing(tmp_path) if n.endswith(".tmp")]


def test_migration_race_at_final_step_keeps_existing_manifest(mig, monkeypatch):
    root, src = mig
    other = _race_link(monkeypatch)
    errs = g.migrate_legacy(root, src, "r")
    assert "created by someone else" in errs[0]
    assert (root / g.MANIFEST_REL).read_bytes() == other
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]
    assert src.exists()


def test_write_manifest_never_overwrites_and_cleans_up(proj):
    before = (proj / g.MANIFEST_REL).read_bytes()
    with pytest.raises(g.ManifestExistsError):
        g._write_manifest(proj, {"version": 1})
    assert (proj / g.MANIFEST_REL).read_bytes() == before
    assert not [n for n in _tools_listing(proj) if n.endswith(".tmp")]


def test_successful_creation_leaves_no_temp_files(mig):
    root, src = mig
    assert g.migrate_legacy(root, src, "r") == []
    names = _tools_listing(root)
    assert "protected_manifest.json" in names
    assert not [n for n in names if n.endswith(".tmp")]


def _no_links(monkeypatch):
    def nolink(*a, **k):
        raise OSError(errno.ENOTSUP, "hard links not supported")
    monkeypatch.setattr(g.os, "link", nolink)


def test_fallback_without_hard_links_creates_valid_manifest(mig, monkeypatch):
    root, src = mig
    _no_links(monkeypatch)
    assert g.migrate_legacy(root, src, "r") == []
    assert g.check(root) == []
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]


@pytest.mark.parametrize("windows", [True, False])
def test_fallback_without_hard_links_never_overwrites(mig, monkeypatch, windows):
    root, src = mig
    real_exclusive = g._create_exclusive
    marker = b"created meanwhile"

    def racing_excl(path, text):
        Path(path).write_bytes(marker)
        return real_exclusive(path, text)  # O_EXCL now raises FileExistsError

    def racing_rename(a, b):
        Path(b).write_bytes(marker)
        raise FileExistsError(errno.EEXIST, "exists", str(b))  # Windows semantics

    _no_links(monkeypatch)
    monkeypatch.setattr(g, "_IS_WINDOWS", windows)
    monkeypatch.setattr(g, "_create_exclusive", racing_excl)
    monkeypatch.setattr(g.os, "rename", racing_rename)
    errs = g.migrate_legacy(root, src, "r")
    assert "created by someone else" in errs[0]
    assert (root / g.MANIFEST_REL).read_bytes() == marker
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]


@pytest.mark.parametrize("windows", [True, False])
def test_unexpected_write_failure_cleans_up_temp_file(mig, monkeypatch, windows):
    root, src = mig

    def boom(*a, **k):
        raise PermissionError("denied")

    _no_links(monkeypatch)
    monkeypatch.setattr(g, "_IS_WINDOWS", windows)
    monkeypatch.setattr(g, "_create_exclusive", boom)
    monkeypatch.setattr(g.os, "rename", boom)
    with pytest.raises(PermissionError):
        g.migrate_legacy(root, src, "r")
    assert not (root / g.MANIFEST_REL).exists()
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]


def test_reset_baseline_still_replaces_the_manifest(proj):
    (proj / "tools/check_m1_guards.py").write_text("# edit\n", encoding="utf-8")
    assert g.reset_baseline(proj, "r", g.CONFIRM_TOKEN) == []
    assert g.check(proj) == []
    assert not [n for n in _tools_listing(proj) if n.endswith(".tmp")]


# ------------------------------------------------ publication guarantees
def test_link_publication_shows_only_a_complete_manifest(mig, monkeypatch):
    """At the moment of publication the destination does not exist yet and the
    temp file already holds the COMPLETE sealed content."""
    root, src = mig
    real_link = g.os.link
    seen = {}

    def spy(tmp, dst, *a, **k):
        seen["dst_existed"] = Path(dst).exists()
        data = json.loads(Path(tmp).read_text(encoding="utf-8"))
        seen["complete"] = data.get("seal") == g._seal(data)
        return real_link(tmp, dst, *a, **k)

    monkeypatch.setattr(g.os, "link", spy)
    assert g.migrate_legacy(root, src, "r") == []
    assert seen == {"dst_existed": False, "complete": True}
    assert g.check(root) == []


def test_truncated_manifest_is_never_valid_and_blocks_creation(mig):
    root, src = mig
    full = json.dumps({"version": 1, "protected": {}, "guards": {}})
    (root / g.MANIFEST_REL).write_text(full[: len(full) // 2], encoding="utf-8")
    data, errors = g.load_manifest(root)
    assert data is None and errors
    before = (root / g.MANIFEST_REL).read_bytes()
    assert g.init_baseline(root, "r")
    assert g.migrate_legacy(root, src, "r")
    assert (root / g.MANIFEST_REL).read_bytes() == before


def test_exclusive_fallback_removes_partial_file_on_write_failure(tmp_path, monkeypatch):
    target = tmp_path / "m.json"

    def bad_fsync(fd):
        raise OSError(errno.EIO, "io error")

    monkeypatch.setattr(g.os, "fsync", bad_fsync)
    with pytest.raises(OSError):
        g._create_exclusive(target, "{}\n")
    assert not target.exists()


def test_exclusive_fallback_never_overwrites_existing_file(tmp_path):
    target = tmp_path / "m.json"
    target.write_bytes(b"keep me")
    with pytest.raises(FileExistsError):
        g._create_exclusive(target, "{}\n")
    assert target.read_bytes() == b"keep me"


@pytest.mark.parametrize("windows", [True, False])
@pytest.mark.parametrize("err", [
    PermissionError(errno.EACCES, "denied"),
    OSError(errno.EIO, "io error"),
    OSError(errno.ENOSPC, "disk full"),
])
def test_unrelated_link_errors_propagate_without_fallback(mig, monkeypatch, windows, err):
    root, src = mig
    called = []

    def bad_link(*a, **k):
        raise err

    def fallback(*a, **k):
        called.append(1)
        raise AssertionError("fallback must not run for unrelated errors")

    monkeypatch.setattr(g.os, "link", bad_link)
    monkeypatch.setattr(g, "_IS_WINDOWS", windows)
    monkeypatch.setattr(g, "_create_exclusive", fallback)
    monkeypatch.setattr(g.os, "rename", fallback)
    with pytest.raises(OSError) as info:
        g.migrate_legacy(root, src, "r")
    assert info.value is err
    assert not called
    assert not (root / g.MANIFEST_REL).exists()
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]


def test_link_unsupported_classification():
    assert g._link_unsupported(OSError(errno.ENOTSUP, "x"))
    assert g._link_unsupported(OSError(errno.EPERM, "x"))
    assert g._link_unsupported(OSError(errno.ENOSYS, "x"))
    assert not g._link_unsupported(OSError(errno.EIO, "x"))
    assert not g._link_unsupported(OSError(errno.ENOSPC, "x"))
    assert not g._link_unsupported(FileExistsError(errno.EEXIST, "x"))
    win = OSError(errno.EINVAL, "x", None, 50)
    if hasattr(win, "winerror"):  # Windows only: winerror decides
        assert g._link_unsupported(win)
        assert not g._link_unsupported(OSError(errno.EINVAL, "x", None, 5))


@pytest.mark.skipif(os.name != "nt", reason="real os.rename no-replace is Windows semantics")
def test_real_windows_rename_fallback_creates_and_never_overwrites(mig, monkeypatch):
    root, src = mig
    _no_links(monkeypatch)
    assert g.migrate_legacy(root, src, "r") == []
    assert g.check(root) == []
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]
    before = (root / g.MANIFEST_REL).read_bytes()
    assert g.migrate_legacy(root, src, "r")  # refused: manifest exists
    assert (root / g.MANIFEST_REL).read_bytes() == before
    with pytest.raises(g.ManifestExistsError):
        g._write_manifest(root, {"version": 1})
    assert (root / g.MANIFEST_REL).read_bytes() == before
    assert not [n for n in _tools_listing(root) if n.endswith(".tmp")]
