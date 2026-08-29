### Snip Occlusion configuration

- `drag_threshold_px`: how far (in image pixels) the cursor must travel
  before a click on a shape turns into a move. Raise this if you still nudge
  shapes by accident; lower it if moving feels laggy. Default: `5`.
- `mask_fill`: colour of ordinary masks in the editor and on cards.
  Default: `"#FFEBA2"`.
- `target_fill`: colour of the highlighted target mask on cards.
  Default: `"#FF7E7E"`.
- `erase_color_mode`: default fill for new cover-up boxes. `"majority"`
  uses the slide's overall majority colour (recommended for BPP slides);
  `"local"` samples the background immediately around each box. You can
  always override a single box by right-clicking it. Default: `"majority"`.
- `shortcut_open`: global shortcut for opening the dialog from the main
  window. Default: `"Ctrl+Shift+O"`.
- `close_after_add`: close the dialog after adding cards instead of
  clearing it for the next snip. Default: `false`.
- `default_mode`: `"hag1"` (Hide All, Guess One) or `"hog1"`
  (Hide One, Guess One). Default: `"hag1"`.
- `nudge_step` / `nudge_step_large`: pixels moved by arrow keys /
  Shift+arrow keys. Defaults: `1` / `10`.

Note: `mask_fill` and `target_fill` are written into the note type's CSS
when the note type is first created. To restyle existing cards, edit the
"Snip Occlusion" note type's styling directly in Anki (`.io-mask` and
`.io-target`).
