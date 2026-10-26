#!/usr/bin/env python3
"""Red proofs for check_packs.py: python3 tools/test_check_packs.py. Each tamper must turn the check red."""
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_packs as cp

REPO = Path(__file__).resolve().parents[1]
ZIP = "org.openpatch.supersaw-pad-1.0.1.zip"


def rebuild(root, mutate):
    """Rewrite the zip with mutate(entries: name -> bytes) applied; the index is left as it was."""
    path = root / "packs" / ZIP
    with zipfile.ZipFile(path) as zf:
        entries = {i.filename: zf.read(i) for i in zf.infolist()}
    mutate(entries)
    with zipfile.ZipFile(path, "w") as zf:
        for n, b in entries.items():
            zf.writestr(n, b)


def manifest(entries, **change):
    m = json.loads(entries["pack.json"])
    m.update(change)
    entries["pack.json"] = json.dumps(m).encode()


def tamper_index(root, **change):
    d = json.loads((root / "index.json").read_text())
    d["packs"][0].update(change)
    (root / "index.json").write_text(json.dumps(d, indent=1) + "\n")


CASES = {
    "licence is not CC-BY-4.0": lambda r: rebuild(r, lambda e: manifest(e, licence={**json.loads(e["pack.json"])["licence"], "spdx": "MIT"})),
    "absolute path in the zip": lambda r: rebuild(r, lambda e: e.update({"/etc/passwd": b"x"})),
    "path climbs out": lambda r: rebuild(r, lambda e: e.update({"../x.txt": b"x"})),
    "native code": lambda r: rebuild(r, lambda e: e.update({"libx.dylib": b"x"})),
    "file changed after hashing": lambda r: rebuild(r, lambda e: e.update({"wavetables/additive_harmonics.wav": b"RIFF"})),
    "id outside org.openpatch / io.github": lambda r: rebuild(r, lambda e: manifest(e, id="com.example.pad")),
    "index hash wrong": lambda r: tamper_index(r, sha256="0" * 64),
    "index size wrong": lambda r: tamper_index(r, size=1),
    "index entry lies about the pack": lambda r: tamper_index(r, manifest={**json.loads((r / "index.json").read_text())["packs"][0]["manifest"], "name": "Other"}),
    "gallery names a removed pack": lambda r: (r / "gallery/index.html").write_text(
        (r / "gallery/index.html").read_text().replace("<main>", '<main><article id="org.openpatch.squeeze"></article>')),
}


def fresh():
    tmp = Path(tempfile.mkdtemp(prefix="check-packs-"))
    shutil.copytree(REPO, tmp / "r", ignore=shutil.ignore_patterns(".git"))
    return tmp, tmp / "r"


def main():
    quiet = lambda _: None
    tmp, root = fresh()
    assert cp.run(root, out=quiet) == 0, "the clean repo must pass"
    shutil.rmtree(tmp)
    for name, tamper in CASES.items():
        tmp, root = fresh()
        tamper(root)
        rc = cp.run(root, out=quiet)
        shutil.rmtree(tmp)
        assert rc == 1, f"not caught: {name}"
        print("red  ", name)
    tmp, root = fresh()
    (root / "packs" / ZIP).unlink()
    assert cp.run(root, out=quiet) == 1, "not caught: index names a missing zip"
    shutil.rmtree(tmp)
    print("all red proofs pass")


if __name__ == "__main__":
    main()
