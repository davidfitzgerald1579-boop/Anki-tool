# AI Flashcards (Local LLM) — configuration

All settings take effect the next time you open the generator dialog.

## provider

Which kind of LLM server to talk to:

- `"ollama"` (default) — the [Ollama](https://ollama.com) server running on
  your own machine. Free and open source.
- `"openai_compatible"` — any server exposing the OpenAI chat-completions
  API: LM Studio, llama.cpp server, Jan, KoboldCpp, vLLM, etc.
- `"anthropic"` — Claude, paid from your Claude API credits. Set
  `anthropic_api_key` (below) and a Claude `model`. Your text is sent to
  Anthropic.

## model

The model name to request.

- For Ollama this is the tag you pulled, e.g. `llama3.1:8b`, `qwen2.5:7b`,
  `mistral:7b`. Run `ollama list` to see what you have installed.
- For LM Studio and similar servers, use the model identifier the server
  shows (many local servers ignore this field and use whatever model is
  currently loaded).
- For `"anthropic"`: `claude-opus-5-5` (most capable, $4 / $20 per
  million input / output tokens), `claude-sonnet-5-5` ($2 / $10) or
  `claude-haiku-5-5` (fastest and cheapest, $0.10 / $0.50). A non-Claude
  name here falls back to `claude-opus-5-5`.

## ollama_url

Base URL of the Ollama server. Default `http://localhost:11434`. Only used
when `provider` is `"ollama"`. Point it at another machine on your network
(e.g. `http://192.168.1.20:11434`) to use a model hosted on a beefier PC.

## openai_base_url

Base URL of the OpenAI-compatible server, *including* the `/v1` suffix if
the server uses one. Default `http://localhost:1234/v1` (LM Studio's
default). Only used when `provider` is `"openai_compatible"`.

## api_key

Optional. Sent as a `Bearer` token to OpenAI-compatible servers that
require one. Local servers normally don't; leave it empty.

## anthropic_api_key

Your Claude API key, used only when `provider` is `"anthropic"`. Create
one at https://platform.claude.com/settings/keys. Leave empty to use the
`ANTHROPIC_API_KEY` environment variable instead. The key is stored in
this add-on's config on your computer and sent only to api.anthropic.com.

## claude_effort

How hard Claude thinks before answering: `"low"`, `"medium"` (default)
or `"high"`. Thinking is billed as output tokens, so lower effort is
faster and cheaper.

## max_output_tokens

The most Claude may write in one request, thinking included — a hard
ceiling on what one request can cost (you pay only for what is used).
Default `16000`; allowed range 1024–64000.

## note_type

The Anki note type used for new cards. Default `"Basic"`. The generated
question goes into the note type's first field and the answer into its
second field, so any note type with at least two fields works.

## max_cards

Default value of the "Max cards" spinner in the dialog. Default `15`.

## timeout_seconds

How long to wait for the LLM server before giving up. Default `300`.
Local models can take a while on the first request after loading; raise
this if you use a large model on modest hardware.
