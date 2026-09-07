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

1. Log in at <https://ankiweb.net> with the account you sync Anki
   with. AnkiWeb refuses add-on uploads from new accounts ("Sorry,
   your account is too new for this action") to stop spam; the exact
   criteria aren't published, but an account that has been syncing a
   collection for a while passes. If you hit that message, post in the
   *Syncing & AnkiWeb* category of <https://forums.ankiweb.net> asking
   for sharing to be enabled — the Anki developer approves accounts
   there — and try again once they reply.
2. Go to <https://ankiweb.net/shared/addons/> and press **Upload**.
3. First time: fill in the form using `docs/ankiweb-listing.md`
   (title, description, supported versions) and attach
   `dist/snip_occlusion.ankiaddon`. Submitting gives the add-on its
   permanent numeric ID and a page at
   `https://ankiweb.net/shared/info/<id>` — students install it with
   Tools → Add-ons → Get Add-ons… and that code. Put the code and page
   link in the README's Install section once you have them.
4. Updates: open your add-on's page → Edit → upload the new
   `.ankiaddon`. The ID stays the same and users get the update via
   Tools → Add-ons → Check for Updates. Anki reads `human_version`
   from `manifest.json` to show which version is installed, so bump it
   every time (step 1).
5. Listing tips: the title and description are what AnkiWeb search
   matches, so keep the key terms in them (image occlusion, slides, AI
   flashcards, OCR). Reviews on the page can't be replied to, so the
   description points people to GitHub for support.

## 5. Tag the release on GitHub

After merging to `main`, create a tag/release named after the version
(e.g. `v0.28.2`) on the GitHub website (Releases → Draft a new
release), paste that version's `CHANGELOG.md` entry as the notes, and
attach the built `.ankiaddon` so non-AnkiWeb users can download it.
The CI run for the merge commit also keeps the same file as its
`snip_occlusion.ankiaddon` artifact.

## 6. Tell people

AnkiWeb listings are found by search, not browsing, so a first
announcement helps: the *Add-ons* category on
<https://forums.ankiweb.net> (one post, link to the AnkiWeb page and
GitHub), and r/Anki on Reddit, which allows add-on announcements. Put
the AnkiWeb code in the README so people arriving from GitHub can
install in one step too.
