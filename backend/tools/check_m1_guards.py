"""M1 guards.  Run from backend/:

    python tools/check_m1_guards.py                       check (exit 0 = clean)
    python tools/check_m1_guards.py --init --reason TEXT  create the FIRST baseline
    python tools/check_m1_guards.py --reset-baseline --confirm RESET-M1-BASELINE --reason TEXT
    python tools/check_m1_guards.py --from-legacy-manifest PATH --reason TEXT
                                                          one-time migration

What is guarded
  * LEGACY files (engine, schemas, routes, existing tests): must equal the
    SHA-256 recorded in tools/protected_manifest.json.  backend/ is untracked in
    git, so git diff cannot protect them.
  * GUARD files (this script, its test file): same check, but they MAY be
    changed on purpose through --reset-baseline.
  * The manifest itself carries a "seal" (SHA-256 over its own content), so an
    accidental or partial edit of the manifest is detected.
  * Import boundary: nothing under finance/calc/ may import finance.engine,
    finance.schemas or finance.routes.

Manifest creation (--init, migration) never replaces an existing file.  The
content is first written completely to a unique temp file, then PUBLISHED:
  1. os.link(tmp, manifest)  - atomic and no-replace on NTFS and POSIX; readers
     see no manifest or the complete one.  Used everywhere first.
  2. Only if the link call fails with an error that really means "hard links
     unsupported here" (see _link_unsupported) the fallback is used:
       Windows: os.rename(tmp, manifest) - Windows refuses to rename onto an
                existing file, so it is atomic and no-replace as well.
       POSIX:   O_EXCL create + write.  This is NOT atomic: for a moment the
                manifest can exist incomplete.  It never replaces a file, a
                failed write removes the partial file, and a partial manifest is
                never valid (it fails JSON/seal validation, so the guard reports
                it and --init/migration refuse to touch it).  Only on a POSIX
                file system without hard links is full atomicity not available.
  Any other OSError (permissions, disk full, I/O error...) is propagated, never
  mistaken for "unsupported".  The temp file is always removed.  Only
  --reset-baseline replaces a manifest (os.replace, after validating it).

Baseline changes (there is deliberately no bare --record):
  --init            only when NO manifest exists.
  --reset-baseline  only when the existing manifest is valid and sealed, every
                    LEGACY file still matches it, the import boundary is clean,
                    --confirm RESET-M1-BASELINE is given and --reason is given.
                    It re-records the GUARD hashes only, and appends an entry
                    (reason, UTC time, previous seal) to the manifest history.
                    Legacy hashes can never be re-recorded by this tool.  If
                    legacy files must truly change, a person must delete the
                    manifest on purpose and run --init (that is the audit trail:
                    the old manifest is gone and the decision is explicit).

One-time migration from the old flat manifest (--from-legacy-manifest PATH)
  The first guard version wrote a flat {path: sha256} manifest with no version,
  seal or history.  This command turns it into a sealed v1 manifest, and only
  if ALL of these hold (otherwise nothing is written):
    * no active manifest exists (a valid, corrupt or dangling one all refuse);
    * PATH is an explicit file you name; trash and other folders are never
      searched, and PATH may not be the active manifest itself;
    * the source is a JSON object with EXACTLY the six LEGACY paths, each a
      64-character lowercase hex SHA-256;
    * all LEGACY and GUARD files exist, and every LEGACY file on disk equals
      its hash in the source;
    * the import boundary is clean and --reason is given.
  The six legacy hashes are copied from the source verbatim (they are never
  recomputed); only the two GUARD hashes are computed from the current files.
  The history entry records action 'migrate-legacy', the reason, UTC time, the
  source path as given and the SHA-256 of the source file.  The source file is
  only read, never modified, moved or deleted.

Import-boundary detection (AST based, no code is executed)
  Detected: `import finance.engine`, `from finance import engine`,
  `from finance.engine import x`, relative forms (`from .. import engine`,
  `from ..engine import x`), importlib.import_module(...) / import_module(...)
  (also via any alias of the module or `from importlib import import_module as
  f`), __import__(...) including `fromlist`, importlib.util.find_spec(...) and
  runpy.run_module(...), when the module name is a string literal (relative
  names are resolved with a literal `package`).
  Fail-closed: a dynamic import whose name is NOT a literal, eval/exec/compile
  calls, and any bare reference to __import__ (aliasing it) are reported as
  problems, because they cannot be proven safe.
  NOT detected (limitations): names built at runtime and passed through
  getattr()/vars()/globals() lookups, sys.modules access, `import finance`
  followed by attribute access `finance.engine`, importing through a third
  module outside finance/calc/ that re-exports the legacy engine, code loaded
  from non-.py files, and anything a determined author hides on purpose.  The
  guard catches accidents and common patterns, it is not a security sandbox.
"""
import ast
import datetime
import errno
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_REL = "tools/protected_manifest.json"
MANIFEST_VERSION = 1
_IS_WINDOWS = os.name == "nt"
# errno / winerror values that mean "this file system cannot hard-link".
_NO_LINK_ERRNOS = {errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM}
_NO_LINK_WINERRORS = {1, 50, 120}  # INVALID_FUNCTION, NOT_SUPPORTED, CALL_NOT_IMPLEMENTED
CONFIRM_TOKEN = "RESET-M1-BASELINE"

LEGACY = [
    "finance/__init__.py",
    "finance/engine.py",
    "finance/schemas.py",
    "finance/routes.py",
    "tests/test_api.py",
    "tests/test_engine.py",
]
GUARDS = [
    "tools/check_m1_guards.py",
    "tests/calc/test_calc_guards.py",
]
FORBIDDEN = ("finance.engine", "finance.schemas", "finance.routes")

DYN_NAMES = {"import_module", "__import__", "find_spec", "run_module"}
CODE_EXEC = {"eval", "exec", "compile"}
_HEX64 = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------- hashing
def digest(root, rel):
    return hashlib.sha256((Path(root) / rel).read_bytes()).hexdigest()


def _seal(data):
    body = {k: v for k, v in data.items() if k != "seal"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------- manifest
def _validate_section(data, name, expected, errors):
    sec = data.get(name)
    if not isinstance(sec, dict):
        errors.append(f"manifest: section '{name}' missing or not an object")
        return
    for rel in expected:
        if rel not in sec:
            errors.append(f"manifest: missing entry '{rel}' in '{name}'")
        elif not isinstance(sec[rel], str) or not _HEX64.fullmatch(sec[rel]):
            errors.append(f"manifest: invalid hash for '{rel}' in '{name}' "
                          "(need 64 lowercase hex characters)")
    for rel in sec:
        if rel not in expected:
            errors.append(f"manifest: unexpected entry '{rel}' in '{name}'")


def load_manifest(root=ROOT):
    """Return (data, errors).  data is None whenever errors is non-empty."""
    path = Path(root) / MANIFEST_REL
    if not path.is_file():
        return None, [f"manifest: file not found: {MANIFEST_REL} "
                      "(create the first baseline with --init)"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:  # JSONDecodeError and bad encoding are ValueErrors
        return None, [f"manifest: malformed JSON ({exc})"]
    if not isinstance(data, dict):
        return None, ["manifest: top level must be a JSON object"]
    errors = []
    if data.get("version") != MANIFEST_VERSION:
        errors.append(f"manifest: unsupported version {data.get('version')!r} "
                      f"(expected {MANIFEST_VERSION})")
    _validate_section(data, "protected", LEGACY, errors)
    _validate_section(data, "guards", GUARDS, errors)
    hist = data.get("history")
    if not isinstance(hist, list) or not hist or not all(
            isinstance(h, dict) and all(isinstance(h.get(k), str) and h.get(k)
                                        for k in ("action", "reason", "utc"))
            for h in hist):
        errors.append("manifest: 'history' must be a non-empty list of "
                      "{action, reason, utc} entries")
    seal = data.get("seal")
    if not isinstance(seal, str) or not _HEX64.fullmatch(seal):
        errors.append("manifest: 'seal' missing or invalid")
    elif not errors and seal != _seal(data):
        errors.append("manifest: seal mismatch - the manifest was edited by hand "
                      "or corrupted")
    return (None, errors) if errors else (data, [])


def _link_unsupported(exc):
    """True only for errors that genuinely mean hard links are unavailable."""
    if isinstance(exc, FileExistsError):
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror is not None:
        return winerror in _NO_LINK_WINERRORS
    return exc.errno in _NO_LINK_ERRNOS


def _create_exclusive(path, text):
    """POSIX fallback when hard links are unsupported: O_EXCL creation never
    replaces an existing file but is NOT atomic (the file is briefly incomplete).
    A half-written file we created is removed again."""
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise


def _write_manifest(root, data, overwrite=False):
    """Write the sealed manifest.

    overwrite=False (init, migration): NEVER replaces an existing file.  Full
    content goes to a unique temp file, then os.link(tmp, path) publishes it
    (atomic, FileExistsError if the destination exists).  Only when the link
    error satisfies _link_unsupported(): Windows uses os.rename (atomic, refuses
    to replace); POSIX uses O_EXCL creation (no-replace but NOT atomic, see the
    module docstring).  All other OSErrors propagate.  The temp file is always
    removed.  If another process created the manifest first, ManifestExistsError
    is raised and that file is left untouched.

    overwrite=True is used only by --reset-baseline, which has already validated
    the existing manifest, and replaces it atomically with os.replace.
    """
    data = dict(data)
    data["seal"] = _seal(data)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    path = Path(root) / MANIFEST_REL
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if overwrite:
            os.replace(tmp, path)
            return
        try:
            os.link(tmp, path)
        except FileExistsError:
            raise ManifestExistsError(str(path)) from None
        except OSError as exc:
            if not _link_unsupported(exc):
                raise  # unrelated failure: never disguised as "no hard links"
            try:
                if _IS_WINDOWS:
                    os.rename(tmp, path)  # Windows: fails if path exists
                else:
                    _create_exclusive(path, text)
            except FileExistsError:
                raise ManifestExistsError(str(path)) from None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


class ManifestExistsError(FileExistsError):
    """The active manifest appeared (or existed) at the final creation step."""


_RACE = ["refused: the active manifest was created by someone else during this "
         "operation; it was left untouched"]


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hashes(root, rels):
    return {r: digest(root, r) for r in rels}


def _missing(root, rels):
    return [r for r in rels if not (Path(root) / r).is_file()]


# ------------------------------------------------------- protected paths
def protected_problems(root=ROOT):
    data, errors = load_manifest(root)
    if errors:
        return errors
    out = []
    for section, rels in (("protected", LEGACY), ("guards", GUARDS)):
        for r in rels:
            if not (Path(root) / r).is_file():
                out.append(f"missing {section} file: {r}")
            elif digest(root, r) != data[section][r]:
                out.append(f"changed {section} file: {r}")
    return out


# -------------------------------------------------------- import boundary
def _forbidden(name):
    return any(name == b or name.startswith(b + ".") for b in FORBIDDEN)


def _resolve_from(pkg_parts, node):
    base = node.module or ""
    if node.level:
        keep = max(0, len(pkg_parts) - node.level + 1)
        base = ".".join(pkg_parts[:keep] + ([base] if base else []))
    return base


def _lit(node):
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _arg(call, pos, kw):
    if len(call.args) > pos:
        return call.args[pos]
    for k in call.keywords:
        if k.arg == kw:
            return k.value
    return None


def _dynamic_names(call, fname):
    """(module names, problem or None) for one dynamic-import call."""
    first = _arg(call, 0, "name")
    name = _lit(first)
    if name is None:
        return [], "dynamic import with a non-literal module name"
    names = [name]
    if fname == "__import__":
        level = _arg(call, 4, "level")
        if level is not None and not (isinstance(level, ast.Constant) and level.value == 0):
            return [], "__import__ with a relative/non-literal level"
        fl = _arg(call, 3, "fromlist")
        if isinstance(fl, (ast.List, ast.Tuple)):
            names += [f"{name}.{_lit(e)}" for e in fl.elts if _lit(e)]
    elif name.startswith("."):
        pkg = _lit(_arg(call, 1, "package"))
        if pkg is None:
            return [], "relative dynamic import without a literal package"
        try:
            names = [importlib.util.resolve_name(name, pkg)]
        except (ImportError, ValueError):
            return [], "relative dynamic import that cannot be resolved"
    return names, None


def scan_source(source, pkg_parts):
    """Problems (strings without the file prefix) found in one module's source."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"cannot parse ({exc.msg}, line {exc.lineno})"]
    dyn = set(DYN_NAMES)
    for n in ast.walk(tree):  # aliases: from importlib import import_module as f
        if isinstance(n, ast.ImportFrom) and not n.level and n.module in (
                "importlib", "importlib.util", "runpy"):
            dyn |= {a.asname for a in n.names if a.name in DYN_NAMES and a.asname}
    out, handled = [], set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if _forbidden(a.name):
                    out.append(f"line {n.lineno}: imports {a.name}")
        elif isinstance(n, ast.ImportFrom):
            base = _resolve_from(pkg_parts, n)
            for m in [base] + [f"{base}.{a.name}" for a in n.names]:
                if _forbidden(m):
                    out.append(f"line {n.lineno}: imports {m}")
        elif isinstance(n, ast.Call):
            f = n.func
            fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if fname in CODE_EXEC and isinstance(f, ast.Name):
                out.append(f"line {n.lineno}: {fname}() cannot be verified")
            elif fname in dyn:
                handled.add(id(f))
                canon = "__import__" if fname == "__import__" else (
                    fname if fname in DYN_NAMES else "import_module")
                names, problem = _dynamic_names(n, canon)
                if problem:
                    out.append(f"line {n.lineno}: {fname}(): {problem}")
                out += [f"line {n.lineno}: dynamically imports {m}"
                        for m in names if _forbidden(m)]
    for n in ast.walk(tree):  # aliasing a dynamic importer without calling it
        ref = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if ref == "__import__" and id(n) not in handled and isinstance(
                getattr(n, "ctx", None), ast.Load):
            out.append(f"line {n.lineno}: reference to __import__ (aliasing)")
    return out


def boundary_problems(root=ROOT):
    root = Path(root)
    calc = root / "finance" / "calc"
    out = []
    for f in sorted(calc.rglob("*.py")) if calc.exists() else []:
        rel = f.relative_to(root)
        pkg_parts = list(rel.with_suffix("").parts[:-1])
        try:
            src = f.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            out.append(f"{rel.as_posix()}: unreadable ({exc})")
            continue
        out += [f"{rel.as_posix()}: {p}" for p in scan_source(src, pkg_parts)]
    return out


def check(root=ROOT):
    return protected_problems(root) + boundary_problems(root)


# ------------------------------------------------------- baseline changes
def init_baseline(root, reason):
    """Create the first manifest.  Refuses if one exists (even a broken one)."""
    root = Path(root)
    if not reason or not reason.strip():
        return ["--reason is required"]
    if (root / MANIFEST_REL).exists():
        return ["refused: a manifest already exists; use --reset-baseline "
                "(valid manifest) or delete it deliberately first"]
    gone = _missing(root, LEGACY + GUARDS)
    if gone:
        return [f"refused: files to protect are missing: {', '.join(gone)}"]
    try:
        _write_manifest(root, {
            "version": MANIFEST_VERSION,
            "protected": _hashes(root, LEGACY),
            "guards": _hashes(root, GUARDS),
            "history": [{"action": "init", "reason": reason.strip(), "utc": _now()}],
        })
    except ManifestExistsError:
        return list(_RACE)
    return []


def load_legacy_manifest(path):
    """Read the OLD flat manifest.  Return (hashes, errors)."""
    path = Path(path)
    if not path.is_file():
        return None, [f"legacy manifest: file not found: {path}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        return None, [f"legacy manifest: malformed JSON ({exc})"]
    if not isinstance(data, dict):
        return None, ["legacy manifest: top level must be a JSON object"]
    errors = []
    for rel in LEGACY:
        if rel not in data:
            errors.append(f"legacy manifest: missing entry '{rel}'")
        elif not isinstance(data[rel], str) or not _HEX64.fullmatch(data[rel]):
            errors.append(f"legacy manifest: invalid hash for '{rel}' "
                          "(need 64 lowercase hex characters)")
    errors += [f"legacy manifest: unexpected entry '{rel}'"
               for rel in data if rel not in LEGACY]
    return (None, errors) if errors else ({r: data[r] for r in LEGACY}, [])


def migrate_legacy(root, source, reason):
    """Create the first sealed v1 manifest from the old flat manifest."""
    root = Path(root)
    if not reason or not reason.strip():
        return ["refused: --reason is required"]
    active = root / MANIFEST_REL
    if os.path.lexists(active):
        return ["refused: an active manifest already exists (valid or not); "
                "migration never overwrites it"]
    if source is None or str(source).startswith("--") or not str(source).strip():
        return ["refused: --from-legacy-manifest needs an explicit file path"]
    source = Path(source)
    if source.exists() and source.resolve() == active.resolve():
        return ["refused: the source may not be the active manifest path"]
    legacy, errors = load_legacy_manifest(source)
    if errors:
        return ["refused: source manifest is not valid:"] + errors
    gone = _missing(root, LEGACY + GUARDS)
    if gone:
        return [f"refused: files are missing: {', '.join(gone)}"]
    bad = [f"mismatch: {r} differs from the legacy manifest"
           for r in LEGACY if digest(root, r) != legacy[r]]
    if bad:
        return ["refused: current legacy files do not match the source:"] + bad
    bounds = boundary_problems(root)
    if bounds:
        return ["refused: import boundary is not clean:"] + bounds
    try:
        _write_manifest(root, {
            "version": MANIFEST_VERSION,
            "protected": dict(legacy),  # verbatim from the source, not recomputed
            "guards": _hashes(root, GUARDS),
            "history": [{
                "action": "migrate-legacy", "reason": reason.strip(), "utc": _now(),
                "source_manifest": str(source).replace("\\", "/"),
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        })
    except ManifestExistsError:
        return list(_RACE)
    return []


def reset_baseline(root, reason, confirm):
    """Re-record GUARD hashes only, after validating the existing baseline."""
    root = Path(root)
    if confirm != CONFIRM_TOKEN:
        return [f"refused: pass --confirm {CONFIRM_TOKEN}"]
    if not reason or not reason.strip():
        return ["refused: --reason is required"]
    data, errors = load_manifest(root)
    if errors:
        return ["refused: existing baseline is not valid:"] + errors
    gone = _missing(root, LEGACY + GUARDS)
    if gone:
        return [f"refused: files are missing: {', '.join(gone)}"]
    legacy = [f"changed protected file: {r}" for r in LEGACY
              if digest(root, r) != data["protected"][r]]
    if legacy:
        return ["refused: legacy files differ from the baseline; they may "
                "not be re-recorded:"] + legacy
    bounds = boundary_problems(root)
    if bounds:
        return ["refused: import boundary is not clean:"] + bounds
    data["guards"] = _hashes(root, GUARDS)
    data["history"] = data["history"] + [{
        "action": "reset-guards", "reason": reason.strip(), "utc": _now(),
        "previous_seal": data["seal"]}]
    _write_manifest(root, data, overwrite=True)
    return []


# -------------------------------------------------------------------- CLI
def _opt(argv, name):
    if name in argv:
        i = argv.index(name)
        return argv[i + 1] if i + 1 < len(argv) else None
    return None


def main(argv, root=ROOT):
    if "--record" in argv:
        print("--record was removed: it could silently overwrite the trusted "
              "baseline.\nUse --init (no manifest yet) or --reset-baseline "
              f"--confirm {CONFIRM_TOKEN} --reason TEXT.")
        return 2
    if "--from-legacy-manifest" in argv:
        if "--init" in argv or "--reset-baseline" in argv:
            print("refused: --from-legacy-manifest cannot be combined with "
                  "--init or --reset-baseline")
            return 2
        errs = migrate_legacy(root, _opt(argv, "--from-legacy-manifest"),
                              _opt(argv, "--reason"))
        print("\n".join(errs) or "sealed v1 manifest created from the legacy manifest")
        return 2 if errs else 0
    if "--init" in argv:
        errs = init_baseline(root, _opt(argv, "--reason"))
        print("\n".join(errs) or "baseline created")
        return 2 if errs else 0
    if "--reset-baseline" in argv:
        errs = reset_baseline(root, _opt(argv, "--reason"), _opt(argv, "--confirm"))
        print("\n".join(errs) or "guard hashes re-recorded; legacy hashes unchanged")
        return 2 if errs else 0
    probs = check(root)
    print("\n".join(probs) or "OK: manifest valid, protected paths unchanged, import boundary clean")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
