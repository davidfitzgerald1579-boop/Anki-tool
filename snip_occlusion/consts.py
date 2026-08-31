"""Shared constants for the Snip Occlusion add-on."""

ADDON_NAME = "Snip Occlusion"

# Note type
MODEL_NAME = "Snip Occlusion"
BASIC_MODEL_NAME = "Snip Occlusion Basic"
BASIC_FIELDS = ["Front", "Back", "Notes"]
FIELDS = [
    "Occlusion ID",
    "Image",
    "Header",
    "Footer",
    "Masks",
    "Target",
    "Mode",
    "Search Text",  # OCR of the card image; searchable, never displayed
]

# Fields that identify a note type as ours (for in-place field upgrades)
MARKER_FIELDS = {"Occlusion ID", "Masks", "Target", "Mode"}
CARD_NAME = "Occlusion Card"

# Card generation modes
MODE_HIDE_ALL = "hag1"  # Hide All, Guess One
MODE_HIDE_ONE = "hog1"  # Hide One, Guess One

# Shape kinds
KIND_RECT = "rect"
KIND_ELLIPSE = "ellipse"  # legacy: no longer drawable, still renders on old notes
KIND_ERASE = "erase"
KIND_PATCH = "patch"  # a pixel-exact cutout of the image, movable
KIND_HIGHLIGHT = "highlight"  # translucent highlighter band, baked in

# Kinds that become occlusion masks / cards (the rest are image surgery)
MASK_KINDS = (KIND_RECT, KIND_ELLIPSE)

# Editor tools
TOOL_SELECT = "select"
TOOL_RECT = "rect"
TOOL_ERASE = "erase"
TOOL_PATCH = "patch"
TOOL_HIGHLIGHT = "highlight"

# Snap behaviours
SNAP_WORD = "word"  # rect created by double-clicking a word; resize snaps
                    # to whole words on its text line

# Quick colours offered in the highlighter's right-click menu (light tones
# multiply nicely: background takes the colour, dark text stays dark)
HIGHLIGHT_QUICK_COLORS = [
    ("Yellow", "#ffe94d"),
    ("Green", "#b9f6a5"),
    ("Pink", "#ffb3de"),
    ("Blue", "#a5d8ff"),
]

# Geometry
MIN_SHAPE_PX = 6  # shapes smaller than this on creation are discarded

DEFAULT_CONFIG = {
    "drag_threshold_px": 5,
    "mask_fill": "#FFEBA2",
    "target_fill": "#FF7E7E",
    "erase_color_mode": "majority",  # "majority" or "local"
    "highlight_fill": "#ffe94d",
    "shortcut_open": "Ctrl+Shift+O",
    "shortcut_text_card": "Ctrl+Shift+T",
    "close_after_add": False,
    "default_mode": MODE_HIDE_ALL,
    "nudge_step": 1,
    "nudge_step_large": 10,
    "ocr_backend": "auto",  # "auto" | "windows" | "tesseract" | "none"
    "tesseract_path": "",
    "tesseract_user_words": "",
    "ocr_corrections": {},
    "qgen_provider": "ollama",  # "ollama" | "openai_compatible"
    "qgen_model": "llama3.1:8b",
    "qgen_ollama_url": "http://localhost:11434",
    "qgen_openai_base_url": "http://localhost:1234/v1",
    "qgen_api_key": "",
    "qgen_max_cards": 4,
    "qgen_timeout_seconds": 300,
    "qgen_prefetch": True,
    "qgen_keep_alive": "30m",
    "qgen_feedback": True,
    "qgen_feedback_examples": 4,
}

# Distinct colors used for group badges in the editor
GROUP_PALETTE = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#46f0f0",
    "#f032e6",
    "#008080",
    "#9a6324",
    "#800000",
    "#808000",
    "#000075",
]
