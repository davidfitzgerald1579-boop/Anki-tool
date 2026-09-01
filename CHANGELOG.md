# Changelog

Each version below corresponds to a commit on the repository; the
installed version is shown as `human_version` in
`snip_occlusion/manifest.json`.

## v0.27.1 — 2026-09-01

- **The Suggested Cards view now matches the Write Card view's
  shape**: the source text sits at the top and the suggested cards
  underneath. The source pane defaults to exactly the height its
  text needs (the suggestions take the rest and scroll) and re-fits
  when a new snip or lesson arrives; drag the divider to override it
  for the current batch, just like the Write Card view.

## v0.27.0 — 2026-09-01

- **Reveal source is now a split view: the slide AND the highlighted
  source text.** Opening 🔍 Reveal source on a card back now shows
  two panes below the card — the full snip on the left, and on the
  right the source text with the sentences the card most likely came
  from highlighted (the same 🔎 trace as the Suggested Cards page:
  yellow for question/answer, orange for the Notes line). Image /
  Text / Both buttons switch the view; Both (split screen) is the
  default, and the panes stack on narrow screens. The highlights are
  computed against the card as you actually added it — corrections
  made in the Use → window are traced, not the AI's original — and
  baked into a new `Source Text` field at add time, so they render on
  AnkiDroid and AnkiMobile with nothing installed on the device.
- **Cards from pasted text get Reveal source too.** A card generated
  from a pasted lesson (which has no snip) now stores the passage it
  was written from: Reveal source shows "No image to display" in the
  image pane and the highlighted text in the text pane.
- Redeploying a card from the Added cards tray re-highlights the
  source text against the corrected card. Existing note types are
  upgraded the same way as v0.26 (one consent prompt on a synced
  collection; the stock v0.26 reveal block is swapped for the new
  one, custom template edits stay untouched, and a deleted block
  stays deleted). `text_card_attach_source: false` switches all of
  it off.

## v0.26.0 — 2026-09-01

- **"Reveal source" on AI text cards.** A card made from a suggested
  flashcard (Use →) now carries the full snip it was generated from:
  while reviewing, the card back gains a **🔍 Reveal source** button
  that opens the whole slide, for when the answer alone isn't enough
  context. Built with plain `<details>`/`<summary>`, so it works on
  AnkiDroid and AnkiMobile with nothing installed on the device. The
  snip is written to the media collection once per slide, when the
  first card citing it is added — skipped suggestions cost nothing —
  and every sibling card shares the file (so Shift+Delete during
  review can still remove the whole family). Focused cards (✨ from
  highlighted text) carry the snip too — always the slide whose text
  is on display, even across failed generations, snips landing
  mid-run, and the ↻ fallback to a previous snip's remembered text;
  cards from a pasted lesson have no snip and show no button.
  Redeploying a card from the Added cards tray keeps its source. The
  "Snip Occlusion Basic" note type gains a `Source` field; existing
  note types are upgraded in place — the reveal block is appended to
  the back template without touching any customisation, and only in
  the same pass that adds the field, so deleting the block from your
  template later sticks. Because adding a field is a schema change,
  a synced collection shows Anki's standard full-sync confirmation
  once before the upgrade; declining adds the card without a source.
  Switch off with `text_card_attach_source` in the config — the note
  type is then left untouched as well.

## v0.25.0 — 2026-08-31

- **Accent-coloured words are flagged to the AI as key terms.** Slides
  often print the crucial words in a different colour; the snip is now
  re-read with word positions, each word's ink colour is sampled, and
  words that clearly differ from the page's dominant ink — on lines
  that mix both colours, so all-accent headings don't trigger — are
  handed to the model as terms the cards must incorporate. Adjacent
  accent words are joined into phrases. Best-effort: if the OCR
  backend can't give word boxes, generation continues without the
  hint. Sensitivity via `ocr_accent_threshold` in the config (0 turns
  it off).
- **B / I / U now properly toggle off on a second click** in the
  Suggested Cards Use→ window and the Write Card tab. The on/off state
  is read from the selected text itself, so it also works when the
  selection was dragged right-to-left.

## v0.24.0 — 2026-08-31

- **Choose how many cards to make from highlighted text.** Right-click
  a selection in the source pane: "✨ Make a card from this selection"
  still writes one, and a new "✨ Make several cards from it…" submenu
  asks for 2–8 cards about that passage. In 🖍 Pick mode a selector
  appears next to ✨ Make cards: "1 per pick" (the default, one card
  per highlighted passage) or a number 1–8 for that many cards in
  total across the picked passages. The prompt tells the model the
  EXACT number either way.

## v0.23.1 — 2026-08-31

- **The Added cards tray now moves with the view**: bottom of the
  sidebar in the Image Editor (below the tools), top of the sidebar —
  directly under "📋 Load new snip" — in the Suggested Cards and
  Write Card views.
- **Removed the "📝 Text card" sidebar button** (the Write Card tab at
  the top does the same job) and **the "🔍 Text preview" button** (the
  OCR text is always visible under the Suggested Cards view now); its
  Settings checkbox is gone too.

## v0.23.0 — 2026-08-31

- **The Suggested Cards and Write Card views now show a minimal
  sidebar**: just "📋 Load new snip" and the Added cards list — no
  drawing tools, no queue. Everything comes back when you switch to
  the Image Editor. (The existing keep/hide setting still hides the
  sidebar entirely if you prefer.)
- **Trim the Image Editor sidebar in ⚙ Settings**: new checkboxes let
  you switch off sections you don't use — New card queue, See-through,
  Text preview, Shortcuts help. Untick to hide, re-tick any time; the
  choice is saved and only affects the Image Editor tab.
- **Added cards are now readable** — each entry is a slide-style
  preview card showing the question and answer text (like the queue's
  PowerPoint thumbnails, but for text), with a count in the heading
  and newest first. Click a card to edit & redeploy or delete it.
- **The sidebar can be dragged out to half the window** (the old 400px
  cap is gone), so the added cards on the left read as large and
  clearly as the suggested cards on the right.

## v0.22.0 — 2026-08-31

- **Added cards can be fixed after the fact.** Every text card you add
  now appears under "Added cards" in the sidebar (newest first). Click
  one to reopen it: edit and press **Redeploy** — the corrected note is
  added first, then the old one is deleted, so nothing can be lost —
  or **🗑 Delete card** to remove it from the deck. The entry keeps
  tracking the replacement, so a card can be redeployed repeatedly.
  (The list is per Anki session.)
- **Right-click a selection in the source text → "✨ Make a card from
  this selection".** The AI writes a card that specifically teaches the
  passage you highlighted, using the rest of the slide only as context.
- **🖍 Pick mode** (button beside the source-text heading): turn it on,
  drag over each sentence you want a card about — every selection stays
  marked in blue — then press **✨ Make cards (N)** and the AI writes
  exactly one card per picked passage. Focused cards append to the
  current suggestions, carry the usual verdict buttons and 🔎 trace,
  and count in the model bake-off.

## v0.21.2 — 2026-08-31

- **The OCR text no longer waits for the AI.** It used to appear only
  when the whole prefetch (OCR + card generation) finished. Now the
  moment a snip's text is read — seconds after the image loads — it
  shows up in the Suggested Cards source pane (embedded and popped-out)
  AND the Write Card source pane, while the LLM keeps generating in
  the background. A pasted-lesson run's source text is never
  clobbered, and a snip that's been replaced by a newer one is
  ignored.

## v0.21.1 — 2026-08-31

- **Pasting into card fields is now always plain text.** Copying from
  the source text pane (or anywhere) used to drag its colours and 🔎
  highlight backgrounds onto the card. Pasted text now takes on the
  Front/Back/Notes field's own font and style at the cursor; the
  B/I/U toolbar still formats normally afterwards.

## v0.21.0 — 2026-08-31

- **Hover tooltips are finally readable** — crisp dark-on-cream, in
  every add-on window. Root cause found: Qt draws a tooltip in its own
  top-level window parented to the *screen*, so the `QToolTip` styling
  in the dialog's stylesheet never reached it and Anki's (dark)
  app-wide look won. The add-on now intercepts the tooltip event
  itself and shows its own styled tip for widgets inside its windows —
  Anki's global tooltips are untouched. The same dead-styling
  assumption was fixed elsewhere: the word-detection debug
  notification used a native tooltip too and now uses the cream
  notification.
- **"Cards:" selector on the Suggested Cards view** (next to the ↶
  undo button): choose 1–8 suggested cards per slide, default 4. The
  choice is saved and applies from the next generation — press ↻ to
  redo the current one with the new count.

## v0.20.0 — 2026-08-31

- **✎ Fix: correct a suggested card purely to teach the AI.** When the
  style is right but the content is wrong (confused concepts, a missed
  distinction), click ✎ Fix on the suggestion, edit the Front/Back/
  Notes, and save "Teach corrected version". YOUR corrected card
  becomes a kept example for future generations — no flashcard is
  added to your deck. The ↶ undo button reverses it like any other
  verdict.
- In the bake-off scoreboard, a correction counts as a new "fixed"
  verdict against the model that generated the card: it lowers that
  model's kept-rate and shows as "N needed correcting" next to it.

## v0.19.1 — 2026-08-31

- **Write Card: the source text pane auto-sizes to the whole text** —
  down to the last line, no scrolling — compressing the fields below as
  needed. It re-fits on every new snip/lesson and on window resizes; a
  manual drag of the divider takes over until the next text arrives.
  (If the text is taller than the window physically allows, the pane
  takes all it can and scrolls for the remainder.)
- **Correcting a suggestion now teaches the corrected version.** When
  you Use → a card, fix its content in the window, and add it, the
  learning loop replaces the model's original with YOUR corrected card
  in the kept examples — so the loop learns the right distinction, not
  the confusion. (Adding the card unchanged leaves things as before.)

## v0.19.0 — 2026-08-31

- **✋ Grab tool.** Click and hold to drag the image around the window
  and park it wherever suits your screen — made for split-screen work.
  (Middle-drag still pans in every tool.)
- **Three clean views.** The top toggle is now 🖼 Image Editor /
  ✨ Suggested Cards / 📝 Write Card. Suggested Cards shows the AI
  suggestions with the source (OCR/pasted) text underneath; Write Card
  shows the source text above the Front/Back/Notes fields. The ⧉
  pop-out now opens the Suggested Cards page.
- **🔎 highlights inline.** Clicking 🔎 no longer opens a popup — the
  source text below simply lights up (yellow = question/answer,
  orange = Notes) and scrolls to the first match; the caption warns in
  red when the Notes match nothing.
- **Readable popups everywhere.** The transient notices ("Card added",
  etc.) no longer use Anki's dark bubble — they're now crisp dark-on-
  cream text matching the rest of the add-on.

## v0.18.2 — 2026-08-31

- **The 🔎 viewer now traces the Notes line separately** — notes are
  where hallucinations concentrate. The card's Notes are shown in the
  viewer header, the sentences they came from are highlighted in
  ORANGE (question/answer matches stay yellow), and when nothing in
  the source matches the Notes a red warning says so outright: likely
  invented — verify or flag with ⚠ Ref.

## v0.18.1 — 2026-08-31

- **Half-screen friendly suggestion rows.** The six row buttons now sit
  in a compact two-wide, three-tall grid on the right (Use → / Skip,
  ★ Great / ✗ Bad, ⚠ Ref / 🔎), so the card text keeps most of the
  width — no more one-word-per-line cards when the window is snapped to
  half the screen.

## v0.18.0 — 2026-08-31

- **🔎 Where did this card come from?** Every suggested card now has a
  🔎 button that opens the full source text with the sentences the
  card most likely came from highlighted — so references and facts can
  be checked in one click. Matching is computed locally by word
  overlap: the model is never asked, so generation speed is completely
  unaffected. When no sentence matches closely, the viewer says so —
  a strong hint the card deserves suspicion (or a ✗/⚠).

## v0.17.0 — 2026-08-31

- **Invented references get caught.** Every citation-shaped string in a
  suggested card (case names, years, Acts, sections, Articles) is now
  checked against the source text: a citation that isn't actually in
  the source strips the Notes field automatically, and shows a red
  "⚠ not in the source text" warning when it sits in the question or
  answer. Even a real case with an invented year is caught.
- **⚠ button: flag an invented reference.** Tell the add-on exactly
  which reference the model made up (pre-filled with the detected
  citation) — it goes on a permanent local blocklist and is stripped
  from every future card, and the card counts as Bad for the learning
  loop. Deliberately NOT shown to the model: repeating a fabricated
  citation in the prompt could teach a small model to produce it.
- **Suggestion text is selectable.** Click-drag over any suggested
  card's preview to select and copy its text — for checking references
  against the source side by side.
- The prompt now instructs: cite only what appears word-for-word in
  the source; if the source names no authority, cite nothing.

## v0.16.0 — 2026-08-31

- **Pop-out Text Editor.** The ⧉ button next to the view toggle opens
  the full Text Editor — suggestions, verdicts, paste-text, undo, card
  fields — in its own resizable window, and the main window returns to
  the Image Editor. Snap the popped-out editor to one half of the
  screen and your source material to the other to check references
  while reviewing. New snips feed its suggestions too; closing it warns
  about unsaved card text.

## v0.15.2 — 2026-08-31

- **Fixed: the smaller model writing cards about topics you never
  pasted.** Small models were treating the style examples in the prompt
  (drawn from the author's own deck) as content to write about. Three
  defences: the prompt is restructured so the source text comes last —
  right where the model anchors — with the examples clearly fenced off
  as "other, unrelated topics"; positives are capped at 4 total (live
  verdicts take priority over seed examples, which also trims the
  prompt for speed); and an on-topic filter drops any card sharing no
  substance with the source text (failing open so a batch is never
  emptied by mistake). Also makes the bake-off comparison fairer to the
  smaller model.

## v0.15.1 — 2026-08-31

- **Simpler model choice in ⚙ Settings.** Three plain options: use the
  smaller, faster model (llama3.2:3b) · use the bigger model
  (llama3.1:8b) · alternate between the two at random and keep score.
  The scoreboard and all its data stay. Alternation is now random
  rather than strict turn-taking.
- **Clarified in the UI: both models always learn from all verdicts.**
  Kept/flagged example cards are shared style memory, not tied to the
  model that wrote them — so feedback given during a bake-off improves
  whichever model you end up choosing.

## v0.15.0 — 2026-08-31

- **Model bake-off.** Turn it on in ⚙ Settings and generations
  alternate between two models (default `llama3.1:8b` vs
  `llama3.2:3b`), with each suggestion remembering which model wrote
  it. Your Use/★/Skip/✗ clicks (undo included) score the models, and
  generation times are recorded too. The scoreboard in ⚙ Settings shows
  each model's kept-rate and average speed — and states whether the
  quality gap is statistically meaningful yet or the faster model is
  simply winning. Pick your model with evidence, not vibes.

## v0.14.2 — 2026-08-31

- **The model now leaves a CPU core free while generating**
  (`qgen_leave_cores_free`, default 1), so Anki and the rest of the
  laptop stay responsive during background generation. Raise it if the
  machine still feels sluggish while the AI works; set `0` for maximum
  generation speed.

## v0.14.1 — 2026-08-31

- **Undo for suggestion verdicts.** The new ↶ button brings back the
  last card you Skipped, ★'d or ✗'d — restoring it to its place in the
  list and erasing the verdict from the learning loop. Multi-level:
  keep clicking to walk further back. (Cleared when a new batch of
  suggestions loads.)
- **Closing a "Use →" window returns the card.** If you open a
  suggestion with Use → and then close its window without adding, the
  card automatically reappears in the suggestions list and the "kept"
  verdict is forgotten — so clicking ✗ Bad afterwards is what the
  learning loop remembers, not your initial Use.

## v0.14.0 — 2026-08-31

- **Cards from pasted text.** The suggestions panel's new "📄 Paste
  text…" button takes a whole lesson/element text. It is split into
  sections at its headings and the cards stream into the panel as each
  section finishes — first cards within about a minute, review with the
  usual Use/Skip/Great/Bad while the rest generate. The ↻ button
  becomes ■ during a run to stop it. Section-by-section generation
  keeps prompts small, so the local model stays fast and thorough
  instead of being overloaded by one giant prompt.

## v0.13.2 — 2026-08-31

- **Readable tooltips.** Hover text was dark-on-black and near
  invisible; tooltips now use a cream background with dark text,
  matching the rest of the UI.

## v0.13.1 — 2026-08-31

- **Suggestions open at full height.** The suggestions pane now sizes
  itself to show every suggested card with no scrolling, pushing the
  Front/Back/Notes boxes down as needed. A splitter handle under the
  pane drags up to shrink it (it scrolls internally once shrunk), and
  it re-fits automatically as cards are used or dismissed — until you
  drag it yourself, which takes over for that batch.

## v0.13.0 — 2026-08-31

- **Text Editor built into the main window.** Two buttons at the top —
  🖼 Image Editor (default) / 📝 Text Editor — switch the editing area
  in place, no separate window. The sidebar stays put (or hides, via
  the new ⚙ Settings button — your choice).
- **Suggestions appear on their own.** The Text Editor shows the
  AI-suggested cards for the current snip at the top automatically —
  a "generating…" note while the model is still working, cards as soon
  as it's done. No button to press; ↻ regenerates on demand.
- **Clearer verdict buttons**, left to right: **Use →** (make this
  card), **Skip** (don't want it, teaches nothing), **★ Great** (not
  using it, but write more like this), **✗ Bad** (write less like
  this). No more squinting at thumbs.
- "Use →" still opens the card in its own small window to tweak and
  add; that window is now just the card fields. Ctrl+Shift+T outside
  the main window opens the same standalone window.

## v0.12.1 — 2026-08-31

- **👍 button on suggestions.** For "not using it, but great card":
  saves the card as a positive style example without opening it — the
  full verdict set is now Use → / 👍 / ✕ (neutral) / 👎.

## v0.12.0 — 2026-08-31

- **The AI learns your card taste.** Suggestions now have three
  verdicts: "Use →" (write more like this), "✕" (neutral discard —
  teaches nothing; the slide may simply not be card-worthy), and "👎"
  (badly written — write less like this). Kept and flagged cards are
  folded into future prompts as form-to-copy / habits-to-avoid, and the
  positive list is seeded from the author's real SQE deck so the very
  first generation already imitates it. Configurable via
  `qgen_feedback` / `qgen_feedback_examples`; everything stays local.
- **Rewritten generation prompt.** Four suggestions by default instead
  of eight (`qgen_max_cards`), and the model is told to write fewer —
  or none — when a slide has little exam-relevant material. Questions
  may now run to three sentences, with short scenario-style questions
  encouraged ("A pays B less than the agreed sum. B accepts. Is this
  good consideration?"); answers state the legal position precisely
  ("Yes, but…", numbered procedure steps, statute/case references).
- **Notes on suggestions.** The model can attach brief context (an
  authority, a caveat) to a card; it shows small under the answer in
  the suggestion list and prefills the Notes field on "Use →".

## v0.11.0 — 2026-08-31

- **Suggestions are pre-generated.** The moment a snip lands in the
  editor, OCR and the AI model start working in the background — by the
  time you open the text card dialog and click "✨ Suggest cards", the
  drafts usually appear instantly. Configurable via `qgen_prefetch`.
- **Delete suggestions.** Each suggestion row now has a ✕ button next
  to "Use →", so you can discard the duds as you work down the list.
- **Fewer model-load waits.** Ollama is now asked to keep the model in
  RAM between requests (`qgen_keep_alive`, default 30 minutes), so only
  the first generation of a study session pays the load time.

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
