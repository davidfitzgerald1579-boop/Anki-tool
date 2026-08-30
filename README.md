# Anki-tool — AI Flashcards with a Local, Open-Source LLM

An Anki add-on that turns your notes, textbook excerpts, or articles into
flashcards using an LLM that runs **entirely on your own computer**.

- **No API keys, no subscriptions, no per-request costs.** It talks to a
  free, open-source model server (Ollama by default) on `localhost`.
- **Private.** Your study material never leaves your machine.
- **No dependencies.** The add-on uses only Python's standard library, so
  it runs inside Anki's bundled Python with nothing extra to install.

## Why "connect to a local LLM" instead of bundling one into the add-on?

Bundling a model inside the add-on isn't practical: usable models are
2–8+ GB (far beyond add-on size limits), and the add-on would also have to
ship an inference engine with per-OS GPU support. The standard approach is
what this add-on does: you install a small, free model server once
([Ollama](https://ollama.com)), download a model with one command, and the
add-on connects to it over `http://localhost`. Everything is open source
and everything runs locally.

## Setup (about 5 minutes)

### 1. Install Ollama and download a model

Ollama is a free, open-source LLM server for Windows, macOS, and Linux.

1. Install it from <https://ollama.com/download>.
2. Open a terminal and download a model:

   ```
   ollama pull llama3.1:8b
   ```

That's it — Ollama runs in the background and serves the model at
`http://localhost:11434`.

**Which model?** Rough guide by hardware:

| Model (Ollama tag) | Size | Needs (RAM) | Notes |
|---|---|---|---|
| `llama3.1:8b` | ~4.7 GB | 8–16 GB | Good default; solid card quality |
| `qwen2.5:7b` | ~4.7 GB | 8–16 GB | Strong at following the JSON format |
| `mistral:7b` | ~4.1 GB | 8 GB | Fast, decent quality |
| `llama3.2:3b` | ~2 GB | 4–8 GB | For older/low-RAM machines |
| `qwen2.5:14b` | ~9 GB | 16–32 GB | Better cards if your machine can run it |

If you pick a model other than `llama3.1:8b`, set it in the add-on config
(step 3).

### 2. Install the add-on

**From this repository:**

1. Download or clone this repo.
2. Copy the `ai_flashcards` folder into your Anki add-ons folder:
   - Windows: `%APPDATA%\Anki2\addons21\`
   - macOS: `~/Library/Application Support/Anki2/addons21/`
   - Linux: `~/.local/share/Anki2/addons21/`

   (In Anki: Tools › Add-ons › View Files opens this folder.)
3. Restart Anki.

**Or build an `.ankiaddon` file** to share with others:

```
cd ai_flashcards
zip -r ../ai_flashcards.ankiaddon . -x "__pycache__/*" "meta.json"
```

Anyone can then install it via Tools › Add-ons › Install from file.

### 3. Configure (optional)

Tools › Add-ons › select "AI Flashcards (Local LLM)" › Config. The
defaults work out of the box with Ollama and `llama3.1:8b`. See
[`ai_flashcards/config.md`](ai_flashcards/config.md) for every option.

## Usage

1. In Anki: **Tools › Generate AI Flashcards (Local LLM)...**
2. Paste your source text, pick a deck and a max card count, click
   **Generate**.
3. Review the cards in the preview table (double-click any cell to edit),
   then click **Add cards to deck**.

## Using something other than Ollama

Any server that speaks the OpenAI chat-completions API works — LM Studio,
llama.cpp's server, Jan, KoboldCpp, vLLM, and others. In the add-on
config set:

```json
{
    "provider": "openai_compatible",
    "openai_base_url": "http://localhost:1234/v1",
    "model": "whatever-the-server-expects"
}
```

`http://localhost:1234/v1` is LM Studio's default; adjust for your server.
You can also point `ollama_url` or `openai_base_url` at another machine on
your network to run the model on a more powerful PC than the one running
Anki.

## Troubleshooting

- **"Could not reach the Ollama server"** — Ollama isn't running or isn't
  installed. Run `ollama serve` in a terminal (or just launch the Ollama
  app) and make sure you've pulled a model.
- **Timeouts** — the first request after a model loads can be slow. Raise
  `timeout_seconds` in the config, or use a smaller model.
- **Garbled/empty cards** — small models occasionally break the JSON
  format. Click Generate again, or switch to `qwen2.5:7b` /
  `llama3.1:8b`, which follow instructions more reliably.

## Project layout

```
ai_flashcards/
├── __init__.py         # add-on entry point (Tools menu item)
├── gui.py              # generate/preview/add dialog
├── card_generator.py   # prompt construction + lenient JSON parsing
├── llm_client.py       # HTTP client for Ollama / OpenAI-compatible servers
├── config.json         # default settings
├── config.md           # settings documentation (shown in Anki's config UI)
└── manifest.json       # add-on metadata for .ankiaddon packaging
```

## License

See [LICENSE](LICENSE).
