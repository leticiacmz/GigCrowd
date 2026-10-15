"""What turns a stored show log into a review.

A show log records attendance; it becomes a review by carrying an opinion.
For writing, an opinion is a rating or some words - a photo alone is not
enough, because a picture without anything said about the show is evidence
rather than an opinion. Reading is deliberately broader: rows written under
the older rule (rating plus text or photo, or a photo on its own) are
already reviews in the database and must keep counting as what they were
recorded as. The predicate below is that reading rule, used everywhere a
stored log is asked "did this person review the show?".
"""

from typing import Optional


def log_carries_review(log: dict) -> bool:
    """Whether a stored show log carries an opinion.

    Text, a photo, or a rating of at least one star - any of the three. The
    rating check excludes `0`, `None`, and the empty string some legacy
    rows carry, so absence stays absence and never reads as a score.
    """

    text = log.get("review")

    if isinstance(text, str) and text.strip():
        return True

    photo = log.get("photo_url")

    if isinstance(photo, str) and photo.strip():
        return True

    rating = log.get("rating")

    return (
        isinstance(rating, int)
        and not isinstance(rating, bool)
        and rating >= 1
    )


def stored_rating(log: dict) -> Optional[int]:
    """The rating a stored log states, or `None` when it states none.

    Absence has to survive the read: an opinion written without stars is
    exposed as no rating at all, never as a fabricated zero that would
    render as an empty star row and read like a verdict.
    """

    rating = log.get("rating")

    # `bool` is a subclass of `int` in Python, and `True` is not a star.
    if isinstance(rating, bool) or not isinstance(rating, int):
        return None

    return rating if rating >= 1 else None
