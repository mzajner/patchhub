#!/usr/bin/env python3
"""Check PatchHub before a merge: python3 tools/check_packs.py [--strict] [--signature] [--root DIR]

Mirrors what PatchLab refuses at install (PatchCore packages/graph/Source/graph/packs.cpp, tools/pack_make.py)
plus the hub's own rules: CC-BY-4.0, reverse-DNS ids under org.openpatch.* or io.github.*, zips named
<id>-<version>.zip, and an index.json whose entries match the files byte for byte.
Warnings do not fail the run; --strict turns them into failures. --signature also verifies index.json.sig
with the minisign binary (the owner signs on merge, so pull requests leave it off).
Exit 0 = clean, 1 = something is wrong.
"""
import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

PUBLIC_KEY = "RWQO87fofYsYyI+wcOUDQzXyyU3Ee72WI7bSXMX1sXgj7s5/cWdVGBOU"   # PatchCore hub_trust.h
RAW_BASE = "https://raw.githubusercontent.com/mzajner/patchhub/main/packs/"
LICENCE = "CC-BY-4.0"
MAX_FILE, MAX_PACK, MAX_ENTRIES, MAX_DOC = 128 << 20, 512 << 20, 4096, 8 << 20   # packs.h
HUB_MAX_ZIP = 50 << 20            # GitHub warns at 50 MiB and refuses 100 MiB
MAX_SIDE, MAX_PIXELS = 16384, 16_000_000
PURPOSES = ("instrument", "effect", "midi", "learn", "utility")
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
AUDIO = {".wav", ".flac", ".aif", ".aiff", ".ogg", ".mp3"}
KINDS = {"face-asset": IMAGES | {".json"}, "nam-model": {".json", ".nam"}, "preset": {".plpreset"},
         "wasm-block": {".wasm"}, "sample": AUDIO}
DOCS = {".json", ".nam", ".plpreset", ".xml", ".svg"}
NATIVE = {".dylib", ".so", ".dll", ".vst3", ".component", ".clap", ".exe"}
NESTED = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
MAGIC = (b"\x7fELF", b"MZ", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe",
         b"\xca\xfe\xba\xbe")
ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:\.[a-z][a-z0-9]*(?:-[a-z0-9]+)*)+")
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z.-]+)?")
SHA = re.compile(r"[0-9a-f]{64}")
SKIP_DIRS = {".git", ".github", "gallery", "packs", "tools"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def no_dupes(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError(f"duplicate key {k!r}")
        d[k] = v
    return d


def load(text):
    return json.loads(text, object_pairs_hook=no_dupes)


def safe_path(p):
    """packs.cpp safePath + nativePath: relative, printable ASCII, no traversal, no native code."""
    if not p or len(p) > 1024 or p[0] == "/" or p[-1] == "/" or "//" in p or "\\" in p or ":" in p:
        return "not a plain relative path"
    if any(ord(c) < 32 or ord(c) >= 127 for c in p):
        return "not printable ASCII"
    parts = p.split("/")
    if len(parts) > 32 or any(x in (".", "..") or len(x) > 240 for x in parts):
        return "unsafe path component"
    if any(PurePosixPath(x).suffix.lower() in NATIVE or ".so." in x.lower() for x in parts):
        return "native code"
    return None


def png_size(b):
    if len(b) < 24 or b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", b[16:24])


def summary_of(m):
    """What pack_make.summary_of puts in an index entry."""
    out = {k: m[k] for k in ("id", "name", "version", "description", "author", "minAppVersion")}
    for k in ("purpose", "cover", "buyUrl", "buyLine", "exportable", "training", "homepage", "tags"):
        if k in m and not (k == "purpose" and m[k] not in PURPOSES):
            out[k] = m[k]
    out["licence"] = {"spdx": m["licence"]["spdx"]}
    return out


def check_zip(path, err, warn):
    """Everything PatchLab and the hub require of one pack zip. Returns pack.json (or None) for the index check."""
    def bad(msg):
        err(f"{path.name}: {msg}")
    if path.stat().st_size > HUB_MAX_ZIP:
        bad(f"zip is {path.stat().st_size >> 20} MiB; the hub holds at most {HUB_MAX_ZIP >> 20} MiB per pack")
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as e:
        return bad(f"not a zip ({e})")
    with zf:
        infos = [i for i in zf.infolist() if not i.filename.endswith("/")]
        if len(zf.infolist()) > MAX_ENTRIES:
            return bad(f"more than {MAX_ENTRIES} entries")
        names, total = {}, 0
        for i in infos:
            n, ext = i.filename, PurePosixPath(i.filename).suffix.lower()
            if (why := safe_path(n)):
                bad(f"{n}: {why}")
            if n.lower() in names:
                bad(f"{n}: duplicate entry")
            names[n.lower()] = i
            mode = i.external_attr >> 16
            if (mode & 0o170000) not in (0, 0o100000):
                bad(f"{n}: symlink or special file")
            if mode & 0o111:
                bad(f"{n}: executable")
            if i.flag_bits & 1:
                bad(f"{n}: encrypted")
            if ext in NESTED:
                bad(f"{n}: nested archive")
            if i.file_size > MAX_FILE:
                bad(f"{n}: over 128 MiB")
            if i.file_size > 100 * max(i.compress_size, 1):
                bad(f"{n}: compression ratio over 100:1")
            total += i.file_size
        if total > MAX_PACK:
            bad("unpacks to more than 512 MiB")
        if (broken := zf.testzip()):
            return bad(f"{broken}: CRC mismatch, the zip is damaged")
        if "pack.json" not in names:
            return bad("no pack.json")
        try:
            m = load(zf.read("pack.json"))
            ident, ver = m["id"], m["version"]
            assert isinstance(m, dict) and all(isinstance(m[k], str) and 0 < len(m[k]) <= 240 for k in
                                               ("id", "name", "version", "author", "minAppVersion"))
            assert isinstance(m["description"], str) and 0 < len(m["description"]) <= 500
            lic, contents = m["licence"], m["contents"]
            assert isinstance(lic["spdx"], str) and isinstance(lic["text"], str) and isinstance(contents, list) and contents
        except (ValueError, KeyError, TypeError, AssertionError) as e:
            return bad(f"pack.json is not a valid manifest ({type(e).__name__}: {e})")
        if not ID.fullmatch(ident) or len(ident) > 200:
            bad("id must be lowercase reverse-DNS")
        elif not ident.startswith(("org.openpatch.", "io.github.")):
            bad("id must start with org.openpatch. or io.github.<user>.")
        for field in ("version", "minAppVersion"):
            if not SEMVER.fullmatch(m[field]):
                bad(f"{field} is not semver: {m[field]}")
        if path.name != f"{ident}-{ver}.zip":
            bad(f"file name must be {ident}-{ver}.zip")
        if lic["spdx"] != LICENCE:
            bad(f"licence.spdx is {lic['spdx']}; the hub lists only {LICENCE}")
        declared = {"pack.json"}
        entries = [{"path": lic["text"], "kind": "licence", "sha256": lic.get("sha256")}] + contents
        for e in entries:
            try:
                p, kind, want = e["path"], e["kind"], e["sha256"]
            except (KeyError, TypeError):
                bad("a contents entry needs path, kind and sha256")
                continue
            if (why := safe_path(p)):
                bad(f"{p}: {why}")
            if p.lower() in {d.lower() for d in declared}:
                bad(f"{p}: listed twice")
            declared.add(p)
            if p.lower() not in names:
                bad(f"{p}: listed in pack.json but not in the zip")
                continue
            info = names[p.lower()]
            ext = PurePosixPath(p).suffix.lower()
            if kind != "licence" and (kind not in KINDS or ext not in KINDS[kind]):
                bad(f"{p}: a {kind} file cannot have the extension {ext!r}")
            if kind == "wasm-block":
                warn(f"{path.name}: {p} is code (wasm-block); the hub lists it as unverified")
            if not isinstance(want, str) or not SHA.fullmatch(want):
                bad(f"{p}: sha256 must be 64 lowercase hex digits")
                continue
            data = zf.read(info)
            if sha256(data) != want:
                bad(f"{p}: sha256 differs from pack.json")
            if kind == "licence" and not data.strip():
                bad("licence text is empty")
            if data[:4] in MAGIC or data[:2] == b"MZ":
                bad(f"{p}: native binary")
            if ext in DOCS and len(data) > MAX_DOC:
                bad(f"{p}: document over 8 MiB")
            if ext in (".json", ".nam"):
                try:
                    load(data)
                except ValueError as ex:
                    bad(f"{p}: not strict JSON ({ex})")
            if ext == ".png":
                size = png_size(data)
                if not size or not all(size):
                    bad(f"{p}: not a readable PNG")
                elif max(size) > MAX_SIDE or size[0] * size[1] > MAX_PIXELS:
                    bad(f"{p}: image is {size[0]}x{size[1]}; the limit is 16384 a side and 16 megapixels")
        for n in names:
            if n not in {d.lower() for d in declared}:
                bad(f"{n}: in the zip but not in pack.json")
        if m.get("purpose") not in (None, *PURPOSES):
            bad("purpose must be one of " + ", ".join(PURPOSES))
        if m.get("buyUrl") and (not str(m["buyUrl"]).startswith("https://") or not m.get("buyLine")):
            bad("buyUrl must be https and come with a buyLine")
        if m.get("cover"):
            cover = zf.read(names[m["cover"].lower()]) if m["cover"].lower() in names else b""
            if m["cover"] not in [c.get("path") for c in contents]:
                bad("cover must be one of the pack's contents")
            elif m["cover"].lower().endswith(".png") and png_size(cover) != (1600, 400):
                bad("cover must be 1600x400")
        return m


def check_index(root, packs, err, warn, signature):
    """packs: {zip name: pack.json}. index.json must list exactly these, with their hashes."""
    def bad(msg):
        err(f"index.json: {msg}")
    index = root / "index.json"
    if not index.is_file():
        return bad("missing")
    raw = index.read_bytes()
    try:
        side = (root / "index.json.sha256").read_text().split()[0]
    except (OSError, IndexError):
        side = ""
    if side != sha256(raw):
        bad("index.json.sha256 does not match index.json (the maintainer regenerates and signs it, see CONTRIBUTING.md)")
    try:
        doc = load(raw)
        assert doc["schema"] == 1 and isinstance(doc["serial"], int) and doc["serial"] >= 0
        assert isinstance(doc["packs"], list) and isinstance(doc["blocklist"], list)
        expires = datetime.strptime(doc["expires"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        datetime.strptime(doc["generated"], "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, KeyError, TypeError, AssertionError) as e:
        return bad(f"not a valid envelope ({type(e).__name__}: {e})")
    if expires < datetime.now(timezone.utc):
        warn(f"index.json: expired {doc['expires']}; PatchLab shows it as stale until it is re-signed")
    if len(raw) > 1 << 20:
        bad("over 1 MiB")
    for b in doc["blocklist"]:
        if not (isinstance(b, dict) and ID.fullmatch(str(b.get("id", ""))) and b.get("reason")):
            bad("a blocklist row is {id, reason}")
    seen = set()
    for e in doc["packs"]:
        try:
            m, url = e["manifest"], e["url"]
            name = url.rsplit("/", 1)[-1]
            label = f"index.json ({m['id']} {m['version']})"
            if e["format"] != "zip":
                err(f"{label}: format must be zip")
            if url != RAW_BASE + name:
                err(f"{label}: url must be {RAW_BASE}<file>")
            if name in seen:
                err(f"{label}: listed twice")
            seen.add(name)
            if name not in packs:
                err(f"{label}: {name} is not in packs/")
                continue
            z = root / "packs" / name
            if e["sha256"] != sha256(z.read_bytes()) or e["size"] != z.stat().st_size:
                err(f"{label}: sha256 or size differs from {name}")
            if packs[name] and m != summary_of(packs[name]):
                err(f"{label}: manifest summary differs from the pack.json inside {name}")
        except (KeyError, TypeError) as ex:
            err(f"index.json: malformed entry ({type(ex).__name__}: {ex})")
    for name in sorted(set(packs) - seen):
        warn(f"{name}: in packs/ but not in index.json yet (the owner adds it and signs on merge)")
    gallery = root / "gallery" / "index.html"
    if gallery.is_file():
        ids = set(re.findall(r'<article [^>]*id="([^"]+)"', gallery.read_text()))
        want = {e["manifest"]["id"] for e in doc["packs"] if isinstance(e, dict) and "manifest" in e}
        for i in sorted(ids ^ want):
            err(f"gallery/index.html: {i} {'is not in the index' if i in ids else 'is missing'}")
    if signature:
        if not shutil.which("minisign"):
            err("index.json.sig: --signature needs the minisign binary")
        else:
            r = subprocess.run(["minisign", "-Vm", str(index), "-x", str(root / "index.json.sig"), "-P", PUBLIC_KEY],
                               capture_output=True, text=True)
            if r.returncode:
                err("index.json.sig does not verify with the hub key (re-sign after any change to index.json)")


def check_submissions(root, packs, err, warn):
    """Folders a pack_publish pull request adds: <id>/entry.json + <id>/pack.json beside packs/<id>-<version>.zip."""
    for d in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith(".")):
        try:
            entry, summary = load((d / "entry.json").read_text()), load((d / "pack.json").read_text())
        except (OSError, ValueError) as e:
            err(f"{d.name}/: needs a readable entry.json and pack.json ({e})")
            continue
        if summary.get("id") != d.name:
            err(f"{d.name}/: folder name must be the pack id")
        name = f"{d.name}-{summary.get('version')}.zip"
        if not str(entry.get("url", "")).startswith(RAW_BASE):
            warn(f"{d.name}/: archive is hosted elsewhere ({entry.get('url')}); the owner downloads and checks it on merge")
            continue
        if entry["url"] != RAW_BASE + name or name not in packs:
            err(f"{d.name}/: entry.json url must be {RAW_BASE}{name} and the zip must be in packs/")
            continue
        z = root / "packs" / name
        if entry.get("sha256") != sha256(z.read_bytes()) or entry.get("size") != z.stat().st_size:
            err(f"{d.name}/: entry.json sha256 or size differs from {name}")
        if packs[name] and summary != summary_of(packs[name]):
            err(f"{d.name}/: pack.json differs from the one inside {name}")


def run(root, strict=False, signature=False, out=print):
    problems, notes = [], []
    err, warn = problems.append, notes.append
    packs = {}
    for z in sorted((root / "packs").glob("*.zip")):
        before = len(problems)
        packs[z.name] = check_zip(z, err, warn)
        out(("ok   " if len(problems) == before else "FAIL ") + z.name)
    check_index(root, packs, err, warn, signature)
    check_submissions(root, packs, err, warn)
    for n in notes:
        out("warn " + n)
    for p in problems:
        out("FAIL " + p)
    failed = bool(problems) or (strict and bool(notes))
    out(f"{len(packs)} pack(s), {len(problems)} problem(s), {len(notes)} warning(s): {'FAILED' if failed else 'clean'}")
    return 1 if failed else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--signature", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.root, a.strict, a.signature))
