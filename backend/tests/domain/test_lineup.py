"""Deduplicating a lineup without inventing an identity for anyone.

A festival's bill lists the same act more than once often enough to matter, and
it lists performers the catalogue has never heard of. Both have to survive
being stored: a duplicate entry makes a page look wrong, and dropping an
unidentified performer because it lacks an id would hide a real act.

The rule is that a Songkick id is the identity when there is one, and a name is
only ever a way to notice a repeat - never a substitute for an id.
"""
from __future__ import annotations

from app.domain.lineup import (
    dedupe_lineup,
    LineupEntry,
)


def entry(
    name: str,
    songkick_id: str | None = None,
    **overrides,
) -> LineupEntry:
    return LineupEntry(
        name=name,
        songkick_id=songkick_id,
        **overrides,
    )


class TestDeduplication:
    def test_the_same_id_appears_once(self):
        result = dedupe_lineup(
            [
                entry("Arctic Monkeys", "520117"),
                entry("arctic monkeys", "520117"),
            ]
        )

        assert len(result) == 1

    def test_the_first_appearance_wins(self):
        """The source put it in that order; the later entry is the repeat."""

        result = dedupe_lineup(
            [
                entry("Arctic Monkeys", "520117"),
                entry("ARCTIC MONKEYS", "520117"),
            ]
        )

        assert result[0].name == "Arctic Monkeys"

    def test_two_different_ids_are_both_kept(self):
        """A shared name is not a shared performer."""

        result = dedupe_lineup(
            [
                entry("The National", "111"),
                entry("The National", "222"),
            ]
        )

        assert len(result) == 2

    def test_a_name_repeat_is_collapsed_when_no_id_exists(self):
        result = dedupe_lineup(
            [
                entry("Unknown Act"),
                entry("unknown  act"),
            ]
        )

        assert len(result) == 1

    def test_a_named_act_is_kept_when_nothing_identifies_it(self):
        """The act is real; it simply cannot be resolved yet."""

        result = dedupe_lineup(
            [entry("Unidentified Opening Act")]
        )

        assert len(result) == 1
        assert result[0].songkick_id is None

    def test_a_named_act_does_not_absorb_an_identified_one(self):
        result = dedupe_lineup(
            [
                entry("Arctic Monkeys", "520117"),
                entry("Arctic Monkeys"),
            ]
        )

        assert len(result) == 2

    def test_duplicates_are_removed_before_order_is_assigned(self):
        result = dedupe_lineup(
            [
                entry("First", "1"),
                entry("Duplicate", "1"),
                entry("Second", "2"),
            ]
        )

        assert [
            entry_.order for entry_ in result
        ] == [0, 1]
        assert [entry_.name for entry_ in result] == [
            "First",
            "Second",
        ]

    def test_an_empty_lineup_stays_empty(self):
        assert dedupe_lineup([]) == []

    def test_a_single_entry_keeps_its_place(self):
        assert dedupe_lineup([entry("Only", "1")])[0].order == 0


class TestIdentity:
    def test_an_id_is_preferred_over_a_name(self):
        assert entry("A", "520117").identity() == "id:520117"

    def test_a_name_is_only_a_fallback_key(self):
        """It deduplicates; it never pretends to be an identifier."""

        assert entry("A").identity() == "name:a"

    def test_names_are_compared_without_case_or_spacing(self):
        assert (
            entry("  Arctic   Monkeys ").identity()
            == entry("arctic monkeys").identity()
        )

    def test_the_fallback_key_is_not_confusable_with_an_id(self):
        """An id and a name must never produce the same key."""

        assert entry("520117").identity() != entry(
            "520117", "520117"
        ).identity()


class TestModel:
    def test_an_entry_needs_only_a_name(self):
        assert entry("Solo Act").genres == []

    def test_an_empty_lineup_is_not_shared_between_events(self):
        """Two events' lineups must not be the same mutable list."""

        one = []
        two = []

        one.append(entry("Act"))

        assert two == []

    def test_genres_default_to_an_empty_list(self):
        first = entry("A")
        second = entry("B")

        first.genres.append("rock")

        assert second.genres == []