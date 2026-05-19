import re

import bleach
import markdown as _markdown_lib

_DANGEROUS_URL_ATTR: re.Pattern[str] = re.compile(
    r"""(?:href|src|xlink:href)\s*=\s*["']?\s*(?:javascript|vbscript|data|file|about):""",
    re.IGNORECASE,
)


def _reject_dangerous_links(
    cleaned: str,
) -> None:
    """Render markdown to HTML and raise if any link or image uses a blocked scheme."""

    html: str = _markdown_lib.markdown(cleaned, extensions=["fenced_code"])
    if _DANGEROUS_URL_ATTR.search(html):
        raise ValueError(
            "Markdown contains a link or image with an unsupported URL scheme",
        )


def sanitize_markdown_source(
    value: str,
) -> str:
    """Strip every HTML tag and comment, then reject dangerous markdown links.

    Checks:
        - non-empty input that survives sanitization -> cleaned string
        - empty/whitespace input -> raise ValueError (required field)
        - non-empty input that bleach strips to empty -> raise ValueError

    Use for required markdown fields where the field must always have content."""

    if not value or not value.strip():
        raise ValueError("content is empty after stripping HTML")
    cleaned: str = bleach.clean(value, tags=[], strip=True, strip_comments=True)
    if not cleaned.strip():
        raise ValueError(
            "Content contained no allowed elements after sanitization",
        )
    _reject_dangerous_links(cleaned)
    return cleaned


def sanitize_optional_markdown(
    value: str | None,
) -> str | None:
    """Same sanitization as `sanitize_markdown_source`, but treats None and empty distinctly.

    Check:
        - None input -> return None (sentinel meaning "do not change" for PATCH/PUT)
        - empty/whitespace input -> return "" (explicit clear; field-level logic
          decides whether that is permitted)
        - non-empty input that survives sanitization -> cleaned string
        - non-empty input that bleach strips to empty -> raise ValueError
          (caller submitted markup with no allowed content, e.g. only <script> tags)

    Use for optional markdown fields where None means "unchanged" and "" means
    "explicitly cleared"."""

    if value is None:
        return None
    if not value.strip():
        return ""
    cleaned: str = bleach.clean(value, tags=[], strip=True, strip_comments=True)
    if not cleaned.strip():
        raise ValueError(
            "Content contained no allowed elements after sanitization",
        )
    _reject_dangerous_links(cleaned)
    return cleaned
