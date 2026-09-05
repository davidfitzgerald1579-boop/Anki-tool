# Running the AI on a server instead of your laptop

"Suggest cards" turns a slide's text into flashcard drafts with an
open-source language model. Out of the box that model runs on your own
computer through Ollama. That is free and private, but a laptop CPU
produces about ten words a second, so a slide takes a minute or more —
and a whole pasted lesson takes ten.

The same open models run on a datacentre GPU **fifty to three hundred
times faster**. This page explains the ways to get that, what each one
costs, what you give up, and how to set it up in the add-on. Nothing
here changes the add-on's licence or price: Snip Occlusion is free and
open source whichever option you use.

## The three places the model can run

| | Where it runs | Speed per slide | What you pay | Privacy | Set-up |
| --- | --- | --- | --- | --- | --- |
| **On this computer** (default) | Ollama on your laptop | 30 s – 3 min on a CPU; a few seconds with a gaming GPU | Nothing | Nothing leaves the machine | Install Ollama, `ollama pull` a model |
| **A hosted service** | A company's GPUs (Groq, OpenRouter, Together, …) | 1 – 3 s | Per use: a fraction of a cent per slide; several have free tiers | The slide's *text* (never the image) is sent to the service | Create an account, paste an API key |
| **A server you rent** | A GPU box you rent by the hour and run Ollama/vLLM on yourself | 1 – 5 s | By the hour, whether or not you are using it | Text goes to your own server | An afternoon's setup; you administer it |

For one student, **a hosted service is almost always the right upgrade**:
it is the fastest, the cheapest by a wide margin, and takes two
minutes. Renting a server is the option for people who want their own
box, or who need a model no service offers.

## How "paying for the server" works

Two things are involved when you use an AI model: the **model** — a
big file of numbers such as Llama, Qwen or gpt-oss — and the
**computer** that does the arithmetic to run it. The open-source models
this add-on uses are free to download and use. What is not free is a
datacentre GPU.

Proprietary services like Claude or ChatGPT charge you for both at once
and keep the model private. With an open-source model you only ever pay
for the computer time, and there are two ways to buy it:

**Pay per use ("serverless", "inference API").** Companies such as
Groq, OpenRouter, Together AI, DeepInfra and Hugging Face keep the
popular open models loaded on their GPUs and let anyone send requests.
You are billed per *token* (roughly, per word) in and out. Their
customers share the hardware, so you pay only for the seconds your
request actually uses. Prices in September 2026:

| Model | Typical price per million tokens (in / out) | Cost of one slide's cards |
| --- | --- | --- |
| gpt-oss-20b (small, replaces Llama 3.1 8B) | $0.04 – 0.10 / $0.15 – 0.30 | ≈ $0.0002 |
| gpt-oss-120b (large) | $0.04 – 0.35 / $0.17 – 0.75 | ≈ $0.0005 |
| Llama 3.3 70B | $0.10 – 0.90 / $0.30 – 0.90 | ≈ $0.0008 |

A slide's prompt is about 1,500 tokens in (the slide text plus the
style examples) and 300 – 600 tokens out, so **a thousand slides cost
somewhere between twenty cents and a dollar**. Most services also have
a free tier that covers a student's day: Groq's needs no card and
allows about 200,000 tokens a day per model — over a hundred slides;
OpenRouter's `:free`
models allow 50 requests a day (1,000 after a one-off $10 top-up);
Ollama Cloud and Mistral have free tiers too. The add-on shows each
service's free-tier note in the Settings window.

**Rent a whole GPU by the hour.** RunPod, Vast.ai, Lambda and similar
marketplaces rent you a machine with a GPU — an RTX 4090 for
$0.30 – 0.70 an hour, an A100 for about $1.40, an H100 for about $2.90 —
and you install Ollama or vLLM on it yourself. This is what "I'm just
paying for the server" usually means. The catch: **you pay for every
hour the box exists, not for the seconds you use**, so a server left
running while you sleep costs $7 – 70 a day. RunPod's *serverless*
endpoints fix that by starting a GPU only when a request arrives and
billing per second — but each cold start takes 30 – 90 s, which is
exactly the wait you were trying to avoid. For a single person
generating flashcards, renting a GPU costs hundreds of times more per
card than pay-per-use, for no gain in speed. It only wins when you need
a model that no service hosts, or a box you fully control.

**Why the add-on doesn't run a shared server for everyone.** It could:
the author would rent a server (or an API key) and every user's
requests would go through it. That is how paid tools work, and it is
why they charge. For a free add-on it would mean the author paying for
everyone's usage with no way to stop abuse, so — like every other
open-source AI tool — this one uses **bring-your-own-key**: each user
creates their own account with the service they choose, and is billed
(or not) by that service directly. The add-on never sees the bill.

## Setting up a hosted service (two minutes)

1. Create an account with a service and make an API key. **Groq** is
   the recommended first choice: no card, a free tier that is plenty
   for studying, and very fast. Go to
   <https://console.groq.com/keys>, sign up, press *Create API Key*
   and copy it.
2. In Anki, open Snip Occlusion (Ctrl+Shift+O) and press the **⚙**
   button, then under *AI model for card suggestions* choose **A
   hosted service**.
3. Pick the service, paste the key, and leave the model as suggested —
   or press **↻ Fetch list** to see everything the service offers.
4. Press **Test connection**. Within a couple of seconds it should say
   `✓ Groq answered with openai/gpt-oss-20b in 0.6 s`. If it reports a
   rejected key, a missing model or a rate limit, the message says
   what to do.
5. Save. The next snip's suggestions arrive in a second or two; the
   status line under the suggestions says *generating via Groq (…)*.

Every service in the drop-down works the same way; only the key and the
model names differ. Keys are stored in the add-on's config on your
computer (Tools → Add-ons → Snip Occlusion → Config: `qgen_api_key` for
the current service, `qgen_api_keys` for every service you have entered
one for), like every other setting — each key is only ever sent to the
service it was entered for. If you prefer not to keep a key in a file,
leave the box empty and set the service's usual environment variable
(`GROQ_API_KEY`, `OPENROUTER_API_KEY`, `HF_TOKEN`, …) before starting
Anki.

Note that with background pre-generation on (the default,
`qgen_prefetch`), every snip's text is sent to the service the moment
it lands in the editor — that is what makes the suggestions instant —
whether or not you open them. Set `qgen_prefetch` to `false` if you'd
rather nothing is sent until you press ↻ in the Suggested Cards view.

### Which model?

Smaller is faster and cheaper; bigger writes better cards. On a hosted
service the speed difference no longer matters — both answer in
seconds — so pick the bigger one unless you are rationing a free tier:

- **gpt-oss-120b** (OpenAI's open-weight model) and **Llama 3.3 70B**
  write clearly better cards than the 8B-class local default. They are
  the "large" option on every service.
- **gpt-oss-20b** is the small/cheap option and still better than the
  local Llama 3.1 8B.
- gpt-oss is a "thinking" model: it reasons before it answers. The
  add-on asks it to think briefly (flashcards don't need long
  deliberation) so it stays fast and cheap. Other thinking models
  (Qwen 3, DeepSeek R1) are left at their default effort, which costs
  a little more time and money per slide.

Model catalogues change — Groq retired its Llama models in August 2026
in favour of gpt-oss — so if a suggested name stops working, press
**↻ Fetch list** and choose a current one. The bake-off checkbox
("Alternate at random with:") lets you run two models side by side and
score them with your Use / ★ / Skip / ✗ verdicts before committing.

### What the service sees

Each generation sends the slide's OCR text (or the pasted lesson) plus
a few of your kept/flagged example cards as style guidance. The image
itself is never sent. Most of these services state that they don't
train on API traffic and keep it only briefly (Cerebras says it keeps
nothing at all), but the policies differ and change: read the policy of
whichever service you pick, and stay with the local option for anything
confidential. The add-on refuses HTTP redirects, so your key is only
ever sent to the address you configured. The Settings window prints the destination
next to the option so it is never a surprise.

## Renting a server and running the model yourself

If you do want your own box — for a model nobody hosts, or a machine
you control end to end — the add-on supports it through the **Another
server** option (any OpenAI-compatible URL) or by pointing the Ollama
option at a remote address. In outline:

1. Rent a GPU machine (RunPod and Vast.ai are the cheap ones; an RTX
   4090 with 24 GB runs 8B – 30B models comfortably, an A100/H100 runs
   70B models). Both have one-click **Ollama** and **vLLM** templates.
2. Run the model server there. With Ollama: `OLLAMA_HOST=0.0.0.0 ollama
   serve` then `ollama pull gpt-oss:20b`. With vLLM, the template's
   OpenAI-compatible server listens on `/v1`.
3. **Do not expose a bare model server to the internet.** Ollama and
   vLLM have no authentication of their own; an open port is a free
   GPU for whoever finds it and a bill for you. Use one of:
   - **Tailscale** (or another VPN) so the box is only reachable from
     your own devices, and give the add-on the box's Tailscale address;
   - a **reverse proxy with a token** (Caddy or nginx with a bearer
     token, or RunPod/Vast's built-in auth proxy) — put the token in
     the API-key box of whichever pane you use (the "On this computer"
     pane has one too, for exactly this) and it is sent as
     `Authorization: Bearer …` to Ollama or vLLM alike;
   - an **SSH tunnel** from your laptop (`ssh -L 11434:localhost:11434
     user@box`) with the add-on pointed at `http://localhost:11434`.
     The add-on can't tell a tunnel from a local server, so the
     privacy note will say nothing leaves the machine (it does — over
     your tunnel) and the laptop's CPU-thread limit is applied to the
     box; set `qgen_leave_cores_free` to `0` in the config to lift it.
4. In the add-on's Settings choose **Another server** with the
   `/v1` URL (vLLM), or keep **On this computer** and change the Ollama
   address to the box's URL. Press Test connection.
5. **Stop the machine when you finish studying.** That is the whole
   cost model: an RTX 4090 left running for a month is $250 – 500; a
   month of pay-per-use for the same student is under a dollar.

A middle ground is a **managed dedicated endpoint** (Hugging Face
Inference Endpoints, Modal, RunPod Serverless): you pick a model, they
run it on a GPU that scales to zero when idle and bill per second of
use, and hand you an OpenAI-compatible URL with a token. No server
administration, but every cold start costs 30 – 90 s, so it suits batch
jobs better than "I just snipped a slide".

## Keeping it local but faster

If you would rather not send text anywhere:

- A computer with a **gaming GPU** (an RTX 3060 or better, 8 GB+ of
  video memory) runs the 8B model in a few seconds per slide with no
  changes to the add-on — Ollama uses the GPU automatically. On a Mac
  with Apple silicon, the same is true out of the box.
- **Another computer on your network** with a GPU can do the work:
  run Ollama there with `OLLAMA_HOST=0.0.0.0`, and set the Ollama
  address in Settings to `http://<that-machine>:11434`.
- A **smaller model** (`llama3.2:3b`) is two to three times faster on
  a CPU at some cost in card quality; the bake-off will tell you how
  much.
- Background pre-generation is already on: the model starts the moment
  a snip lands, so with a fast enough machine the cards are ready
  before you finish drawing boxes.

## Quick reference

| Service | Config value | Key from | Free tier |
| --- | --- | --- | --- |
| Groq | `"groq"` | console.groq.com/keys | Yes, no card |
| OpenRouter | `"openrouter"` | openrouter.ai/keys | `:free` models, 50/day |
| Cerebras | `"cerebras"` | cloud.cerebras.ai | $5 trial credit (card required) |
| Together AI | `"together"` | api.together.ai/settings/api-keys | Small sign-up credit |
| Fireworks AI | `"fireworks"` | app.fireworks.ai | Small sign-up credit |
| DeepInfra | `"deepinfra"` | deepinfra.com/dash/api_keys | No (cheapest per token) |
| Hugging Face | `"huggingface"` | huggingface.co/settings/tokens | Small monthly allowance |
| Ollama Cloud | `"ollama_cloud"` | ollama.com/settings/keys | Yes, no card |
| Mistral AI | `"mistral"` | console.mistral.ai/api-keys | Yes, phone verification |
| Any other server | `"openai_compatible"` + `qgen_openai_base_url` | — | — |

Prices and free tiers above are as of September 2026 and change often;
each service's *Pricing ↗* link in the Settings window is the source of
truth.
