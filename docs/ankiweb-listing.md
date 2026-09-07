# AnkiWeb listing (copy-paste kit)

Everything below is ready to paste into the AnkiWeb upload form at
<https://ankiweb.net/shared/addons/> (log in → **Upload**). The
step-by-step, including what to do for later updates, is in
[`RELEASING.md`](../RELEASING.md).

AnkiWeb's search matches words in the title and description, so both
carry the terms people actually type: image occlusion, slides,
lecture, AI, flashcards, OCR, local, free.

## Title

```
Snip Occlusion – image occlusion for lecture slides + free AI flashcards
```

## Supported versions

Minimum: **2.1.50** · Maximum: leave blank (tested through Anki 26.08,
works on both Qt5 and Qt6 builds).

## Description (paste into the description box)

```html
<b>Snip a slide → it appears in the editor → box the facts → Add Cards.
Or let a free, open-source AI draft the flashcards for you.</b>

Snip Occlusion is an image-occlusion editor built for studying from
slide decks (BPP Adapt, PowerPoint, any presentation you can screenshot).
Take a screenshot snip (Win+Shift+S) and it lands in the editor
automatically from your clipboard.

<img src="https://raw.githubusercontent.com/davidfitzgerald1579-boop/Anki-tool/main/docs/editor.png">

<b>Image occlusion that gets out of your way</b>

<ul>
<li><b>Precise grouping:</b> shift-click ANY combination of boxes and press
G — a box sitting between two grouped boxes stays independent. Groups
share a bold outline colour.</li>
<li><b>No accidental nudges:</b> shift-click only ever selects; nothing
moves until you drag past a threshold; dragging moves only the shape under
your cursor (Ctrl+drag moves the whole selection).</li>
<li><b>Double-click a word to occlude exactly that word</b> — no OCR,
pure pixel analysis; drag its handles to swallow neighbouring words one
at a time.</li>
<li><b>Cover-up tool:</b> erase irrelevant slide text — boxes are filled
with the slide's auto-detected background colour and baked into the
image. <b>Highlighter:</b> perfectly straight bands, text readable
underneath.</li>
<li><b>Snip patch tool:</b> cut out the one sentence you want to keep as a
pixel-perfect movable patch, cover up the rest, drop it back — or send it
to the <b>new-card queue</b> to become its own card.</li>
<li><b>Searchable image cards:</b> the text on each finished image is read
by OCR (built into Windows; Tesseract elsewhere) and stored invisibly on
the note, so the card browser and search add-ons can find your image
cards.</li>
<li><b>Hide All, Guess One / Hide One, Guess One</b> card modes. Cards
render with plain HTML/CSS, so they review correctly on AnkiDroid and
AnkiMobile with nothing installed there.</li>
<li><b>Edit later:</b> a ✂ button in Anki's editor reopens any card's
slide with all its boxes; during review, Delete removes a bad card and
Shift+Delete removes every card from that slide.</li>
</ul>

<b>AI-suggested flashcards — free, no download needed</b>

<ul>
<li>"✨ Suggest cards" turns the snip's text into question/answer drafts.
Each "Use →" opens the draft for a quick edit before it is added; 👎
teaches the AI what you don't want, and it learns your card style from
what you keep.</li>
<li><b>Two-minute setup, nothing to install:</b> make a free account at
Groq (no card needed), paste the key into ⚙ Settings → "A hosted
service", press Test connection, done. Cards arrive in a second or two.
Groq's free tier covers over a hundred slides a day; heavier use costs
a fraction of a cent per slide, paid to Groq, not to us. OpenRouter,
Together, Hugging Face, Ollama Cloud and others work the same way.</li>
<li><b>Prefer to keep everything on your computer?</b> Switch to "On
this computer": install Ollama and run
<code>ollama pull llama3.1:8b</code> (about 5 GB) and the same
open-source model runs locally — no account, no key, and the slide text
never leaves your machine. Slower (a minute or so per slide on a
laptop), but completely private.</li>
<li>Either way the add-on is free and open source. The Settings window
says plainly what is sent where: with a hosted service, the slide
<i>text</i> (never the image) goes to that service; with the local
option, nothing leaves your machine.</li>
<li>Paste a whole lesson and get cards section by section; highlight a
passage and ask for cards about just that; a 🔍 Reveal source button on
every AI card shows the slide and the sentence it came from while you
review.</li>
<li>Invented citations are caught: a case, statute or year that isn't in
the source text is stripped or flagged.</li>
</ul>

<img src="https://raw.githubusercontent.com/davidfitzgerald1579-boop/Anki-tool/main/docs/front_hag1.png">

<b>Getting started:</b> press Ctrl+Shift+O (or Tools → Snip Occlusion),
snip a slide, draw boxes with R, group with G, erase junk with C, pick a
deck and press Add Cards. Click the ? button in the editor for all
shortcuts. For AI suggestions, switch to the Suggested Cards view.

<b>Step-by-step guide (PDF)</b> with screenshots, from install to your
first AI cards:
https://github.com/davidfitzgerald1579-boop/Anki-tool/blob/main/docs/Snip-Occlusion-Getting-Started.pdf

<b>Free and open source</b> (Apache 2.0). Source code, full
documentation and the guide to hosted AI services:
https://github.com/davidfitzgerald1579-boop/Anki-tool

<b>Support:</b> please report problems on GitHub — bug reports in the
reviews section here can't be replied to, so GitHub is the best place to
get help.
```

## Notes on the form

- The description box takes a small subset of HTML — `<b>`, `<i>`,
  `<code>`, `<ul>`/`<li>`, `<img>` and bare URLs (which AnkiWeb links
  automatically) all render; anything else is shown as text. The image
  URLs above point at `main` on GitHub, so they only display once the
  screenshots are merged there (they are).
- Say what leaves the user's machine. AnkiWeb readers are wary of
  add-ons that contact the internet; the AI paragraph above states
  that nothing is sent unless the user opts in, and what is sent when
  they do. Keep that paragraph honest as the feature changes.
- There is no separate "changelog" field — paste the latest
  `CHANGELOG.md` entry at the end of the description when you update,
  or keep a short "What's new" line there.
