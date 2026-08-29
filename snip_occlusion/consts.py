"""Shared constants for the Snip Occlusion add-on."""

ADDON_NAME = "Snip Occlusion"

# Note type
MODEL_NAME = "Snip Occlusion"
FIELDS = [
    "Occlusion ID",
    "Image",
    "Header",
    "Footer",
    "Masks",
    "Target",
    "Mode",
]
CARD_NAME = "Occlusion Card"

# Card generation modes
MODE_HIDE_ALL = "hag1"  # Hide All, Guess One
MODE_HIDE_ONE = "hog1"  # Hide One, Guess One

# Shape kinds
KIND_RECT = "rect"
KIND_ELLIPSE = "ellipse"
KIND_ERASE = "erase"

# Editor tools
TOOL_SELECT = "select"
TOOL_RECT = "rect"
TOOL_ELLIPSE = "ellipse"
TOOL_ERASE = "erase"

# Geometry
MIN_SHAPE_PX = 6  # shapes smaller than this on creation are discarded

DEFAULT_CONFIG = {
    "drag_threshold_px": 5,
    "mask_fill": "#FFEBA2",
    "target_fill": "#FF7E7E",
    "erase_color_mode": "majority",  # "majority" or "local"
    "shortcut_open": "Ctrl+Shift+O",
    "close_after_add": False,
    "default_mode": MODE_HIDE_ALL,
    "nudge_step": 1,
    "nudge_step_large": 10,
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
