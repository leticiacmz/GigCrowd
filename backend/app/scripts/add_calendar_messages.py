"""Add the profile calendar and diary strings to every locale.

The catalogue shape matters. A profile message is either a flat key
(`showsMore`) or a nested object (`shows.empty.attended`), and `next-intl` resolves
a dotted path against it. A key written as a flat dotted string would be looked up
literally and render as raw dots on the page.

So each string is declared here as a path split into segments, and the script
places it at that path. All three locales are written by the same generator, so
they cannot drift apart in shape or content.

Run with --apply to write; without it, this only reports what would change.
"""
from __future__ import annotations

import json
import sys

from pathlib import Path
from typing import Any

MESSAGES = (
    Path(__file__).resolve().parents[3] / "frontend" / "messages"
)

# Every new string, in all three languages, in one place so the three catalogues
# cannot drift apart.
#
# `calendar.*` lives under `profile.calendar` because the calendar is part of the
# profile's shows area, and next-intl resolves `profile.calendar.heading` through
# that nesting.
STRINGS: dict[str, dict[str, Any]] = {
    "en": {
        "showsLoadMore": "Load earlier shows",
        "showsLoadingMore": "Loading…",
        "calendar": {
            "heading": "Shows attended by month",
            "previous": "Previous month",
            "next": "Next month",
            "emptyMonth": "No shows attended this month",
            "noShowsThatDay": "No shows on that day",
            "clearFilterHint":
                "Choose the day again to see the whole month.",
            "filtering": "Showing {day} only",
            "dayWithShows": "{shows} show(s) on day {day}",
            "summary": "{shows} show(s) across {days} day(s)",
            "weekdays": {
                "mon": "Mon",
                "tue": "Tue",
                "wed": "Wed",
                "thu": "Thu",
                "fri": "Fri",
                "sat": "Sat",
                "sun": "Sun",
            },
        },
    },
    "pt-BR": {
        "showsLoadMore": "Carregar shows anteriores",
        "showsLoadingMore": "Carregando…",
        "calendar": {
            "heading": "Shows por mês",
            "previous": "Mês anterior",
            "next": "Próximo mês",
            "emptyMonth": "Nenhum show neste mês",
            "noShowsThatDay": "Nenhum show nesse dia",
            "clearFilterHint":
                "Escolha o dia novamente para ver o mês inteiro.",
            "filtering": "Mostrando apenas {day}",
            "dayWithShows": "{shows} show(s) no dia {day}",
            "summary": "{shows} show(s) em {days} dia(s)",
            "weekdays": {
                "mon": "Seg",
                "tue": "Ter",
                "wed": "Qua",
                "thu": "Qui",
                "fri": "Sex",
                "sat": "Sáb",
                "sun": "Dom",
            },
        },
    },
    "es": {
        "showsLoadMore": "Cargar shows anteriores",
        "showsLoadingMore": "Cargando…",
        "calendar": {
            "heading": "Shows por mes",
            "previous": "Mes anterior",
            "next": "Mes siguiente",
            "emptyMonth": "Sin shows este mes",
            "noShowsThatDay": "Sin shows ese dia",
            "clearFilterHint":
                "Elige el dia de nuevo para ver todo el mes.",
            "filtering": "Mostrando solo el {day}",
            "dayWithShows": "{shows} show(s) el dia {day}",
            "summary": "{shows} show(s) en {days} dia(s)",
            "weekdays": {
                "mon": "Lun",
                "tue": "Mar",
                "wed": "Mie",
                "thu": "Jue",
                "fri": "Vie",
                "sat": "Sab",
                "sun": "Dom",
            },
        },
    },
}

PROFILE = "profile"


def place(
    section: dict,
    path: str,
    value: Any,
    added: list[str],
    locale: str,
) -> None:
    """Put one value at a dotted path inside `section`, creating what is missing."""

    parts = path.split(".")

    node = section

    for part in parts[:-1]:

        existing = node.get(part)

        if existing is None:

            # A group on the way to a leaf. Only the leaf is recorded as added:
            # reporting the group too would double-count every key beneath it.
            node[part] = {}

        elif not isinstance(existing, dict):

            # An existing leaf where a group is needed would be overwritten. Say so
            # rather than silently changing an existing string's meaning.
            print(
                f"   {locale}: profile.{part} is a value, not a group; "
                f"cannot place profile.{path}"
            )
            return

        node = node[part]

    leaf = parts[-1]

    if leaf in node and node[leaf] != value:
        print(
            f"   {locale}: profile.{path} already exists with a "
            f"different value; leaving it alone."
        )
        return

    if leaf not in node:
        added.append(f"{PROFILE}.{path}")

    node[leaf] = value


def write(path: Path, payload: dict) -> None:
    """Write a catalogue in the shape the project expects.

    `ensure_ascii=False` keeps accented Portuguese and Spanish readable in the file
    rather than escaped, and the trailing newline keeps diffs to one clean line.
    """

    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    apply = "--apply" in sys.argv

    for locale, entries in STRINGS.items():

        path = MESSAGES / f"{locale}.json"

        payload = json.loads(path.read_text(encoding="utf-8"))

        section = payload.setdefault(PROFILE, {})

        added: list[str] = []

        def walk(node: dict, prefix: str = "") -> None:
            for key, value in node.items():

                dotted = f"{prefix}{key}"

                if isinstance(value, dict):

                    walk(value, f"{dotted}.")
                    continue

                place(section, dotted, value, added, locale)

        walk(entries)

        print(f"{locale}: {len(added)} key(s)")

        for key in added:
            print(f"      {key}")

        if apply:
            write(path, payload)

    if not apply:
        print()
        print("Dry run. Pass --apply to write.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())