import re
import unicodedata


def generate_slug(text: str) -> str:
    """
    Generates a normalized slug for artist names.
    """

    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")

    text = text.lower()

    text = re.sub(r"[^a-z0-9]+", "-", text)

    text = re.sub(r"-+", "-", text)

    return text.strip("-")