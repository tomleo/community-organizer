"""Sanitizing rich text produced by the Trix editor."""

import html
import re

import nh3

# Exactly what Trix produces (minus attachments). Anything else is removed.
ALLOWED_TAGS = {
    "div",
    "br",
    "strong",
    "em",
    "del",
    "a",
    "h1",
    "blockquote",
    "pre",
    "ul",
    "ol",
    "li",
}
ALLOWED_ATTRIBUTES = {"a": {"href"}}
URL_SCHEMES = {"http", "https", "mailto"}

_cleaner = nh3.Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    url_schemes=URL_SCHEMES,
    link_rel="noopener noreferrer",
)
_strip_all = nh3.Cleaner(tags=set(), attributes={})
_BLOCK_END = re.compile(r"<(?:br|/div|/li|/h1|/blockquote|/pre)\b[^>]*>", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def sanitize_html(value: str | None) -> str:
    return _cleaner.clean(value or "")


def plain_text(value: str | None) -> str:
    """Text content with tags removed, for excerpts and JSON-LD."""
    spaced = _BLOCK_END.sub(" ", value or "")
    text = html.unescape(_strip_all.clean(spaced))
    return _WHITESPACE.sub(" ", text).strip()
