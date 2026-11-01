# PatchHub

PatchHub is the public shelf of packs for PatchLab: samples, wavetables, presets, faces and amp models that you can drop into your own plugins.

A pack holds data only. It never carries code that runs on your machine, and PatchLab refuses a pack that tries.

## Install a pack in PatchLab

1. Open the **Packs** tab.
2. Paste the shelf address into the field and press **Browse**:
   `https://mzajner.github.io/patchhub/index.json`
3. Press **Install** on the pack you want.

PatchLab does not have this address built in yet, so you paste it once. Before it installs anything it checks the shelf's signature and the fingerprint of every file, and it tells you why when it refuses.

## What is in here

- `index.json`, `index.json.sha256`, `index.json.sig`: the list of packs and its signature. The maintainer signs it offline, so a pack only shows up in PatchLab after that signature.
- `packs/`: the pack zips the list points to.
- `gallery/index.html`: a page to browse the packs.
- `tools/check_packs.py`: the check every pull request runs. Run it yourself with `python3 tools/check_packs.py`.
- `tools/gen_wavetables.py`: writes the two wavetables in Supersaw Pad, so they come from arithmetic and nothing else.

## The signature

PatchLab ships the shelf's public key and refuses a list that is unsigned, altered, or older than one it has already seen. The key:

```
RWQO87fofYsYyI+wcOUDQzXyyU3Ee72WI7bSXMX1sXgj7s5/cWdVGBOU
```

To check it yourself with [minisign](https://jedisct1.github.io/minisign/):

```
minisign -Vm index.json -x index.json.sig -P RWQO87fofYsYyI+wcOUDQzXyyU3Ee72WI7bSXMX1sXgj7s5/cWdVGBOU
```

## Licence

Two licences, by folder:

- **Packs** (`packs/`, and the pack data they contain) are [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Use them in your music and your plugins, commercially too. Credit the author named in the pack's `pack.json`, link the licence, and say if you changed it. Each pack carries its own `LICENCE.txt`. The generated wavetables in Supersaw Pad are also released as CC0.
- **`tools/` and `gallery/`** (the checker, its tests, the wavetable generator and the gallery page) are under the [MIT licence](LICENSE).

## Add your own pack

See [CONTRIBUTING.md](CONTRIBUTING.md).
