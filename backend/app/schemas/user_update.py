from typing import Optional

from pydantic import BaseModel, field_validator


class UserUpdateRequest(BaseModel):

    full_name: Optional[str] = None

    bio: Optional[str] = None

    location: Optional[str] = None

    # The avatar rides the same update as the rest of the profile rather than
    # a second endpoint: the photo is uploaded first (the media service owns
    # storage), and its URL is saved here, on the caller's own document via
    # `/users/me` - so "only the owner" needs no extra check, because there is
    # no other user id anywhere in the path to aim at.
    avatar_url: Optional[str] = None

    @field_validator("avatar_url")
    @classmethod
    def _avatar_must_be_a_plain_image_url(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        """Only what a browser will safely paint into an `<img>`.

        The URL is the caller's own choice for their own profile, but it lands
        on public pages, so schemes a browser could *act on* rather than
        display (`javascript:`, `data:`, ...) are refused at the door instead
        of being trusted to some later filter. Length is capped so one field
        cannot carry a whole document into the users collection.
        """
        if value is None:
            return value

        normalized = value.strip()

        if not normalized.lower().startswith(("http://", "https://")):
            raise ValueError(
                "avatar_url must be an http(s) URL"
            )

        if len(normalized) > 2048:
            raise ValueError(
                "avatar_url is too long"
            )

        return normalized
