# Changelog

Each version below corresponds to a commit on the repository; the
installed version is shown as `human_version` in
`snip_occlusion/manifest.json`.

## v0.10.0 — 2026-08-30

- **AI card suggestions are now free, private, and fully open source.**
  "✨ Suggest cards" no longer uses the paid Claude API — it talks to an
  open-source model running on your own computer via
  [Ollama](https://ollama.com) (default: `llama3.1:8b`; one-time setup:
  install Ollama, then `ollama pull llama3.1:8b`). No account, no API
  key, no per-request cost, and the slide text never leaves your
  machine. Any OpenAI-compatible server (LM Studio, llama.cpp, Jan,
  vLLM) is supported as an alternative via `qgen_provider`. The
  `anthropic_api_key` and old `qgen_model` settings are replaced by the
  new `qgen_*` settings — see the config help.

## v0.9.1 — 2026-08-30

- **Double-click erases in the Cover-up tool.** With Cover-up (C) active,
  double-clicking a word now covers up exactly that word — filled with
  the background colour and baked into the image — instead of occluding
  it with a mask. (Matches the Highlighter's double-click behaviour from
  v0.8.0; every other tool still occludes on double-click.)

## v0.9.0 — 2026-08-30

- **AI-suggested cards from your snip.** In the text card dialog, the
  "✨ Suggest cards" button sends your most recent snip's OCR text to the
  Claude API (with your own API key, set in the add-on config) and shows
  drafted question/answer pairs — e.g. slide text "Private members bills
  are brought forward by individual MPs" becomes Q: "Who can bring
  forward private members' bills?" / A: "Individual MPs". Pick a
  favourite with "Use →": it opens prefilled in its own window to tweak
  and add, while the suggestion list stays behind so you can take one,
  two, or three. Generation runs in the background; the slide text is
  sent to Anthropic only when you click the button.

## v0.8.0 — 2026-08-30

- **Double-click highlights in the Highlighter tool.** With the
  Highlighter (H) active, double-clicking a word paints a snug highlight
  over exactly that word instead of occluding it. Side handles still
  extend it word-by-word; never becomes a card.
- **Simple text cards (Ctrl+Shift+T).** A deliberately minimal dialog
  for writing a card in your own words: Deck, Front, Back, Notes (shown
  small under the answer), with bold/italic/underline and font size —
  nothing else. A "Copy text from previous snip" button drops the OCR
  text of your most recent snip onto the front to rephrase. Also
  reachable from the 📝 button in the occlusion editor's toolbar.

## v0.7.2 — 2026-08-30

- **Word detection now understands multiple backgrounds on one slide**
  (table layouts). Double-clicking white text on a pink header bar used
  to select the whole bar: against the page-wide white background the
  pink bar itself read as one slab of "ink" and the white letters were
  invisible. Detection now samples the background AT the click, grows
  that background's region to its edges, detects whether the text is
  darker or lighter than it (white-on-pink flips polarity), and analyzes
  only within the region. Dark text on grey table cells works the same
  way; ordinary slides behave exactly as before.

## v0.7.1 — 2026-08-30

- **Delete ALL cards from an image.** While reviewing, press Shift+Delete
  (or right-click → "Delete ALL cards from this image…") to remove every
  card generated from the current card's slide — after a confirmation
  showing the count and filename, and undoable with Ctrl+Z. Works on
  cards made by other occlusion tools too (e.g. Image Occlusion
  Enhanced): the shared slide image is identified as the file referenced
  by the most notes, so per-card mask files don't confuse it.

## v0.7.0 — 2026-08-30

- **Edit existing cards.** The note editor (Browse, or Edit during a
  review) now has a ✂ button that reopens a Snip Occlusion card's image
  with all its boxes, groups and settings exactly as saved. Rework the
  layout and press Save Changes: every sibling card sharing that slide
  is updated in place (keeping its review history), new boxes become new
  cards, and cards whose boxes were deleted are removed only after a
  confirmation. New cover-ups/highlights/patches are baked into the
  shared image, and the searchable text is re-read.
- **Delete a card mid-review.** Press the Delete key (or right-click the
  card → "Delete this card") while reviewing to remove the current card
  instantly — undoable with Ctrl+Z.

## v0.6.3 — 2026-08-30

- Fixed pink/coloured text losing its first letters in double-click word
  boxes. Coloured text is fainter than black (and subpixel antialiasing
  lightens it further), so some strokes fell below the fixed darkness
  bar. Word detection now runs twice: a strict pass finds the line and
  measures how dark its ink actually is, then an adaptive pass rescans
  with a threshold tuned to that text colour. The threshold keeps a
  floor that always excludes highlight bands and callout backgrounds.

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
