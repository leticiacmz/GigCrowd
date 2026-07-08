import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Normalize text for exact comparisons.

    Example:

    Guns N' Roses
        ↓
    guns n roses

    AC/DC
        ↓
    acdc

    Björk
        ↓
    bjork
    """

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")

    text = text.lower()

    text = re.sub(r"[^a-z0-9\s]", "", text)

    text = re.sub(r"\s+", " ", text)

    return text.strip()