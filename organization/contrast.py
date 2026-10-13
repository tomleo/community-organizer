"""WCAG contrast for the brand colors compiled into the CSS."""

import re

_VARIABLE = r"--bs-{name}:([^;}}]+)"

# Named colors a CSS minifier may write instead of a longer hex value.
NAMED_COLORS = {
    "aqua": "#00ffff",
    "azure": "#f0ffff",
    "beige": "#f5f5dc",
    "bisque": "#ffe4c4",
    "black": "#000000",
    "blue": "#0000ff",
    "brown": "#a52a2a",
    "coral": "#ff7f50",
    "cyan": "#00ffff",
    "gold": "#ffd700",
    "gray": "#808080",
    "green": "#008000",
    "grey": "#808080",
    "indigo": "#4b0082",
    "ivory": "#fffff0",
    "khaki": "#f0e68c",
    "lime": "#00ff00",
    "linen": "#faf0e6",
    "maroon": "#800000",
    "navy": "#000080",
    "olive": "#808000",
    "orange": "#ffa500",
    "orchid": "#da70d6",
    "peru": "#cd853f",
    "pink": "#ffc0cb",
    "plum": "#dda0dd",
    "purple": "#800080",
    "red": "#ff0000",
    "salmon": "#fa8072",
    "sienna": "#a0522d",
    "silver": "#c0c0c0",
    "snow": "#fffafa",
    "tan": "#d2b48c",
    "teal": "#008080",
    "tomato": "#ff6347",
    "violet": "#ee82ee",
    "wheat": "#f5deb3",
    "white": "#ffffff",
    "yellow": "#ffff00",
}


def _channel(value: int) -> float:
    value /= 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _luminance(color: str) -> float:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(part * 2 for part in color)
    red, green, blue = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(red) + 0.7152 * _channel(green) + 0.0722 * _channel(blue)


def contrast_ratio(color: str, background: str = "#ffffff") -> float:
    lighter, darker = sorted((_luminance(color), _luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def _hex(value: str) -> str:
    """#rrggbb for a CSS color value as the minifier writes it; ValueError if it can't tell."""
    value = value.strip().lower()
    if value in NAMED_COLORS:
        return NAMED_COLORS[value]
    if re.fullmatch(r"#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})", value):
        digits = value[1:]
        if len(digits) in (3, 4):
            digits = "".join(part * 2 for part in digits[:3])
        return "#" + digits[:6]  # alpha, if any, is dropped
    raise ValueError(value)


def css_colors(css: str) -> dict:
    """First (light-theme) values of --bs-primary and --bs-link-color, as #rrggbb.

    Raises ValueError when either is missing or isn't a color this module can read.
    """
    colors = {}
    for key, name in (("primary", "primary"), ("link", "link-color")):
        match = re.search(_VARIABLE.format(name=name), css)
        if not match:
            raise ValueError(f"--bs-{name} not found")
        try:
            colors[key] = _hex(match.group(1))
        except ValueError:
            raise ValueError(f"can't read --bs-{name}: {match.group(1).strip()}") from None
    return colors
