# Releasing a new version

The checklist for publishing Snip Occlusion (first time or an update).

## 1. Check the code

```bash
pip install PyQt6 anki pytest
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v
```

All tests must pass. Bump `human_version` in
`snip_occlusion/manifest.json` and add a section to `CHANGELOG.md`.

## 2. Build the package

```bash
python tools/build_ankiaddon.py
```

This writes `dist/snip_occlusion.ankiaddon` — a zip of the add-on
folder's contents with no top-level folder, no `__pycache__`, and no
`meta.json`, which is exactly what AnkiWeb requires.

## 3. Test it in a real Anki

Install the file (Tools → Add-ons → Install from File…), restart Anki,
snip a slide, add a card, review it. On Windows also click "Text preview"
to confirm OCR runs.

## 4. Upload to AnkiWeb

1. Log in (or register) at <https://ankiweb.net>.
2. Go to <https://ankiweb.net/shared/addons/> and press **Upload**.
3. First time: fill in the form using `docs/ankiweb-listing.md`
   (title, description, supported versions) and attach
   `dist/snip_occlusion.ankiaddon`. Submitting gives the add-on its
   permanent numeric ID — students install it with Tools → Add-ons →
   Get Add-ons and that code.
4. Updates: open your add-on's page → Edit → upload the new
   `.ankiaddon`. The ID stays the same and users get the update via
   Tools → Add-ons → Check for Updates.

## 5. Tag the release on GitHub

After merging to `main`, create a tag/release named after the version
(e.g. `v0.4.0`) on the GitHub website (Releases → Draft a new release),
and attach the built `.ankiaddon` so non-AnkiWeb users can download it.
