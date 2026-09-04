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
  The OCR text under the Suggested Cards view shows what is being read.
- `ocr_accent_threshold`: slides often print key terms in a different
  colour; words whose ink colour differs from the page's dominant ink
  by more than this (RGB distance, 0–441) — on lines that mix both
  colours — are flagged to the AI as key terms to work into the cards.
  Lower = more sensitive. `0` turns the feature off. Default: `110`.
- `qgen_provider`: where the AI behind "Suggest cards" runs. Easiest
  changed in the ⚙ Settings window, which also has a Fetch-models list
  and a Test-connection button.
  - `"ollama"` (default): a free, open-source model on your own
    computer via [Ollama](https://ollama.com) — no account, no API key,
    no cost, and (as long as `qgen_ollama_url` is this computer) the
    slide text never leaves your machine. Slow on a laptop CPU
    (typically a minute or more per slide).
  - A hosted service: `"groq"`, `"cerebras"`, `"openrouter"`,
    `"together"`, `"fireworks"`, `"deepinfra"`, `"huggingface"`,
    `"ollama_cloud"` or `"mistral"`. The same open-source models run on
    that company's GPUs — tens of times faster — and you pay per use
    (a fraction of a cent per slide; several have free tiers). Needs
    an API key in `qgen_api_key`. **The slide or lesson text is sent
    to that service** (never the image). See
    [docs/hosted-llm.md](https://github.com/davidfitzgerald1579-boop/Anki-tool/blob/main/docs/hosted-llm.md) for how this works,
    what it costs and how to set it up.
  - `"openai_compatible"`: any other server exposing the OpenAI
    chat-completions API — LM Studio, llama.cpp, Jan, vLLM on this
    machine, or a GPU server you rent and run yourself.
- `qgen_model`: the model to use, named the way the chosen provider
  names it. Default: `"llama3.1:8b"` for Ollama (download it once
  with `ollama pull llama3.1:8b`; other good choices: `"qwen2.5:7b"`,
  `"mistral:7b"`, or `"llama3.2:3b"` on low-RAM machines). Each hosted
  preset has its own default and suggestions in the Settings window;
  the Fetch button lists everything the server actually offers.
- `qgen_ollama_url`: the Ollama server address. Default:
  `"http://localhost:11434"`. Point it at another machine on your
  network (or a server you rent) to run the model there; put an
  authenticating reverse proxy or Tailscale in front of a server on
  the internet and pass its token in `qgen_api_key`.
- `qgen_openai_base_url`: base URL for `"openai_compatible"` servers,
  including any `/v1` suffix. Default: `"http://localhost:1234/v1"`
  (LM Studio's default). Hosted presets ignore this — their URLs are
  built in.
- `qgen_api_key`: the Bearer token for the provider `qgen_provider`
  is set to — hosted services need one; local servers normally don't;
  Ollama gets it too when set (Ollama Cloud, or a proxy in front of a
  remote Ollama). Stored in this add-on's config file on your
  computer, like every other setting. If left empty, the hosted
  presets also look for the usual environment variable
  (`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`, ...). Default:
  empty.
- `qgen_api_keys`: written by the ⚙ Settings window — one key per
  provider you have entered one for (`{"groq": "...", "openai_compatible":
  "..."}`), so switching between services doesn't lose them and a key
  entered for one service is never sent to another. `qgen_api_key`
  wins for the current provider. Default: `{}`.
- `qgen_max_cards`: maximum suggested cards per slide (1–8). Default:
  `4`. Easiest changed via the "Cards:" selector at the top of the
  Suggested Cards view. The model is told to write fewer (or none)
  when a slide has little exam-relevant material, rather than padding
  with filler.
- `qgen_feedback`: learn your card taste from the suggestion buttons.
  "Use →" saves a card as a positive style example, "👎" as a negative
  one, and "✕" (a neutral discard) deliberately saves nothing. Recent
  examples of both are folded into future prompts as form-to-copy /
  habits-to-avoid, alongside a rotating sample of a bundled seed drawn
  from the author's real deck. All data stays on your machine in
  `user_files/qgen_feedback.json` (survives add-on updates). Default:
  `true`.
- `qgen_feedback_examples`: roughly how many examples of each kind go
  into a prompt. More examples steer harder but generate slower on CPU.
  Default: `4`.
- `qgen_timeout_seconds`: how long to wait for the model. Default:
  `300` — the first request after Ollama loads a model can be slow.
  (Replies are also capped at a generous number of tokens per card,
  so a small local model that starts rambling is cut off after a
  couple of minutes instead of running to this timeout.)
- `qgen_prefetch`: start generating suggestions in the background the
  moment a snip lands in the editor, so "Suggest cards" is (usually)
  instant. Default: `true`. Set to `false` if the background generation
  makes drawing feel sluggish on a slow machine — the button then
  generates on demand. Note the suggestions come from the snip as
  loaded; cover-ups drawn afterwards don't re-run generation (delete
  unwanted suggestions with their ✕ button instead).
- `text_editor_sidebar`: what the left toolbar does when you switch the
  main window to the Suggested Cards or Write Card views. `"keep"` (default) leaves it
  visible (trimmed to Load new snip + Added cards); `"hide"` tucks it
  away entirely until you switch back to the Image Editor. Also
  settable via the ⚙ button in the main window.
- `sidebar_hidden`: Image Editor sidebar sections you have switched
  off, any of `"queue"` (New card queue), `"see_through"`,
  `"shortcuts"`. Default: `[]` (show everything). Easiest changed via
  the checkboxes in the ⚙ Settings window; only affects the Image
  Editor tab.
- `qgen_bakeoff`: alternate generations between the models in
  `qgen_bakeoff_models` and score each by your Use/★/Skip/✗ verdicts
  (plus generation times). The scoreboard — including whether the
  quality difference is statistically meaningful yet — lives in the ⚙
  Settings dialog, which is also the easy on/off switch ("Alternate
  at random with:"). Default: `false`.
- `qgen_bakeoff_models`: the contenders when the bake-off is on, named
  the way the current provider names them (both must be on the same
  provider). Default: `["llama3.1:8b", "llama3.2:3b"]` — pull each
  with `ollama pull <name>` first.
- `qgen_leave_cores_free`: CPU cores the model must leave alone while
  generating (Ollama on this computer only; a remote server has its
  own core count). Default `1`, so Anki and the rest of the laptop
  stay responsive during background generation; raise it if the
  machine still feels sluggish, or set `0` to let the model use every
  core (slightly faster generation).
- `qgen_keep_alive`: how long Ollama keeps the model loaded in RAM
  after a request (e.g. `"30m"`, `"2h"`; `-1` for as long as Ollama
  runs). Default: `"30m"`. Longer means fewer model-load waits during a
  study session, at the cost of the RAM staying used. Not sent to
  Ollama Cloud.
- `text_card_attach_source`: save the source behind each text card
  made from an AI suggestion (Use →). While reviewing, the card back
  then has a "🔍 Reveal source" button that opens a split view below
  the card: the whole slide on one side, and on the other the source
  text with the sentences the card most likely came from highlighted
  (the same 🔎 trace as the Suggested Cards page, computed against
  the card as you added it). Image / Text / Both buttons switch the
  view. The snip is stored once per slide in Anki's media collection,
  however many cards cite it; cards from pasted text have no snip, so
  their image pane says "No image to display" and the text pane shows
  the highlighted passage. Set to `false` if you don't want any of
  this in your collection — the note type is then left entirely
  untouched too. Adding the Source field to a note type
  created by an older version is a schema change, so on a synced
  collection the first card added after updating shows Anki's
  standard "requires a full upload" confirmation once; declining
  simply adds the card without a source, and you'll be asked again
  another time. Deleted the "Reveal source" block from your card
  template? It stays deleted — the add-on installs a block only into
  a template that has never had one (upgrading its own stock block
  in place when versions change), never into one you stripped it
  from. Default: `true`.

Note: `mask_fill` and `target_fill` are written into the note type's CSS
when the note type is first created. To restyle existing cards, edit the
"Snip Occlusion" note type's styling directly in Anki (`.io-mask` and
`.io-target`).
