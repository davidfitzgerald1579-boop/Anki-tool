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
- `qgen_provider`: how the text card dialog's "Suggest cards" button
  reaches an AI model. `"ollama"` (default) talks to a free, open-source
  model running on your own computer via [Ollama](https://ollama.com) —
  no account, no API key, no cost, and the slide text never leaves your
  machine. `"openai_compatible"` talks to any server exposing the OpenAI
  chat-completions API (LM Studio, llama.cpp, Jan, vLLM, ...).
- `qgen_model`: the model to use. Default: `"llama3.1:8b"` (download it
  once with `ollama pull llama3.1:8b`). Other good choices:
  `"qwen2.5:7b"`, `"mistral:7b"`, or `"llama3.2:3b"` on low-RAM
  machines.
- `qgen_ollama_url`: the Ollama server address. Default:
  `"http://localhost:11434"`. Point it at another machine on your
  network to run the model on a more powerful PC.
- `qgen_openai_base_url`: base URL for `"openai_compatible"` servers,
  including any `/v1` suffix. Default: `"http://localhost:1234/v1"`
  (LM Studio's default).
- `qgen_api_key`: optional Bearer token for `"openai_compatible"`
  servers that require one; local servers normally don't. Unused by
  Ollama. Default: empty.
- `qgen_max_cards`: maximum suggested cards per slide. Default: `8`.
- `qgen_timeout_seconds`: how long to wait for the model. Default:
  `300` — the first request after Ollama loads a model can be slow.
- `qgen_prefetch`: start generating suggestions in the background the
  moment a snip lands in the editor, so "Suggest cards" is (usually)
  instant. Default: `true`. Set to `false` if the background generation
  makes drawing feel sluggish on a slow machine — the button then
  generates on demand. Note the suggestions come from the snip as
  loaded; cover-ups drawn afterwards don't re-run generation (delete
  unwanted suggestions with their ✕ button instead).
- `qgen_keep_alive`: how long Ollama keeps the model loaded in RAM
  after a request (e.g. `"30m"`, `"2h"`; `-1` for as long as Ollama
  runs). Default: `"30m"`. Longer means fewer model-load waits during a
  study session, at the cost of the RAM staying used.

Note: `mask_fill` and `target_fill` are written into the note type's CSS
when the note type is first created. To restyle existing cards, edit the
"Snip Occlusion" note type's styling directly in Anki (`.io-mask` and
`.io-target`).
