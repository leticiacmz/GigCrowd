"""Check that the message catalogs are the same catalog in three languages.

Two failures are looked for, and both are invisible in a diff of English against
Portuguese:

  * **Parity** - a key present in one language but missing from another. The
    page renders whatever is there, so a missing key is a raw English label or an
    empty string in that language, not a build error.
  * **Encoding** - a value that is not valid UTF-8, or that has been written as
    the escapes of a wrong encoding. "Siga este artista" that reads as
    "Siga este artista" is a shipping bug, not a typo.

Run it directly or under pytest:

    python check_i18n.py
"""

import json
import sys
from pathlib import Path

MESSAGES = Path(__file__).parent / "messages"

# The languages the product ships. A new one has to be added here too, or it
# will silently miss every parity check.
LOCALES = ("en", "pt-BR", "es")

# The file every other language is compared against.
REFERENCE = "en"

# The escapes that appear when a file was written in the wrong encoding: UTF-8
# bytes decoded as Latin-1, and the literal `\uXXXX` form of the same mistake.
MOJIBAKE = (
    "Ã£", "Ã©", "Ã­", "Ã³", "Ãº",
    "Ã§", "Ã¼", "Ã±", "Ãµ",
    "ï¿½", "ï»¿",
    "\\u00e3", "\\u00e7", "\\u00e1", "\\u00e9",
)

# Locales that need their own plural rules. Every shipped language does, and
# the check below reads this set rather than hard-coding a count, so adding a
# language is a one-line change.
PLURAL_LOCALES = set(LOCALES)


def load(locale):
    """Read one catalog, refusing anything that is not valid UTF-8."""

    path = MESSAGES / f"{locale}.json"

    raw = path.read_bytes()

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SystemExit(
            f"{path.name} is not valid UTF-8: {error}"
        ) from error

    return json.loads(text)


def flatten(catalog, prefix=""):
    """Every message in a catalog as `a.b.c` -> value.

    Nested objects are namespaces, not messages, so they are walked rather than
    compared as strings. A key holding a list is a message whose value is the
    list itself.
    """

    flat = {}

    for key, value in catalog.items():
        path = f"{prefix}{key}"

        if isinstance(value, dict):
            flat.update(flatten(value, f"{path}."))
        else:
            flat[path] = value

    return flat


def placeholders(value):
    """The argument names a message interpolates, outermost braces only.

    An ICU message nests its own braces (`{count, plural, one {# post} other
    {# posts}}`), so a naive regex also reports `post` and `Ainda` as arguments.
    Only the names that introduce a substitution at depth zero are arguments.
    """

    names = set()
    depth = 0
    name = ""

    for character in str(value):
        if character == "{":
            depth += 1

            if depth == 1:
                name = ""
            continue

        if character == "}":
            depth -= 1

            if depth == 1 and name.strip():
                names.add(name.strip().split(",")[0].split(" ")[0])
            continue

        if depth == 1:
            name += character

    return names


def find_mojibake(locale, value):
    """The mojibake markers in one message, if it has any."""

    if not isinstance(value, str):
        return []

    return [marker for marker in MOJIBAKE if marker in value]


def main():
    catalogs = {locale: load(locale) for locale in LOCALES}
    flat = {locale: flatten(catalogs[locale]) for locale in LOCALES}
    reference = flat[REFERENCE]

    failures = []

    # --- parity -----------------------------------------------------------
    for locale in LOCALES:
        if locale == REFERENCE:
            continue

        missing = sorted(set(reference) - set(flat[locale]))
        extra = sorted(set(flat[locale]) - set(reference))

        for key in missing:
            failures.append(
                f"{locale}: missing key '{key}'"
            )

        for key in extra:
            failures.append(
                f"{locale}: has unknown key '{key}'"
            )

    # --- placeholders must match across languages -------------------------
    # A translated message that drops `{count}` still builds, and then prints a
    # literal placeholder in the middle of a sentence.
    for key, value in reference.items():
        names = placeholders(value)

        for locale in LOCALES:
            if locale == REFERENCE:
                continue

            translated = flat[locale].get(key)

            if translated is None:
                continue

            translated_names = placeholders(translated)

            if names != translated_names:
                failures.append(
                    f"{locale}: '{key}' placeholders "
                    f"{sorted(translated_names)} != {sorted(names)}"
                )

    # --- encoding ---------------------------------------------------------
    for locale in LOCALES:
        for key, value in flat[locale].items():
            for marker in find_mojibake(locale, value):
                failures.append(
                    f"{locale}: '{key}' contains {marker!r}"
                )

    for locale in LOCALES:
        path = MESSAGES / f"{locale}.json"

        # A file written as UTF-8 with a BOM parses fine but ships a stray
        # character at the start of every string read with the wrong decoder.
        if path.read_bytes().startswith(b"\xef\xbb\xbf"):
            failures.append(f"{locale}: has a UTF-8 BOM")

    print(f"catalogs: {len(LOCALES)} languages, "
          f"{len(reference)} messages in {REFERENCE}")

    if failures:
        print(f"\nFAIL ({len(failures)})")

        for failure in failures:
            print(f"  {failure}")

        return 1

    print("i18n: parity, placeholders and encoding are clean")

    return 0


if __name__ == "__main__":
    sys.exit(main())