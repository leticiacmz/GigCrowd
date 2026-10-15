from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime
from enum import Enum


def _has_words(review) -> bool:
    """Whether a review text states something.

    Whitespace is not words: a text of spaces is the absence of an opinion
    and must never satisfy the rule below.
    """

    return isinstance(review, str) and bool(review.strip())


def _has_photo(photo_url) -> bool:
    """Whether a photo was actually attached (an empty string was not)."""

    return isinstance(photo_url, str) and bool(photo_url.strip())



class AttendanceStatus(str, Enum):

    GOING = "going"
    MAYBE = "maybe"
    WENT = "went"



class ShowLogBase(BaseModel):

    event_id: str

    status: AttendanceStatus

    # Absent by default: a review without a rating stores no rating at all,
    # and the bounds apply only when one is stated.
    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
    )

    review: Optional[str] = None

    # Optional photo of the show, hosted by the project's media service.
    photo_url: Optional[str] = None

    photo_public_id: Optional[str] = None



class ShowLogCreate(ShowLogBase):
    """A log written in one go: attendance, and a review alongside it.

    The rule for the review half: at least a rating or some words. Both are
    individually optional - a rating on its own and a text on its own are
    complete opinions - but a photo on its own is not, and an empty payload
    that mentions no opinion at all is simply attendance and is accepted
    as such. On any status other than `went` the review fields are dropped
    on the way in, so only a log that will actually carry the review is
    judged by this rule.
    """

    @model_validator(mode="after")
    def _a_review_needs_an_opinion(self):

        # `review is not None` on purpose, rather than `_has_words`: a text
        # field that was sent but says nothing - empty, or only spaces - is
        # an attempt at an opinion, not the absence of one, and is refused
        # instead of quietly stored as attendance.
        attempted = (
            self.rating is not None
            or self.review is not None
            or _has_photo(self.photo_url)
        )

        if (
            self.status == AttendanceStatus.WENT
            and attempted
            and self.rating is None
            and not _has_words(self.review)
        ):

            raise ValueError(
                "A review needs a rating or some words - "
                "a photo on its own is not one."
            )

        return self



class ShowLogUpdate(BaseModel):

    status: Optional[AttendanceStatus] = None

    # Absent by default and bounded only when stated, like the create side.
    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
    )

    review: Optional[str] = None

    photo_url: Optional[str] = None

    photo_public_id: Optional[str] = None

    @model_validator(mode="after")
    def _a_review_needs_an_opinion(self):
        """An edit carrying review content must carry an opinion.

        A patch that states no review content at all (attendance changes,
        or nothing new) passes untouched; one that does state content -
        including a text field sent empty or only whitespace - must
        include a rating or some words, so photos-only, empty and
        whitespace-only edits are refused here just as they are on
        creation.
        """

        # See the create side: any string sent is an attempt, even an
        # empty one, while an omitted field is simply not there.
        attempted = (
            self.rating is not None
            or self.review is not None
            or _has_photo(self.photo_url)
        )

        if (
            attempted
            and self.rating is None
            and not _has_words(self.review)
        ):

            raise ValueError(
                "A review needs a rating or some words - "
                "a photo on its own is not one."
            )

        return self



class ReviewUpsert(BaseModel):
    """The body accepted when a review is written on its own.

    Every part is optional on its own - stars, words, photo - but the
    review itself is not optional: at least a rating or some words must
    be stated. A photo alone is evidence rather than an opinion, and an
    empty submission says nothing, so both are refused here.
    """

    rating: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
    )

    review: Optional[str] = None

    photo_url: Optional[str] = None

    photo_public_id: Optional[str] = None

    @model_validator(mode="after")
    def _an_opinion_is_required(self):

        if self.rating is None and not _has_words(self.review):

            raise ValueError(
                "A review needs a rating or some words - "
                "a photo on its own is not one."
            )

        return self



class ShowLogInDB(ShowLogBase):

    id: str = Field(alias="_id")

    user_id: str

    date: Optional[datetime] = None

    reviewed_at: Optional[datetime] = None

    created_at: datetime

    updated_at: datetime


    class Config:

        populate_by_name = True



class ShowLogResponse(ShowLogInDB):

    pass
