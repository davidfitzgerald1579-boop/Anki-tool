# Changelog

Each version below corresponds to a commit on the repository; the
installed version is shown as `human_version` in
`snip_occlusion/manifest.json`.

## v0.6.2 — 2026-08-30

- **Word detection rebuilt around dark strokes.** "Ink" now means pixels
  substantially darker than the local background, so BPP's yellow
  highlight bands (which wrap across line breaks and filled the gap
  between lines), pink callout backgrounds, and decorative dots are
  invisible to the detector — double-click no longer grabs paragraphs
  where highlights bridge lines. Works on highlighted words too.
- **Boxes can be grabbed and moved in every tool**: click-hold-drag a
  mask in the Box tool, a highlight in the Highlighter, etc. Drawing
  still starts anywhere else, including on top of other kinds.
- **The middle of a box always moves it.** Resize handles now live only
  on the border ring — on small boxes (like word boxes) they previously
  blanketed the whole surface, which made word boxes feel jumpy or dead
  when dragged.
- **Word boxes resize vertically like normal boxes**; only their left
  and right edges snap word-by-word.
- **Ctrl+D** copies an annotated picture of the last word-detection
  (line in blue, words in red, click in green) for easy bug reports.

## v0.6.1 — 2026-08-30

- Fixed double-click word occlusion grabbing a whole section on tightly
  spaced slides. BPP sets justified text so tightly that one line's
  descender tails share pixel rows with the next line's ascenders, so no
  empty row separates lines; line detection now finds the ink-density
  valley between lines instead of requiring an empty row, and the word
  box hugs the clicked word's own pixels vertically.

## v0.6.0 — 2026-08-30

- **See-through mode (T / 👁 button):** every box (masks and cover-ups)
  renders as an outline only, so the text underneath stays readable while
  editing. Toggle off to go back to opaque. View-only — cards and the
  saved image are unaffected.
- **Peek at one box:** right-click any box → "Peek underneath" to see
  through just that box; right-click → "Stop peeking" to restore it.

## v0.5.1 — 2026-08-30

- The left toolbar is now freely resizable: drag the divider between the
  toolbar and the canvas to any width (the ⟨ toggle still snaps it away
  entirely).
- Queued new cards are now shown PowerPoint-style: numbered slide
  thumbnails ("Card 1", "Card 2"…) with a border and soft shadow, the
  card's snips letterboxed inside on its background colour, and a ghost
  plus sign for empty cards. The background-colour button is now a swatch
  showing the card's actual colour. The queue also grows to use all spare
  toolbar height.

## v0.5.0 — 2026-08-30

- **Highlighter tool (H):** draws perfectly straight highlight bands with
  the same drag/resize/move behaviour as boxes. Painted in multiply mode,
  so the page takes the colour while the text stays dark and readable —
  like a real highlighter. Right-click a highlight for quick colours
  (yellow/green/pink/blue) or a custom one. Baked into the image; never
  becomes a card.
- **Double-click word occlusion:** double-click any word on the slide and
  a mask box appears covering exactly that word — full height, padded,
  and never touching a neighbouring word (hyphenated words count as one
  word). Dragging its side handles then snaps word-by-word: whole words
  are swallowed or released, never half-covered. Pure pixel analysis, no
  OCR involved.
- **Copy & paste boxes:** Ctrl+C copies the selected shapes, Ctrl+V
  pastes identical clones beside the originals — near but never
  overlapping — and repeated pastes chain sideways instead of stacking.
  Grouped selections keep their internal grouping as a fresh group.
- Fixed a latent group-id collision when grouping after undo/paste.

## v0.4.0 — 2026-08-30

- **Searchable cards (OCR).** When cards are added, the text on the
  finished image is read automatically (Windows' built-in OCR on Windows;
  Tesseract if installed) and stored invisibly in a new "Search Text"
  field, so deck-search add-ons and Anki's browser can find image-only
  cards. Existing Snip Occlusion note types are upgraded in place.
  A "Text preview" button shows exactly what was read, and an
  `ocr_corrections` config map fixes recurring misreads on all future
  cards.
- **New card queue.** Send a snip patch to its own brand-new card:
  drag it off the canvas onto a queued card (or right-click → "Send to
  new card"). Multiple snips stack on one card, on a background matching
  the slide's colour (changeable per card, 🎨). Queue cards show live
  thumbnails, can be added empty or deleted, and load into the editor
  for masking automatically after Add Cards (or on demand via "Start").
- The left toolbar can now be collapsed/expanded with a slim ⟨ / ⟩
  handle — useful in full screen.

## v0.3.0 — 2026-08-30

- Snip patches can now be parked **anywhere on the canvas**, including
  fully outside the slide, while you rearrange it. Adding cards warns if a
  patch was left outside the image (it would be cut off).
- **Fit** now includes parked patches, so nothing drifts off screen.
- New warm pastel theme for the whole dialog (Segoe UI-style font, cream
  background, coral accents, rounded controls) in place of the raw
  default-Qt look.
- Resize handles are live in **every** tool: hovering the selected box in
  the Box/Cover-up tool lets you reshape it without switching to Select.
- Group badges (numbered dots) replaced by **bold coloured outlines** —
  shapes in the same group share the same strong outline colour; the
  selection outline is now a thicker blue with a white halo.

## v0.2.0 — 2026-08-30

- Toolbar moved to a vertical left-hand panel.
- New snip-patch tool (**P**): cut out a region to keep as a movable,
  pixel-exact patch (never resampled, so no quality loss), baked above
  cover-up fills on export. Right-click snaps it back home.
- Masks are now fully opaque once placed.
- Fixed pixelated image display (Qt was using nearest-neighbour scaling;
  now smooth transformation).
- Image stays fit-to-window on resize/maximize until you zoom manually.
- Resize handles show only when hovering the selected shape.
- Minimize/maximize window buttons and F11 full-screen toggle.
- Oval tool removed (legacy ellipse notes still render on cards).

## v0.1.0 — 2026-08-29

- First release: clipboard-first occlusion editor with drag-threshold
  moves, shift-click-safe selection, move-one-not-all dragging, explicit
  id-based grouping, cover-up (majority-colour text eraser), "Hide All,
  Guess One" / "Hide One, Guess One" card generation, and cards that
  render on all Anki clients with no add-on needed at review time.
