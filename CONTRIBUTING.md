# Adding a pack to PatchHub

You made something in PatchLab that other people could use: a set of samples, a wavetable pad, a face, a preset bank. This is how it gets on the shelf.

## What goes in a pack

A pack is a zip of data: samples and wavetables, presets, faces and the images they use, amp models. No native code, no scripts, no zips inside the zip. PatchLab refuses those at install, and the check here refuses them first. A pack of WebAssembly blocks can be listed, but it is marked as unverified.

Only share what you made, or what you have the right to release under CC BY 4.0. Samples, wavetables, images and fonts count. If a sound came from someone else's library, leave it out.

## Licence

Every pack on the hub is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Set `licence.spdx` to `CC-BY-4.0` and ship the licence text in the pack. The licence is irrevocable: if you later take a pack down, it stops being listed, but copies people already have stay theirs under CC BY 4.0.

## Make the pack and open the pull request

In PatchLab, ask your agent to use `pack_publish` on your project. It builds the pack, trial-installs it like a user would, and opens the pull request through your own GitHub login (`gh`). A few things to set:

- `id`: `io.github.<your-github-name>.<pack-name>`. The `org.openpatch.` names belong to the project.
- `licence`: `CC-BY-4.0`, with `licenceFile` pointing at the licence text.
- `description`: one honest sentence about what is inside.

Use `dryRun` first to see the pull request without opening it.

You can also open the pull request by hand. One pack per pull request, on a branch called `pack/<id>-<version>`, with:

- `packs/<id>-<version>.zip`: the pack
- `<id>/pack.json`: the summary of the pack's own `pack.json` (id, name, version, description, author, minAppVersion, `licence: {"spdx": ...}`, and any optional fields)
- `<id>/entry.json`: `{"format": "zip", "url": "https://raw.githubusercontent.com/mzajner/patchhub/main/packs/<id>-<version>.zip", "sha256": "...", "size": ..., "minAppVersion": "..."}`

If the zip is too big for GitHub, host it yourself over https and put that address in `entry.json`. The maintainer then downloads and checks it before merging.

## The check

Run it before you push:

```
python3 tools/check_packs.py
```

The same check runs on every pull request. It looks at each zip for:

- the licence is `CC-BY-4.0` and the licence text is in the pack
- `pack.json` is complete, the id and version are well formed, and the file is named `<id>-<version>.zip`
- every file is listed with the right fingerprint, nothing is missing, nothing extra is hiding in the zip
- no absolute paths, no `..`, no native binaries, no symlinks, no nested archives
- size limits: 128 MiB per file, 512 MiB per pack, 8 MiB per document, images up to 16 megapixels, a cover of exactly 1600 x 400, and 50 MiB per zip on this repository
- the entries in `index.json` match the zips byte for byte

It does not listen to your samples or look at your faces. A person does that.

## How a pull request is reviewed and signed

The maintainer reads every first listing and every new version by hand and tries the pack. Nothing merges on its own.

After the merge, the maintainer rebuilds `index.json` and the gallery on their own machine and signs the index with a key that never leaves it. Only then does the pack show up in PatchLab, which is why it can take a little while after the merge. The signing never happens in a pull request or in CI.

For the maintainer, the steps after a merge are:

```
patch pack index-make packs/*.zip -o index.json --serial <last serial + 1> --expires-days 90 \
  --base-url https://raw.githubusercontent.com/mzajner/patchhub/main/packs --gallery gallery
minisign -Sm index.json -x index.json.sig -s <path to the offline key>
python3 tools/check_packs.py --signature --strict
```

Each index gets a higher serial and an expiry date. PatchLab refuses a lower serial than the last one it saw, and labels an index past its expiry as stale.

## Taking a pack down

Open an issue. The pack is removed from the list and added to the signed blocklist, so PatchLab marks it as withdrawn. Nobody's installed copy or project is deleted.
