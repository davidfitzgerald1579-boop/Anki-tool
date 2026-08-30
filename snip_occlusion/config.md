### Snip Occlusion configuration

- `drag_threshold_px`: how far (in image pixels) the cursor must travel
  before a click on a shape turns into a move. Raise this if you still nudge
  shapes by accident; lower it if moving feels laggy. Default: `5`.
- `mask_fill`: colour of ordinary masks in the editor and on cards.
  Default: `"#FFEBA2"`.
- `target_fill`: colour of the highlighted target mask on cards.
  Default: `"#FF7E7E"`.
- `highlight_fill`: default highlighter colour. Light tones work best —
  the highlight multiplies with the page, so the background takes the
  colour while text stays dark. Default: `"#ffe94d"`.
- `erase_color_mode`: default fill for new cover-up boxes. `"majority"`
  uses the slide's overall majority colour (recommended for BPP slides);
  `"local"` samples the background immediately around each box. You can
  always override a single box by right-clicking it. Default: `"majority"`.
- `shortcut_open`: global shortcut for opening the dialog from the main
  window. Default: `"Ctrl+Shift+O"`.
- `shortcut_text_card`: shortcut for the simple front/back text card
  dialog. Default: `"Ctrl+Shift+T"`.
- `close_after_add`: close the dialog after adding cards instead of
  clearing it for the next snip. Default: `false`.
- `default_mode`: `"hag1"` (Hide All, Guess One) or `"hog1"`
  (Hide One, Guess One). Default: `"hag1"`.
- `nudge_step` / `nudge_step_large`: pixels moved by arrow keys /
  Shift+arrow keys. Defaults: `1` / `10`.
- `ocr_backend`: engine used to read the card image's text into the
  hidden, searchable "Search Text" field. `"auto"` (default) uses the OCR
  built into Windows 10/11, falling back to Tesseract if installed;
  `"windows"`, `"tesseract"`, or `"none"` force a choice.
- `tesseract_path`: full path to `tesseract.exe` if it isn't on PATH.
- `tesseract_user_words`: optional path to a text file of extra
  vocabulary (one word per line, e.g. legal terms) to bias Tesseract.
- `ocr_corrections`: map of recurring OCR misreads to their fixes,
  applied to every future card, e.g. `{"K80": "KBD", "UTlAC": "UTIAC"}`.
  Use the editor's "Text preview" button to find misreads worth adding.
- `anthropic_api_key`: your Claude API key (from console.anthropic.com),
  used only by the text card dialog's "Suggest cards" button. When you
  click it, your snip's OCR text is sent to Anthropic's API to draft
  question/answer cards; nothing is sent otherwise. Default: empty
  (feature off).
- `qgen_model`: the Claude model used for card suggestions. Default:
  `"claude-opus-5"` (highest quality; a slide costs roughly a cent).
- `qgen_max_cards`: maximum suggested cards per slide. Default: `8`.

Note: `mask_fill` and `target_fill` are written into the note type's CSS
when the note type is first created. To restyle existing cards, edit the
"Snip Occlusion" note type's styling directly in Anki (`.io-mask` and
`.io-target`).
