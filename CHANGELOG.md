# Changelog

Each version below corresponds to a commit on the repository; the
installed version is shown as `human_version` in
`snip_occlusion/manifest.json`.

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
