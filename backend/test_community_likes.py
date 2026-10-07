"""Community post likes, end to end against a running API.

This used to log in as a hard-coded account that only existed because somebody
had created it by hand in the database, and it returned early on any unexpected
status. That combination meant it reported success while testing almost nothing:
a clean database reset exposed it immediately.

It now provisions its own account with a unique name, follows an artist the way
the product requires before posting, and asserts on every response - so a route
that does not exist fails the test instead of quietly skipping it.

The API must be running on :8000; the test says so and skips rather than
reporting a confusing failure if it is not.
"""
import uuid

import pytest
import requests

BASE_URL = "http://localhost:8000"

PASSWORD = "TestPass123!"


def _api_is_up() -> bool:
    try:
        requests.get(f"{BASE_URL}/health", timeout=5)
        return True
    except requests.RequestException:
        return False


requires_api = pytest.mark.skipif(
    not _api_is_up(),
    reason="the API must be running on :8000 for this test",
)


@pytest.fixture
def account():
    """A registered account with the headers needed to act as them."""

    handle = f"likes{uuid.uuid4().hex[:10]}"

    registered = requests.post(
        f"{BASE_URL}/auth/register",
        json={
            "username": handle,
            "email": f"{handle}@gigcrowd.app",
            "password": PASSWORD,
        },
        timeout=30,
    )

    assert registered.status_code in (200, 201), registered.text

    token = requests.post(
        f"{BASE_URL}/auth/login",
        data={"username": f"{handle}@gigcrowd.app", "password": PASSWORD},
        timeout=30,
    ).json()["access_token"]

    return {"headers": {"Authorization": f"Bearer {token}"}}


@requires_api
def test_community_likes(account):
    headers = account["headers"]

    artists = requests.get(
        f"{BASE_URL}/artists", headers=headers, timeout=30
    ).json()

    if not artists:
        pytest.skip(
            "no artists in the database; run the development seed first"
        )

    artist_slug = artists[0]["slug"]

    # Posting into an artist community requires following that artist, so the
    # test follows first rather than asserting against a 403.
    followed = requests.post(
        f"{BASE_URL}/artists/{artist_slug}/follow", headers=headers, timeout=30
    )

    assert followed.status_code in (200, 201), followed.text

    created = requests.post(
        f"{BASE_URL}/artists/{artist_slug}/community/posts",
        headers=headers,
        json={"content": "Test community post for likes!"},
        timeout=30,
    )

    assert created.status_code == 200, created.text

    post = created.json()
    post_id = post["id"]

    assert post["likes_count"] == 0
    assert post["comments_count"] == 0

    # Liking registers. The route answers with an acknowledgement rather than
    # the post, so the counter is read back from the list afterwards.
    liked = requests.post(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}/like",
        headers=headers,
        timeout=30,
    )

    assert liked.status_code == 200, liked.text
    assert liked.json()["success"] is True

    def read_post():
        listing = requests.get(
            f"{BASE_URL}/artists/{artist_slug}/community/posts",
            timeout=30,
        )

        assert listing.status_code == 200, listing.text

        return next(
            row
            for row in listing.json()
            if row["id"] == post_id
        )

    assert read_post()["likes_count"] == 1

    # Liking again is refused rather than double counting: the like is a set,
    # and the route says so instead of pretending to add a second one.
    again = requests.post(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}/like",
        headers=headers,
        timeout=30,
    )

    assert again.status_code == 400, again.text
    assert read_post()["likes_count"] == 1

    # And it can be taken back, after which it can be liked again.
    unliked = requests.delete(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}/like",
        headers=headers,
        timeout=30,
    )

    assert unliked.status_code == 200, unliked.text
    assert read_post()["likes_count"] == 0

    reliked = requests.post(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}/like",
        headers=headers,
        timeout=30,
    )

    assert reliked.status_code == 200, reliked.text
    assert read_post()["likes_count"] == 1

    # The post is readable by anyone, and the counters are on it.
    # `liked_by_user` is relative to the reader, so it is checked from both
    # sides: true for the person who liked it, false for anyone else.
    signed_in = requests.get(
        f"{BASE_URL}/artists/{artist_slug}/community/posts",
        headers=headers,
        timeout=30,
    ).json()

    as_author = next(
        row for row in signed_in if row["id"] == post_id
    )

    assert as_author["likes_count"] == 1
    assert as_author["comments_count"] == 0
    assert as_author["content"] == "Test community post for likes!"
    assert as_author["liked_by_user"] is True

    anonymous = requests.get(
        f"{BASE_URL}/artists/{artist_slug}/community/posts",
        timeout=30,
    ).json()

    as_stranger = next(
        row for row in anonymous if row["id"] == post_id
    )

    assert as_stranger["likes_count"] == 1
    assert as_stranger["liked_by_user"] is False

    # Tidy up, so repeated runs do not accumulate posts.
    #
    # Cleanup is not a claim about the product, so its outcome is deliberately
    # not asserted: a leftover post is untidy, a failing teardown is a false
    # alarm about a route this test is not making any claim about.
    requests.delete(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}/like",
        headers=headers,
        timeout=30,
    )

    requests.delete(
        f"{BASE_URL}/artists/{artist_slug}/community/posts/{post_id}",
        headers=headers,
        timeout=30,
    )
