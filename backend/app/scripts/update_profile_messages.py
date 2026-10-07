"""Add the profile strings this iteration introduces to every locale.

Keys are written as literal text in the three message files rather than through
a script that copies one locale over the others, because each language needs its
own wording: "Artists I have seen" is a claim about someone's history, and a
literal translation of a Brazilian original does not survive being translated
back from English.

The script verifies what it wrote by reloading the JSON, so a typo cannot leave
an unparseable file behind, and it checks that all three locales end up with the
same key set so a missing translation is caught here rather than on a page.
"""
from __future__ import annotations

import io
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]

MESSAGES = ROOT / "frontend" / "messages"

# Locale -> {dotted key: value}. Only new keys belong here; existing wording is
# left exactly as it was.
ADDITIONS: dict[str, dict[str, str]] = {
    "en": {
        "panel.artists": "Artists I Have Seen",
        "panelSubtitle.reviews": "What you wrote about",
        "panelSubtitle.events": "Your concert history",
        "panelSubtitle.festivals": "Festivals you have been to",
        "panelSubtitle.artists": "Artists you have seen live",
        "panelSubtitle.followers": "People who follow you",
        "panelSubtitle.following": "People you follow",
        "noArtistsSeen": "No artists seen yet",
        "noArtistsSeenHint": (
            "The artists they have stood in front of appear here, one row"
            " per artist."
        ),
        "reviewedBadge": "You reviewed this show",
        "seenShows": (
            "{count, plural, =0 {No shows} one {# show} other {# shows}}"
        ),
        "statArtists": "Artists",
        "notifications.type.eventAttendanceCheck": (
            "The show is over. Did you go?"
        ),
        "notifications.type.eventReviewPrompt": (
            "You saw this show. Tell us how it was."
        ),
        "notifications.fromGigCrowd": "GigCrowd",
    },
    "pt-BR": {
        "panel.artists": "Artistas que eu vi",
        "panelSubtitle.reviews": "O que você escreveu sobre",
        "panelSubtitle.events": "Seu histórico de shows",
        "panelSubtitle.festivals": "Festivais em que você esteve",
        "panelSubtitle.artists": "Artistas que você viu ao vivo",
        "panelSubtitle.followers": "Pessoas que te seguem",
        "panelSubtitle.following": "Pessoas que você segue",
        "noArtistsSeen": "Nenhum artista visto ainda",
        "noArtistsSeenHint": (
            "Os artistas em que já esteve aparecem aqui, um por linha."
        ),
        "reviewedBadge": "Você avaliou este show",
        "seenShows": (
            "{count, plural, =0 {Nenhum show} one {# show} other {# shows}}"
        ),
        "statArtists": "Artistas",
        "notifications.type.eventAttendanceCheck": (
            "O show acabou. Você foi?"
        ),
        "notifications.type.eventReviewPrompt": (
            "Você viu este show. Conta pra gente como foi."
        ),
        "notifications.fromGigCrowd": "GigCrowd",
    },
    "es": {
        "panel.artists": "Artistas que he visto",
        "panelSubtitle.reviews": "Lo que escribiste sobre",
        "panelSubtitle.events": "Tu historial de conciertos",
        "panelSubtitle.festivals": "Festivales en los que has estado",
        "panelSubtitle.artists": "Artistas que has visto en directo",
        "panelSubtitle.followers": "Personas que te siguen",
        "panelSubtitle.following": "Personas que sigues",
        "noArtistsSeen": "Aún no hay artistas vistos",
        "noArtistsSeenHint": (
            "Los artistas en los que has estado aparecen aquí, uno por"
            " fila."
        ),
        "reviewedBadge": "Has reseñado este concierto",
        "seenShows": (
            "{count, plural, =0 {Ningún concierto} one {# concierto}"
            " other {# conciertos}}"
        ),
        "statArtists": "Artistas",
        "notifications.type.eventAttendanceCheck": (
            "El concierto terminó. ¿Fuiste?"
        ),
        "notifications.type.eventReviewPrompt": (
            "Viste este concierto. Cuéntanos cómo fue."
        ),
        "notifications.fromGigCrowd": "GigCrowd",
    },
}

# Keys this iteration replaces rather than adds. The old wording described a
# followed-artists list, which is no longer what the section shows, so it is
# removed instead of left behind as dead copy.
RETIRED = ("noArtists", "noArtistsHint", "communityPosts", "community")


def write(locale: str, additions: dict[str, str]) -> None:
    path = MESSAGES / f"{locale}.json"

    data = json.loads(path.read_text(encoding="utf-8"))

    for key in RETIRED:
        data["profile"].pop(key, None)

    for dotted, value in additions.items():
        parts = dotted.split(".")

        # The namespace is whatever the key says it is. This script is named for
        # the profile, but it also carries the notifications this iteration
        # added, and hardcoding one namespace quietly filed those under
        # `profile.` - where next-intl reports them as missing and renders the
        # raw key path to the reader.
        target = data

        for part in parts[:-1]:
            target = target.setdefault(part, {})

        target[parts[-1]] = value

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Reloaded so a broken write is a failure here, not on a rendered page.
    json.loads(path.read_text(encoding="utf-8"))


def key_set(locale: str) -> set[str]:
    data = json.loads(
        (MESSAGES / f"{locale}.json").read_text(encoding="utf-8")
    )

    found: set[str] = set()

    def walk(prefix: str, value) -> None:
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key

            if isinstance(nested, dict):
                walk(path, nested)
            else:
                found.add(path)

    walk("", data)

    return found


def main() -> None:
    for locale, additions in ADDITIONS.items():
        write(locale, additions)

    reference = key_set("en")

    for locale in ADDITIONS:
        if key_set(locale) != reference:
            missing = reference - key_set(locale)
            extra = key_set(locale) - reference

            raise SystemExit(
                f"{locale} does not match en: "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )

    # Non-ASCII is written literally, so anything that came out as a replacement
    # character or an escape would mean the file was mangled on the way in.
    for locale in ADDITIONS:
        text = (MESSAGES / f"{locale}.json").read_text(encoding="utf-8")

        if "\ufffd" in text:
            raise SystemExit(f"{locale} contains a replacement character")

        if "\\u" in text:
            raise SystemExit(f"{locale} contains a unicode escape")

    print(f"{len(reference)} keys, {len(ADDITIONS)} locales, all matching")


if __name__ == "__main__":
    main()
