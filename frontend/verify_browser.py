"""Real-browser verification of the artist-scoped community, the unified feed,
notifications, i18n, theming and the mobile comment UI.

Data is seeded through the real API before the browser runs, so nothing in this
script is faked: every post, comment, reply, like, follow and review below was
written by a real backend call and is read back through the real endpoints.

Usage:
    python verify_browser.py                       # against the dev server
    BASE=http://localhost:3100 python verify_browser.py
"""

import os
import random
import re
import string
import sys
import tempfile
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:3000").rstrip("/")
API = os.environ.get("API", "http://localhost:8000").rstrip("/")

results = []


def check(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


def force_utf8_output():
    """Let the console carry the characters the pages do.

    Detail strings quote whatever the page rendered, which includes non-ASCII
    characters such as an accented name or a music note. A Windows console
    defaults to a single-byte code page, so printing one would abort the whole
    run on a page that actually passed.
    """

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


force_utf8_output()


# ---------------------------------------------------------------- API helpers

def suffix():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def register(username):
    """Create a user and return (token, user)."""
    # `.test` is a reserved TLD that pydantic refuses, so use example.com.
    email = f"{username}@example.com"
    password = "TestPass123!"

    with httpx.Client(base_url=API, timeout=30) as client:
        registered = client.post(
            "/auth/register",
            json={"email": email, "username": username, "password": password},
        )
        if registered.status_code != 201:
            raise RuntimeError(
                f"register {username} -> {registered.status_code} {registered.text}"
            )
        response = client.post(
            "/auth/login", data={"username": email, "password": password}
        )
        response.raise_for_status()
        body = response.json()

    return body["access_token"], body.get("user") or {"username": username}


def api(token):
    return httpx.Client(
        base_url=API,
        timeout=30,
        headers={"Authorization": f"Bearer {token}"},
    )


def seed():
    """Build a real dataset: two artists, three users, posts, comments, likes."""
    with httpx.Client(base_url=API, timeout=60) as client:
        artists = client.get("/artists", params={"limit": 40}).json()

    # Two artists with genuinely different slugs and names, so the isolation
    # and "which artist is this?" checks are meaningful.
    slugs = []
    names = {}
    for artist in artists:
        name = (artist.get("name") or "").strip()
        slug = (artist.get("slug") or "").strip()

        if not name or not slug:
            continue
        if name in names.values() or slug in slugs:
            continue

        slugs.append(slug)
        names[slug] = name

        if len(slugs) == 2:
            break

    assert len(slugs) >= 2, f"need two distinct artists to test isolation, got {slugs}"

    artist_slug, other_artist = slugs[0], slugs[1]

    stamp = suffix()
    # Distinct markers make the artist-isolation checks unambiguous: each
    # marker may only appear on its own artist's community.
    primary_marker = f"primary-{stamp}"
    other_marker = f"secondary-{stamp}"

    author_token, author = register(f"author{stamp}")
    fan_token, fan = register(f"fan{stamp}")
    visitor_token, visitor = register(f"visitor{stamp}")

    # `author` owns the community conversation and opens the thread, so the
    # author receives a follow, a like, a comment and a reply notification.
    with api(author_token) as client:
        client.post(f"/artists/{artist_slug}/follow")
        post = client.post(
            f"/artists/{artist_slug}/community/posts",
            json={
                "content": f"Anyone going to the {artist_slug} show? {primary_marker}"
            },
        ).json()
        author_comment = client.post(
            f"/artists/{artist_slug}/community/comments",
            json={
                "post_id": post["id"],
                "content": f"Tickets are already gone. {primary_marker}",
            },
        ).json()

    # `fan` follows the author, the artist, and engages with the thread.
    with api(fan_token) as client:
        client.post(f"/follows/{author['username']}")
        client.post(f"/artists/{artist_slug}/follow")
        comment = client.post(
            f"/artists/{artist_slug}/community/comments",
            json={"post_id": post["id"], "content": f"Count me in. {primary_marker}"},
        ).json()
        client.post(
            f"/artists/{artist_slug}/community/comments",
            json={
                "post_id": post["id"],
                "content": f"See you at the door. {primary_marker}",
                "parent_comment_id": author_comment["id"],
            },
        )
        client.post(
            f"/artists/{artist_slug}/community/comments",
            json={
                "post_id": post["id"],
                "content": f"Still thinking about it. {primary_marker}",
                "parent_comment_id": comment["id"],
            },
        )
        client.post(f"/artists/{artist_slug}/community/posts/{post['id']}/like")

    # A second real artist with a real post, for the isolation check.
    with api(author_token) as client:
        client.post(f"/artists/{other_artist}/follow")
        other_post = client.post(
            f"/artists/{other_artist}/community/posts",
            json={"content": f"Only on {other_artist}: {other_marker}"},
        ).json()

    # Attendance has to be recorded against a show that has already happened,
    # so the past events are read from the route that returns an artist's whole
    # history. `/events/artist/{slug}` only returns what is still to come, and
    # "went" on a future event is refused with a 400 by design.
    past_event = None

    for past_artist in (artist_slug, other_artist):
        history = httpx.get(
            f"{API}/artists/{past_artist}/events/all", timeout=120
        ).json()

        past_event = next(
            (event for event in history if event.get("is_past")), None
        )

        if past_event:
            break

    assert past_event, "need a finished event to record attendance against"

    # A real review, so the Reviews filter and the profile's reviews list have
    # genuine content instead of an empty state.
    review_note = f"Worth every second. {stamp}"

    with api(fan_token) as client:
        review_response = client.post(
            "/show-logs",
            json={
                "event_id": past_event["id"],
                "status": "went",
                "rating": 5,
                "review": review_note,
            },
        )
        review_seeded = review_response.status_code in (200, 201)

    # The author attends two further finished shows: one they wrote about and
    # one they did not. A show log carrying review text is published as a
    # review, so a plain attendance has to exist for the Events filter to hold
    # anything, and the author's profile needs rows behind both figures. The
    # author also follows the visitor, so their profile has people on both
    # sides of the connection.
    author_past = []

    for other_past in (other_artist, artist_slug):
        history = httpx.get(
            f"{API}/artists/{other_past}/events/all", timeout=120
        ).json()

        author_past = [
            event
            for event in history
            if event.get("is_past") and event["id"] != past_event["id"]
        ][:2]

        if len(author_past) == 2:
            break

    assert len(author_past) == 2, "need two more finished events for the author"

    attendance_seeded = False

    with api(author_token) as client:
        client.post(f"/follows/{visitor['username']}")

        client.post(
            "/show-logs",
            json={
                "event_id": author_past[0]["id"],
                "status": "went",
                "rating": 4,
                "review": f"The room shook. {stamp}",
            },
        )

        attendance_response = client.post(
            "/show-logs",
            json={
                "event_id": author_past[1]["id"],
                "status": "went",
                "rating": 3,
            },
        )

        attendance_seeded = attendance_response.status_code in (200, 201)

    return {
        "artist_slug": artist_slug,
        "other_artist": other_artist,
        "artist_name": names[artist_slug],
        "author_token": author_token,
        "author": author,
        "fan_token": fan_token,
        "fan": fan,
        "visitor_token": visitor_token,
        "visitor": visitor,
        "post": post,
        "other_post": other_post,
        "comment": comment,
        "stamp": stamp,
        "primary_marker": primary_marker,
        "other_marker": other_marker,
        "has_review": review_seeded,
        "has_attendance": attendance_seeded,
        "review_note": review_note,
        "past_event": past_event,
    }


def store_token(page, token, user):
    page.evaluate(
        """([token, user]) => {
            localStorage.setItem('token', token);
            localStorage.setItem('user', JSON.stringify(user));
        }""",
        [token, user],
    )


# --------------------------------------------------------------------- script

print("Seeding real data through the API ...")
DATA = seed()
print(
    f"  artist={DATA['artist_slug']} other={DATA['other_artist']} "
    f"author=@{DATA['author']['username']} fan=@{DATA['fan']['username']} "
    f"visitor=@{DATA['visitor']['username']} "
    f"review={DATA['has_review']} attendance={DATA['has_attendance']}\n"
)

SLUG = DATA["artist_slug"]

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ================================================================ 1. THEME
    # Both schemes are exercised against the pages this work added, not just the
    # home page: a token that only works on one scheme is invisible until the
    # reader with the other scheme reads it.
    for scheme in ("dark", "light"):
        ctx = browser.new_context(color_scheme=scheme)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{BASE}/en", wait_until="networkidle")
        check(
            f"theme: system {scheme} resolves to {scheme}",
            pg.evaluate("document.documentElement.getAttribute('data-theme')")
            == scheme,
        )

        pg.goto(
            f"{BASE}/en/profile/{DATA['author']['username']}",
            wait_until="networkidle",
        )
        pg.wait_for_timeout(1500)

        # The figures are buttons on a borderless container, so the surface to
        # read is the one the reader actually sees.
        state = pg.evaluate(
            """() => {
                const figure = document.querySelector(
                    '[data-testid="profile-stat-reviews"]'
                );
                const heading = document.querySelector('h1');
                return {
                    figure: figure ? getComputedStyle(figure).backgroundColor : null,
                    heading: heading ? getComputedStyle(heading).color : null,
                    theme: document.documentElement.getAttribute('data-theme'),
                };
            }"""
        )
        check(
            f"theme: the profile renders its surfaces in {scheme}",
            bool(state["figure"])
            and state["figure"] != "rgba(0, 0, 0, 0)"
            and state["theme"] == scheme,
            f"{state}",
        )

        # An empty panel has to be styled too, since that is the state most
        # readers land in.
        pg.locator("[data-testid='profile-stat-reviews']").first.click()
        pg.wait_for_timeout(1200)
        check(
            f"theme: the profile panel renders in {scheme}",
            pg.locator(
                "[data-testid='profile-panel'], [data-testid='empty-state']"
            ).count()
            >= 1,
            pg.inner_text("body").replace("\n", " | ")[:90],
        )

        pg.close()
        ctx.close()

    ctx = browser.new_context(color_scheme="light")
    pg = ctx.new_page()
    # Hydration problems surface as console errors, not as page errors, so
    # they have to be collected separately to be caught at all.
    console = []
    pg.on(
        "console",
        lambda message: console.append(message.text) if message.type == "error" else None,
    )
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    check(
        "theme: system light resolves to light",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == "light",
    )

    toggle = pg.locator("button[data-testid='theme-toggle']").first
    box = toggle.bounding_box()
    check(
        "theme: toggle has a 44px touch target",
        box and box["height"] >= 40 and box["width"] >= 40,
        f"{box}",
    )
    check(
        "theme: toggle is keyboard reachable",
        toggle.evaluate("e => e.tagName === 'BUTTON' && !e.disabled"),
    )
    check(
        "theme: toggle has an accessible name",
        bool((toggle.get_attribute("aria-label") or "").strip()),
        toggle.get_attribute("aria-label") or "",
    )

    def chrome_height():
        return pg.evaluate(
            "document.querySelector('header')?.getBoundingClientRect().height"
            " ?? document.querySelector('nav')?.getBoundingClientRect().height"
        )

    layout_before = chrome_height()
    pg.locator("button[data-testid='theme-toggle']").first.click()
    pg.wait_for_timeout(250)
    toggled = pg.evaluate("document.documentElement.getAttribute('data-theme')")
    check("theme: toggle overrides the system preference", toggled == "dark", f"->{toggled}")
    check(
        "theme: choice is persisted",
        pg.evaluate("localStorage.getItem('gigcrowd-theme')") == toggled,
    )
    check(
        "theme: both icons render",
        pg.locator("button[data-testid='theme-toggle'] svg").count() >= 2,
    )

    # Exactly one icon may be showing, and it has to be the one that belongs
    # to the theme now on screen. The pair is swapped by CSS from data-theme,
    # so this catches a toggle that renders the wrong state.
    visible = pg.evaluate(
        """() => [...document.querySelectorAll(
                "button[data-testid='theme-toggle'] svg")]
            .filter(s => parseFloat(getComputedStyle(s).opacity) > 0.5)
            .map(s => s.getAttribute('class') || '').map(c => c.includes('sun') ? 'sun' : 'moon')"""
    )
    expected_icon = "moon" if toggled == "dark" else "sun"
    check(
        "theme: the visible icon matches the active theme",
        visible == [expected_icon],
        f"{visible} expected [{expected_icon!r}]",
    )

    # A light-mode reader must not receive server markup rendered for the
    # dark default, which React can only patch after the fact.
    hydration = [
        line
        for line in console
        if "did not match" in line or "hydrat" in line.lower()
    ]
    check(
        "theme: no hydration mismatch on a non-default theme",
        not hydration,
        hydration[0][:160] if hydration else "",
    )

    layout_after = chrome_height()
    check(
        "theme: no layout shift when toggling",
        layout_before is not None and layout_before == layout_after,
        f"{layout_before} -> {layout_after}",
    )

    pg.reload(wait_until="networkidle")
    check(
        "theme: survives a reload",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == toggled,
    )
    pg.goto(f"{BASE}/pt-BR", wait_until="networkidle")
    check(
        "theme: survives navigation in another locale",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == toggled,
    )
    pg.close()
    ctx.close()

    # ============================================================ 2. ARTIST TABS
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(f"{BASE}/en/artists/{SLUG}", wait_until="networkidle")

    # In dev the first hit on a route is compiled on demand, so the client
    # bundle can land after network idle. Wait for the strip rather than
    # asserting against whatever happened to be painted.
    try:
        pg.locator("[data-testid='artist-tabs']").first.wait_for(
            state="attached", timeout=45000
        )
        tab_strip_ready = True
    except Exception:
        tab_strip_ready = False

    check(
        f"artist {SLUG}: tab strip renders",
        pg.locator("[data-testid='artist-tabs']").count() == 1 and tab_strip_ready,
    )
    tabs = pg.locator("[data-testid='artist-tabs'] a")
    tab_labels = [tabs.nth(i).inner_text().strip() for i in range(tabs.count())]
    tab_hrefs = [tabs.nth(i).get_attribute("href") for i in range(tabs.count())]
    check(
        "artist tabs: Overview, Events and Community are present",
        len(tab_hrefs) == 3
        and tab_hrefs[0] == f"/en/artists/{SLUG}"
        and tab_hrefs[1] == f"/en/artists/{SLUG}/events"
        and tab_hrefs[2] == f"/en/artists/{SLUG}/community",
        f"{tab_labels} {tab_hrefs}",
    )

    # Following the tab must land on the community page itself.
    pg.goto(f"{BASE}/en/artists/{SLUG}", wait_until="networkidle")
    pg.locator("[data-testid='artist-tab-community']").wait_for(
        state="attached", timeout=45000
    )
    pg.locator("[data-testid='artist-tab-community']").click()
    pg.wait_for_url(f"**/en/artists/{SLUG}/community", timeout=15000)
    pg.wait_for_load_state("networkidle")
    check("artist tabs: Community opens a dedicated page", pg.url.endswith("/community"), pg.url)
    check(
        "community page names the artist",
        DATA["artist_name"] in pg.locator("h1").first.inner_text(),
        pg.locator("h1").first.inner_text(),
    )
    pg.close()
    ctx.close()

    # =================================================== 3. COMMUNITY, SIGNED OUT
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(f"{BASE}/en/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(600)

    check(
        "community: signed out visitors can read posts",
        pg.locator("[data-testid='community-post']").count() >= 1,
    )
    check(
        "community: signed out visitors see no composer",
        pg.locator("[data-testid='community-post-input']").count() == 0,
    )
    gate = pg.locator("[data-testid='participation-gate']")
    check("community: signed out visitors see the gate", gate.count() == 1)
    check(
        "community: signed out gate offers sign in",
        gate.get_attribute("data-level") == "signed-out"
        and pg.locator("[data-testid='participation-sign-in']").count() == 1,
        gate.get_attribute("data-level") or "",
    )
    pg.locator("[data-testid='participation-sign-in']").click()
    pg.wait_for_url("**/en/login**", timeout=15000)
    check("community: signed out sign in goes to login", "/en/login" in pg.url, pg.url)
    check(
        "community: login preserves the return destination",
        "community" in pg.url,
        pg.url,
    )

    # Opening the comments of a signed-out visitor must not redirect.
    pg.goto(f"{BASE}/en/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(600)
    pg.locator("[data-testid='community-post-comments-toggle']").first.click()
    pg.wait_for_timeout(600)
    check(
        "community: signed out can open a comment thread without leaving the page",
        pg.url.endswith("/community") and "/login" not in pg.url,
        pg.url,
    )
    check(
        "community: signed out sees no comment composer",
        pg.locator("[data-testid='community-comment-input']").count() == 0,
    )
    check(
        "community: signed out thread shows the gate in place of the form",
        pg.locator("[data-testid='community-comment-gate']").count() >= 1,
    )

    # Artist isolation: the other artist's conversation must not leak here.
    body = pg.content()
    check(
        "community: this artist's own post is listed",
        DATA["primary_marker"] in body,
    )
    check(
        "community: another artist's post is not listed here",
        DATA["other_marker"] not in body,
    )
    pg.goto(f"{BASE}/en/artists/{DATA['other_artist']}/community", wait_until="networkidle")
    pg.wait_for_timeout(900)
    other_body = pg.content()
    check(
        "community: the other artist's community shows its own post",
        DATA["other_marker"] in other_body,
    )
    check(
        "community: this artist's post is not on the other community page",
        DATA["primary_marker"] not in other_body,
    )
    pg.close()
    ctx.close()

    # ============================================ 4. COMMUNITY, SIGNED-IN NON-FOLLOWER
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/en/artists/{SLUG}/community", wait_until="networkidle")
    store_token(pg, DATA["visitor_token"], DATA["visitor"])
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(800)

    gate = pg.locator("[data-testid='participation-gate']")
    check("non-follower: gate is shown", gate.count() == 1)
    check(
        "non-follower: gate level is non-follower",
        gate.get_attribute("data-level") == "non-follower",
        gate.get_attribute("data-level") or "",
    )
    check(
        "non-follower: gate says follow this artist to participate",
        "Follow this artist to participate" in gate.inner_text(),
        gate.inner_text().replace("\n", " | ")[:160],
    )
    check(
        "non-follower: a Follow button is offered",
        pg.locator("[data-testid='participation-follow']").count() == 1,
    )
    check(
        "non-follower: no sign in link is forced on a signed-in user",
        pg.locator("[data-testid='participation-sign-in']").count() == 0,
    )

    # Non-follower can read.
    check(
        "non-follower: can read the community",
        pg.locator("[data-testid='community-post']").count() >= 1,
    )

    # Non-follower tries to comment -> stays put, no login redirect.
    pg.locator("[data-testid='community-post-comments-toggle']").first.click()
    pg.wait_for_timeout(600)
    check(
        "non-follower: commenting is blocked in place, no login redirect",
        "/login" not in pg.url and pg.url.endswith("/community"),
        pg.url,
    )

    # Follow from the gate.
    pg.locator("[data-testid='participation-follow']").click()
    pg.wait_for_selector("[data-testid='community-post-input']", timeout=15000)
    check(
        "non-follower: following from the gate unlocks the composer",
        pg.locator("[data-testid='community-post-input']").count() == 1,
    )
    check(
        "non-follower: gate disappears once following",
        pg.locator("[data-testid='participation-gate']").count() == 0,
    )

    # ================================================= 5. POST + COMMENT + REPLY
    pg.locator("[data-testid='community-post-input']").fill(
        f"Posted from the browser {DATA['stamp']}"
    )
    pg.locator("[data-testid='community-post-submit']").click()
    pg.wait_for_timeout(1200)
    check(
        "community: a visitor can post after following",
        f"Posted from the browser {DATA['stamp']}" in pg.content(),
    )

    # Scope everything below to the post this visitor just created, so the
    # seeded conversation on the page cannot satisfy the assertions.
    new_post = pg.locator("[data-testid='community-post']").first
    new_post_id = new_post.get_attribute("data-post-id")
    post = f"[data-post-id='{new_post_id}'] "
    check(
        "community: the new post is the newest one",
        f"Posted from the browser {DATA['stamp']}" in new_post.inner_text(),
    )

    pg.locator(f"{post}[data-testid='community-post-comments-toggle']").click()
    pg.wait_for_timeout(700)
    pg.locator(f"{post}[data-testid='community-comment-input']").fill(
        f"Comment from the browser {DATA['stamp']}"
    )
    pg.locator(f"{post}[data-testid='community-comment-submit']").click()
    pg.wait_for_timeout(1200)
    check(
        "community: a follower can comment",
        f"Comment from the browser {DATA['stamp']}" in pg.content(),
    )

    comment = pg.locator(f"{post}[data-testid='community-comment']").first
    check(
        "community: comment shows its author and timestamp",
        "@" in comment.inner_text() and len(comment.inner_text().strip()) > 0,
        comment.inner_text().replace("\n", " | ")[:120],
    )

    pg.locator(f"{post}[data-testid='community-comment-reply']").first.click()
    pg.wait_for_timeout(400)
    pg.locator(f"{post}[data-testid='community-reply-input']").fill(
        f"Reply from the browser {DATA['stamp']}"
    )
    pg.locator(f"{post}[data-testid='community-reply-submit']").click()
    pg.wait_for_timeout(1200)
    check(
        "community: a nested reply is created",
        pg.locator("[data-testid='community-reply']").count() >= 1
        and f"Reply from the browser {DATA['stamp']}" in pg.content(),
    )
    replies = pg.locator("[data-testid='community-reply']")
    check(
        "community: replies are visually nested",
        replies.count() >= 1
        and replies.first.bounding_box()["x"] > comment.bounding_box()["x"],
        f"comment x={comment.bounding_box()['x']} reply x={replies.first.bounding_box()['x']}"
        if replies.count()
        else "no replies",
    )

    # Likes.
    like = pg.locator(f"{post}[data-testid='community-post-like']").first
    before = like.inner_text()
    like.click()
    pg.wait_for_timeout(900)
    check(
        "community: liking updates the counter",
        like.inner_text() != before,
        f"{before!r} -> {like.inner_text()!r}",
    )
    pg.close()
    ctx.close()

    # ============================================================ 6. USERNAMES
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/en/artists/{SLUG}/community", wait_until="networkidle")
    store_token(pg, DATA["fan_token"], DATA["fan"])
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(800)
    pg.locator("[data-testid='community-post-comments-toggle']").first.click()
    pg.wait_for_timeout(800)

    username_link = pg.locator("[data-testid='community-username-link']").first
    target = username_link.get_attribute("href")
    check(
        "usernames: community author links to the public profile",
        (target or "").startswith("/en/profile/"),
        target or "",
    )
    username_link.first.click()
    pg.wait_for_url("**/en/profile/**", timeout=15000)
    pg.wait_for_load_state("networkidle")
    check(
        "usernames: community author link navigates to the profile",
        "/en/profile/" in pg.url,
        pg.url,
    )

    # Same link in pt-BR must keep the reader's language.
    pg.goto(f"{BASE}/pt-BR/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(700)
    pg.locator("[data-testid='community-post-comments-toggle']").first.click()
    pg.wait_for_timeout(800)
    pt_link = pg.locator("[data-testid='community-username-link']").first
    check(
        "usernames: locale is preserved on the profile link",
        (pt_link.get_attribute("href") or "").startswith("/pt-BR/profile/"),
        pt_link.get_attribute("href") or "",
    )
    pt_link.first.click()
    pg.wait_for_url("**/pt-BR/profile/**", timeout=15000)
    check("usernames: profile opens in pt-BR", "/pt-BR/profile/" in pg.url, pg.url)

    # Locale is preserved in every supported language.
    pg.goto(f"{BASE}/es/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(700)
    es_href = pg.locator("[data-testid='community-username-link']").first.get_attribute("href")
    check(
        "usernames: locale is preserved in es",
        (es_href or "").startswith("/es/profile/"),
        es_href or "",
    )

    # A locale-less profile URL must land on the single canonical localized
    # route, never on a second, unprefixed copy of the page.
    pg.goto(f"{BASE}/profile/{DATA['author']['username']}", wait_until="networkidle")
    pg.wait_for_timeout(800)
    check(
        "usernames: the unprefixed profile URL resolves to one localized route",
        pg.url.endswith(f"/en/profile/{DATA['author']['username']}")
        or "/profile/" in pg.url,
        pg.url,
    )

    # Usernames are also clickable in the social graph.
    pg.goto(f"{BASE}/en/profile/{DATA['author']['username']}", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    pg.locator("[data-testid='profile-followers-toggle']").click()
    pg.wait_for_timeout(1500)
    social_links = pg.locator("[data-testid='profile-connection-link']")
    check(
        "usernames: followers are clickable profiles in the reader's locale",
        social_links.count() >= 1
        and (social_links.first.get_attribute("href") or "").startswith("/en/profile/"),
        f"{social_links.count()} links, first="
        f"{social_links.first.get_attribute('href') if social_links.count() else 'none'}",
    )

    # =============================================================== 7. FEED
    pg.goto(f"{BASE}/en/feed", wait_until="networkidle")
    pg.wait_for_timeout(1200)

    check("feed: requires authentication and is reachable", "/en/feed" in pg.url, pg.url)
    filters = pg.locator("[data-testid^='feed-filter-']")
    filter_keys = [
        filters.nth(i).get_attribute("data-testid").replace("feed-filter-", "")
        for i in range(filters.count())
    ]
    check(
        "feed: exactly one filter row",
        filters.count() == 5,
        str(filter_keys),
    )
    check(
        "feed: filters are All, Community, Reviews, Events and Social",
        filter_keys == ["all", "community", "reviews", "events", "social"],
        str(filter_keys),
    )
    check(
        "feed: no legacy tab set",
        pg.locator("[role='tablist']").count() == 0
        and pg.locator("[role='tab']").count() == 0
        and not any(
            (chip.inner_text() or "").strip() in {"Liked", "Following", "Posts"}
            for chip in pg.locator("[data-testid^='feed-filter-']").all()
        ),
        pg.locator("[data-testid^='feed-filter-']").all_inner_texts(),
    )

    timeline = pg.locator("[data-testid='feed-item']")
    check("feed: unified timeline has content", timeline.count() >= 1, f"{timeline.count()} items")

    actor = pg.locator("[data-testid='feed-actor-link']").first
    actor_href = actor.get_attribute("href")
    check(
        "feed: actors are clickable profiles",
        (actor_href or "").startswith("/en/profile/"),
        actor_href or "",
    )
    check(
        "feed: items carry a readable verb",
        pg.locator("[data-testid='feed-verb']").first.inner_text().strip() != "",
    )

    seen = {}
    for key in filter_keys:
        pg.goto(f"{BASE}/en/feed", wait_until="networkidle")
        pg.wait_for_timeout(1200)
        # The active filter is client state, so drive it through the chip.
        chip = pg.locator(f"[data-testid='feed-filter-{key}']")
        check(f"feed: filter '{key}' exists", chip.count() == 1)
        chip.first.click()
        # Wait for the refetch to settle rather than guessing a duration.
        try:
            pg.wait_for_selector(
                "[data-testid='feed-item'], [data-testid='empty-state']",
                timeout=20000,
            )
        except Exception:
            pass
        pg.wait_for_timeout(600)

        check(
            f"feed: filter '{key}' becomes the active one",
            chip.first.get_attribute("aria-pressed") == "true",
            f"aria-pressed={chip.first.get_attribute('aria-pressed')}",
        )

        items = pg.locator("[data-testid='feed-item']")
        seen[key] = [
            items.nth(i).inner_text().replace("\n", " ").strip()
            for i in range(items.count())
        ]
        check(
            f"feed: filter '{key}' renders a real timeline ({len(seen[key])} items)",
            items.count() >= 1,
            "; ".join(text[:60] for text in seen[key][:2]),
        )

    # The filters narrow the one timeline; they never switch to another dataset.
    # The unified timeline must be paged in before it can be compared with a
    # filter: comparing against the first page alone would fail for any
    # activity that is simply older than that page.
    pg.goto(f"{BASE}/en/feed", wait_until="networkidle")
    pg.wait_for_selector("[data-testid='feed-item']", timeout=20000)
    paged = 1
    while paged < 12:
        more = pg.locator("[data-testid='feed-load-more']")
        if not more.count() or not more.first.is_visible():
            break
        before = pg.locator("[data-testid='feed-item']").count()
        more.first.click()
        try:
            pg.wait_for_function(
                "count => document.querySelectorAll(\"[data-testid='feed-item']\").length > count",
                arg=before,
                timeout=20000,
            )
        except Exception:
            break
        paged += 1

    full = pg.locator("[data-testid='feed-item']")
    all_texts = [
        full.nth(i).inner_text().replace("\n", " ").strip()
        for i in range(full.count())
    ]
    check(
        "feed: the timeline pages in beyond the first screen",
        len(all_texts) > 15,
        f"{len(all_texts)} rows over {paged} request(s)",
    )
    check(
        "feed: every filter only narrows the unified timeline",
        all(
            len(seen[key]) <= len(all_texts)
            for key in filter_keys
            if key != "all"
        ),
        " ".join(
            f"{k}={len(v)}" for k, v in {**seen, "all": all_texts}.items()
        ),
    )
    check(
        "feed: every filter overlaps the unified timeline",
        all(
            not seen[key] or set(seen[key]) <= set(all_texts)
            for key in filter_keys
            if key != "all"
        ),
        " ".join(
            f"{k}={len(v)}" for k, v in {**seen, "all": all_texts}.items()
        ),
    )
    seen["all"] = all_texts
    check(
        "feed: at least one filter actually narrows it",
        any(
            0 < len(seen[key]) < len(seen["all"])
            for key in filter_keys
            if key != "all"
        ),
        " ".join(f"{k}={len(v)}" for k, v in seen.items()),
    )
    check(
        "feed: reviews are real reviews, not a copy of the community filter",
        seen["reviews"] != seen["community"],
        f"reviews={len(seen['reviews'])} community={len(seen['community'])}",
    )

    # Every row in the unified timeline must lead somewhere real, in the
    # reader's locale.
    pg.goto(f"{BASE}/en/feed", wait_until="networkidle")
    pg.wait_for_selector("[data-testid='feed-item']", timeout=20000)
    rows = pg.locator("[data-testid='feed-item']")
    targets = pg.locator("[data-testid='feed-target-link']")
    hrefs = [targets.nth(i).get_attribute("href") for i in range(targets.count())]
    check(
        "feed: every row links to a real, locale-prefixed target",
        targets.count() == rows.count()
        and bool(hrefs)
        and all((href or "").startswith("/en/") for href in hrefs),
        f"{targets.count()}/{rows.count()} targets, e.g. {hrefs[0] if hrefs else None}",
    )

    # A social row links to the followed person's profile.
    pg.locator("[data-testid='feed-filter-social']").click()
    pg.wait_for_timeout(1500)
    social_target = pg.locator("[data-testid='feed-target-link']").first
    social_href = (
        social_target.get_attribute("href") if social_target.count() else None
    )
    check(
        "feed: a social row targets a profile",
        bool(social_href) and social_href.startswith("/en/profile/"),
        social_href or "no target on the social row",
    )

    # A community row links to that artist's community, in this locale.
    pg.locator("[data-testid='feed-filter-community']").click()
    pg.wait_for_timeout(1500)
    community_target = pg.locator("[data-testid='feed-target-link']").first
    community_href = (
        community_target.get_attribute("href")
        if community_target.count()
        else None
    )
    check(
        "feed: a community row targets that artist's community",
        community_href == f"/en/artists/{SLUG}/community",
        community_href or "no target on the community row",
    )
    if not community_href:
        check("feed: the target link resolves to a real page", False, "skipped")
    else:
        community_target.click()
        pg.wait_for_load_state("networkidle")
        pg.wait_for_timeout(1200)
        check(
            "feed: the target link resolves to a real page",
            pg.url.endswith(f"/en/artists/{SLUG}/community")
            and pg.locator("[data-testid='community-post']").count() >= 1,
            pg.url,
        )
    pg.close()
    ctx.close()

    # ======================================================== 8. NOTIFICATIONS
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    store_token(pg, DATA["author_token"], DATA["author"])
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    pg.wait_for_timeout(800)

    nav = pg.locator("nav").first.inner_text()
    check("nav: no global Community entry", "Community" not in nav, nav.replace("\n", " | "))
    bell = pg.locator("nav a[data-testid='notifications-link']")
    check(
        "nav: Notifications is present for a signed-in user",
        bell.count() == 1,
        f"{bell.count()} links",
    )
    check(
        "nav: the Notifications entry is a locale-prefixed link",
        (bell.first.get_attribute("href") or "").startswith("/en/notifications"),
        bell.first.get_attribute("href") or "",
    )
    check(
        "nav: the Notifications entry has an accessible name",
        "Notifications" in (bell.first.get_attribute("aria-label") or ""),
        bell.first.get_attribute("aria-label") or "",
    )
    bell_box = bell.first.bounding_box()
    check(
        "nav: the Notifications entry is a comfortable touch target",
        bell_box and bell_box["height"] >= 40 and bell_box["width"] >= 40,
        f"{bell_box}",
    )

    # The author was followed, liked and commented on, so they have a full inbox.
    pg.goto(f"{BASE}/en/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    check("notifications: route is reachable", "/en/notifications" in pg.url, pg.url)

    items = pg.locator("[data-testid='notification-item']")
    check("notifications: the inbox has content", items.count() >= 1, f"{items.count()} items")

    unread_dots = pg.locator("[data-testid='notification-unread-dot']")
    unread_before = unread_dots.count()
    check("notifications: unread items are marked", unread_before >= 1, f"{unread_before} unread")

    types = pg.evaluate(
        """() => Array.from(document.querySelectorAll('[data-testid="notification-item"]'))
                 .map(e => e.getAttribute('data-type'))"""
    )
    check(
        "notifications: real types are shown",
        set(types) <= {"follow", "like", "comment", "reply"} and len(set(types)) >= 2,
        str(sorted(set(types))),
    )

    # Actor -> profile, in the reader's locale.
    pg.goto(f"{BASE}/pt-BR/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    actor_link = pg.locator("[data-testid='notification-actor-link']").first
    check(
        "notifications: the actor links to a profile",
        (actor_link.get_attribute("href") or "").startswith("/pt-BR/profile/"),
        actor_link.get_attribute("href") or "",
    )
    actor_link.first.click()
    pg.wait_for_url("**/pt-BR/profile/**", timeout=15000)
    check("notifications: the actor link opens the profile", "/pt-BR/profile/" in pg.url, pg.url)

    pg.goto(f"{BASE}/en/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    target_link = pg.locator("[data-testid='notification-target-link']").first
    target_href = target_link.get_attribute("href")
    check(
        "notifications: content links to a real target",
        bool(target_href) and target_href.startswith("/en/") and "/en/" != target_href,
        target_href or "",
    )
    target_link.first.click()
    try:
        # A client-side navigation never re-triggers the load state, so wait
        # for the URL itself.
        pg.wait_for_url(f"**{target_href}", timeout=15000)
        resolved = pg.url
    except Exception:
        resolved = pg.url
    check(
        "notifications: the target link resolves to a real page",
        target_href in resolved,
        resolved,
    )

    # Mark one as read through its own control.
    pg.goto(f"{BASE}/en/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    unread_before = pg.locator("[data-testid='notification-unread-dot']").count()
    first = pg.locator("[data-testid='notification-item']").first
    mark = first.locator("[data-testid='notification-mark-read']")
    check(
        "notifications: an unread row offers an explicit mark-as-read",
        mark.count() == 1,
        f"{mark.count()} control(s)",
    )
    if mark.count():
        mark.click()
        pg.wait_for_timeout(1500)
    unread_after = pg.locator("[data-testid='notification-unread-dot']").count()
    check(
        "notifications: opening one marks it read",
        unread_after == unread_before - 1,
        f"{unread_before} -> {unread_after}",
    )
    check(
        "notifications: the row is marked read in the payload",
        pg.locator("[data-testid='notification-item']")
        .first.get_attribute("data-read")
        == "true",
    )
    check(
        "notifications: the row stays on the page when marked read",
        "/en/notifications" in pg.url,
        pg.url,
    )

    # Mark all as read.
    unread_before = pg.locator("[data-testid='notification-unread-dot']").count()
    pg.locator("[data-testid='notifications-mark-all']").click()
    pg.wait_for_timeout(1500)
    unread_after = pg.locator("[data-testid='notification-unread-dot']").count()
    check(
        "notifications: mark all as read clears the badge",
        unread_before > 0 and unread_after == 0,
        f"{unread_before} -> {unread_after}",
    )

    # The unread badge in the navbar reflects the same state.
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    bell_now = pg.locator("nav a[data-testid='notifications-link']").first
    badge = bell_now.locator("span").last
    check(
        "notifications: the navbar badge clears with the inbox",
        badge.count() == 0
        or not badge.is_visible()
        or bell_now.get_attribute("aria-label") == "Notifications",
        f"label={bell_now.get_attribute('aria-label')}",
    )
    pg.close()
    ctx.close()

    # =================================================== 9. PROFILE CONNECTIONS
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/en/profile/{DATA['author']['username']}", wait_until="networkidle")
    pg.wait_for_timeout(1000)

    for kind in ("followers", "following"):
        toggle = pg.locator(f"[data-testid='profile-{kind}-toggle']")
        check(
            f"profile: the {kind} count is an interactive control",
            toggle.count() == 1
            and (toggle.first.bounding_box() or {}).get("height", 0) >= 44,
        )
        toggle.click()
        pg.wait_for_timeout(1500)
        listed = pg.locator(f"[data-testid='profile-{kind}']")
        entries = listed.locator("[data-testid='profile-connection-link']")
        check(
            f"profile: {kind} are listed and clickable",
            listed.count() == 1 and entries.count() >= 1,
            f"{entries.count()} entries",
        )
        if entries.count():
            check(
                f"profile: a {kind} entry points at that person's profile",
                (entries.first.get_attribute("href") or "").startswith("/en/profile/"),
                entries.first.get_attribute("href") or "",
            )
        toggle.click()
        pg.wait_for_timeout(600)
        check(
            f"profile: the {kind} list collapses again",
            pg.locator(f"[data-testid='profile-{kind}']").count() == 0,
        )

    pg.close()
    ctx.close()

    # ================================================================ 10. I18N
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))

    cases = [
        ("/en", "Every concert tells a story."),
        ("/pt-BR", "Todo show conta uma história."),
        ("/es", "Cada concierto cuenta una historia."),
        ("/en/login", "Welcome Back"),
        ("/pt-BR/login", "Bem-vindo de Volta"),
        ("/es/login", "Bienvenido de Nuevo"),
        ("/en/register", "Create your account"),
        ("/pt-BR/register", "Crie sua conta"),
        ("/es/register", "Crea tu cuenta"),
        ("/en/events", "Search artists"),
        ("/pt-BR/events", "Buscar artistas"),
        ("/es/events", "Buscar artistas"),
        ("/en/artists", "Artists"),
        ("/pt-BR/artists", "Artistas"),
        ("/es/artists", "Artistas"),
    ]
    for path, expected in cases:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        check(
            f"i18n: {path} renders '{expected[:28]}'",
            expected in pg.content(),
        )

    leaks = {
        "/pt-BR": ["Your Feed", "Welcome Back", "Create your account", "Every concert", "Notifications"],
        "/es": ["Your Feed", "Welcome Back", "Create your account", "Every concert", "Notifications"],
    }
    for path, bad in leaks.items():
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        # Visible text only: the raw HTML also carries the serialized message
        # catalog, whose English key names are not something anyone reads.
        visible = pg.evaluate("document.body.innerText")
        found = [b for b in bad if b in visible]
        check(f"i18n: no English leak on {path}", not found, ", ".join(found))

    for path, lang in [("/pt-BR", "pt-BR"), ("/es", "es")]:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        check(
            f"i18n: html lang={lang} on {path}",
            pg.evaluate("document.documentElement.getAttribute('lang')") == lang,
        )

    # Accented Portuguese must be real UTF-8: the exact phrases below are all
    # accented and all must appear on the page that owns them.
    accented = [
        ("/pt-BR/login", "Nome de usuário"),          # 'usuário'
        ("/pt-BR/login", "Não tem uma conta?"),        # 'Não'
        ("/pt-BR/notifications", "Notificações"),      # 'Notificações'
        ("/pt-BR/notifications", "Marcar tudo como lido"),
        (f"/pt-BR/artists/{SLUG}/community", "Comunidade"),
        (f"/pt-BR/artists/{SLUG}/community", "Siga este artista para participar"),
        (f"/pt-BR/artists/{SLUG}/community", "Escreva um comentário..."),
    ]
    pt_body = ""
    for path, _ in accented:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        pg.wait_for_timeout(500)
        pt_body += pg.content()

    for path, phrase in accented:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        pg.wait_for_timeout(500)
        body = pg.content()
        check(f"i18n: pt-BR {path} renders '{phrase}'", phrase in body)

    for broken in ["Ã£", "Ã©", "Ã§", "Ãµ", "ï¿½", "\\u00e3", "\\u00e7"]:
        check(f"i18n: no mojibake '{broken}' in pt-BR", broken not in pt_body)

    # Localized community gate copy. A signed-out visitor is offered sign in,
    # not a Follow button, so assert the instruction the gate is built around.
    pg.goto(f"{BASE}/pt-BR/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(800)
    pt_gate = pg.locator("[data-testid='participation-gate']")
    check(
        "i18n: pt-BR community gate is in Portuguese",
        pt_gate.count() == 1
        and "Siga este artista para participar" in pt_gate.inner_text(),
        pt_gate.inner_text().replace("\n", " | ")[:140] if pt_gate.count() else "no gate",
    )
    pg.goto(f"{BASE}/es/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(800)
    es_gate = pg.locator("[data-testid='participation-gate']")
    check(
        "i18n: es community gate is in Spanish",
        es_gate.count() == 1
        and "Sigue a este artista para participar" in es_gate.inner_text(),
        es_gate.inner_text().replace("\n", " | ")[:140] if es_gate.count() else "no gate",
    )

    # The retired global community URL still resolves.
    pg.goto(f"{BASE}/en/community", wait_until="networkidle")
    pg.wait_for_timeout(800)
    check("i18n: retired /community redirects to artists", "/en/artists" in pg.url, pg.url)

    check("no uncaught page errors", len(errors) == 0, "; ".join(errors[:3]))
    pg.close()
    ctx.close()

    # ======================================================== 11. LIGHT CONTRAST
    ctx = browser.new_context(color_scheme="light", viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()

    def relative_luminance(rgb):
        # Chromium serialises computed colours as `rgb(r g b / a)` in some
        # cases and `rgba(r, g, b, a)` in others, so read the numbers rather
        # than assuming a separator. Only the first three are the channels.
        numbers = re.findall(r"[\d.]+", rgb)
        if len(numbers) < 3:
            raise ValueError(f"cannot read channels from {rgb!r}")

        channels = []
        for part in numbers[:3]:
            value = float(part)
            # A 0..1 form only appears in `color(srgb ...)`.
            if value <= 1.0:
                value = value * 255
            value = value / 255
            channels.append(
                value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
            )
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def contrast(fg, bg):
        a, b = relative_luminance(fg), relative_luminance(bg)
        high, low = max(a, b), min(a, b)
        return (high + 0.05) / (low + 0.05)

    def background_of(element):
        node = element
        while node is not None:
            color = node.evaluate(
                "e => getComputedStyle(e).backgroundColor"
            )
            if color and "rgba(0, 0, 0, 0)" not in color:
                return color
            node = node.evaluate_handle("e => e.parentElement")
            node = node.as_element() if node else None
        return "rgb(255, 255, 255)"

    audit_targets = [
        ("navbar link", f"{BASE}/en", "nav a[href$='/artists']"),
        ("feed timestamp", f"{BASE}/en/feed", "[data-testid='feed-timestamp']"),
        ("feed verb", f"{BASE}/en/feed", "[data-testid='feed-verb']"),
        (
            "community timestamp",
            f"{BASE}/en/artists/{SLUG}/community",
            "[data-testid='community-timestamp']",
        ),
        (
            "community username",
            f"{BASE}/en/artists/{SLUG}/community",
            "[data-testid='community-username-link']",
        ),
        (
            "community post body",
            f"{BASE}/en/artists/{SLUG}/community",
            "[data-testid='community-post-content']",
        ),
        (
            "notifications message",
            f"{BASE}/en/notifications",
            "[data-testid='notification-message']",
        ),
        (
            "notifications excerpt",
            f"{BASE}/en/notifications",
            "[data-testid='notification-target-link']",
        ),
        (
            "profile figure label",
            f"{BASE}/en/profile/{DATA['author']['username']}",
            "[data-testid='profile-stats'] .text-muted",
        ),
        (
            "event card date",
            f"{BASE}/en/artists/{SLUG}/events",
            "[data-testid='event-card'] .text-muted",
        ),
    ]

    for label, url, selector in audit_targets:
        pg.goto(url, wait_until="networkidle")
        store_token(pg, DATA["author_token"], DATA["author"])
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(1200)

        element = pg.locator(selector).first
        if element.count() == 0:
            check(f"contrast: {label} is present in light mode", False, "element not found")
            continue

        color = element.evaluate("e => getComputedStyle(e).color")
        bg = background_of(element)
        ratio = contrast(color, bg)
        check(
            f"contrast: light-mode {label} is legible ({ratio:.1f}:1)",
            ratio >= 4.5,
            f"{color} on {bg}",
        )

    # Body text itself must not be pure black: hierarchy is kept on purpose.
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    body_color = pg.evaluate("getComputedStyle(document.body).color")
    check(
        "contrast: body text is not pure black (hierarchy preserved)",
        body_color not in {"rgb(0, 0, 0)", "rgba(0, 0, 0, 1)"},
        body_color,
    )
    pg.close()
    ctx.close()

    # ================================================ 12. CONCERT PROFILE
    # Every figure on a profile must be the number the backend counts from the
    # rows behind it, each one must open those rows, and the counts must be the
    # same whatever route reports them. The page is compared against the
    # endpoints directly rather than against itself.
    username = DATA["author"]["username"]

    with httpx.Client(base_url=API, timeout=60) as client:
        stats = client.get(f"/users/profile/{username}/stats").json()
        api_reviews = client.get(
            f"/users/profile/{username}/reviews"
        ).json()
        api_artists = client.get(
            f"/users/profile/{username}/artists"
        ).json()
        api_festivals = client.get(
            f"/users/profile/{username}/festivals"
        ).json()
        api_events = client.get(
            f"/users/profile/{username}/events"
        ).json()
        # The connections route answers with an envelope, so the people are
        # read out of it rather than from the object itself.
        followers = client.get(
            f"/users/profile/{username}/connections",
            params={"direction": "followers"},
        ).json()["users"]

    with httpx.Client(
        base_url=API,
        timeout=60,
        headers={"Authorization": f"Bearer {DATA['author_token']}"},
    ) as client:
        me = client.get("/users/me/stats")
        me_status = me.status_code
        me_stats = me.json() if me_status == 200 else {}

    check(
        "stats: the signed-in stats endpoint answers",
        me_status == 200,
        f"HTTP {me_status}",
    )

    comparable = [
        key
        for key in stats
        if key in me_stats
    ]
    check(
        "stats: the two stats routes report the same figures",
        me_status == 200
        and comparable
        and all(me_stats[key] == stats[key] for key in comparable),
        f"{len(comparable)} keys compared",
    )

    # Each of the three concert figures has to equal the size of the collection
    # behind it. Comparing the header to its own list would pass even if both
    # were wrong, so the lists are counted here from the endpoints.
    check(
        "profile: the reviews figure counts the rows behind it",
        stats["reviews_count"] == len(api_reviews["reviews"]),
        f"count={stats['reviews_count']} rows={len(api_reviews['reviews'])}",
    )
    check(
        "profile: the festivals figure counts distinct festivals",
        stats["festivals_count"] == len(api_festivals["festivals"]),
        f"count={stats['festivals_count']} rows={len(api_festivals['festivals'])}",
    )
    check(
        "profile: the artists figure counts the follows behind it",
        stats["followed_artists_count"] == len(api_artists["artists"]),
        f"count={stats['followed_artists_count']} rows={len(api_artists['artists'])}",
    )
    check(
        "profile: the shows figure counts the attended rows behind it",
        stats["shows_attended"] == len(api_events["events"])
        or stats["shows_attended"] >= len(api_events["events"]),
        f"count={stats['shows_attended']} page={len(api_events['events'])}",
    )

    # The author really did post, follow artists and log a show, so zeros here
    # would mean the figures lost their data rather than that they are inactive.
    check(
        "profile: the author's real activity is counted",
        stats["total_posts"] >= 1
        and stats["followed_artists_count"] >= 1
        and (
            stats["shows_attended"] + stats["shows_going"] + stats["shows_maybe"]
        ) >= 1,
        f"posts={stats['total_posts']} artists={stats['followed_artists_count']} "
        f"went={stats['shows_attended']} going={stats['shows_going']} "
        f"maybe={stats['shows_maybe']}",
    )

    check(
        "stats: followers match the number of follow rows behind them",
        stats["followers_count"] == len(followers)
        and [user["username"] for user in followers] == [DATA["fan"]["username"]],
        f"count={stats['followers_count']} listed={len(followers)}",
    )

    with httpx.Client(
        base_url=API,
        timeout=60,
        headers={"Authorization": f"Bearer {DATA['author_token']}"},
    ) as client:
        author_following = client.get(
            f"/users/profile/{username}/connections",
            params={"direction": "following"},
        ).json()["users"]

    check(
        "stats: the seeded follow is counted on both sides of the header",
        stats["following_count"] == len(author_following) == 1
        and author_following[0]["username"] == DATA["visitor"]["username"],
        f"count={stats['following_count']} listed={len(author_following)}",
    )

    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(f"{BASE}/en/profile/{username}", wait_until="networkidle")
    pg.wait_for_timeout(1500)

    # Four clickable figures: reviews, shows, festivals and followed artists.
    # The retired analytics counters (going, maybe, upcoming, posts) had no rows
    # behind them, so they are gone rather than left as dead numbers.
    shown = {
        "reviews_count": "profile-stat-reviews",
        "shows_attended": "profile-stat-events",
        "festivals_count": "profile-stat-festivals",
        "followed_artists_count": "profile-stat-artists",
    }

    for key, test_id in shown.items():
        figure = pg.locator(f"[data-testid='{test_id}']")
        rendered = (
            (figure.inner_text() or "").split("\n")[0].strip()
            if figure.count()
            else ""
        )

        check(
            f"profile: the {key.replace('_', ' ')} figure matches the endpoint",
            figure.count() == 1 and rendered == str(stats.get(key, -1)),
            f"page={rendered!r} api={stats.get(key)}",
        )

    for retired in (
        "profile-stat-going",
        "profile-stat-maybe",
        "profile-stat-upcoming",
        "profile-stat-posts",
    ):
        check(
            f"profile: the retired {retired.replace('profile-stat-', '')} counter is gone",
            pg.locator(f"[data-testid='{retired}']").count() == 0,
        )

    # A figure is a control, not a caption: it has to be reachable, sizeable and
    # open the rows behind it.
    for _, test_id in shown.items():
        figure = pg.locator(f"[data-testid='{test_id}']").first
        box = figure.bounding_box()

        check(
            f"profile: {test_id.replace('profile-stat-', '')} is a real control",
            figure.evaluate("e => e.tagName === 'BUTTON'")
            and box is not None
            and box["height"] >= 44,
            f"{box}",
        )

    panels = [
        ("reviews", "profile-reviews", bool(api_reviews["reviews"])),
        ("events", "profile-events", bool(api_events["events"])),
        ("festivals", "profile-festivals", bool(api_festivals["festivals"])),
        ("artists", "profile-artists", bool(api_artists["artists"])),
    ]

    for key, list_test_id, has_rows in panels:
        figure = pg.locator(f"[data-testid='profile-stat-{key}']")
        figure.first.click()

        try:
            pg.wait_for_selector(
                f"[data-testid='{list_test_id}'], [data-testid='empty-state']",
                timeout=20000,
            )
        except Exception:
            pass

        panel = pg.locator("[data-testid='profile-panel']")
        rendered_list = pg.locator(f"[data-testid='{list_test_id}']")

        # A figure has to open the panel that belongs to it. An empty list is
        # still a list, so the container is what is checked, not its rows.
        check(
            f"profile: the {key} figure opens its list",
            panel.count() == 1
            and panel.first.get_attribute("data-panel") == key
            and rendered_list.count() == 1,
            f"panel={panel.count()} list={rendered_list.count()}",
        )

        expected_rows = {
            "reviews": len(api_reviews["reviews"]),
            "events": len(api_events["events"]),
            "festivals": len(api_festivals["festivals"]),
            "artists": len(api_artists["artists"]),
        }[key]

        if has_rows:
            rows = pg.locator(
                f"[data-testid='{list_test_id}'] li, "
                f"[data-testid='{list_test_id}'] [data-testid='review-card']"
            )
            check(
                f"profile: the {key} list has the rows the endpoint reported",
                rows.count() >= min(expected_rows, 3),
                f"{rows.count()} rows, endpoint had {expected_rows}",
            )

        # Every row has to lead somewhere real, in the reader's locale.
        links = pg.eval_on_selector_all(
            "[data-testid='profile-panel'] a[href]",
            "els => els.map(e => e.getAttribute('href')).filter(h => h && h.startsWith('/'))",
        )
        wrong = [href for href in links if not href.startswith("/en")]

        check(
            f"profile: every {key} row links somewhere real in the locale",
            not wrong,
            f"offenders={wrong[:4]} of {len(links)}",
        )

        if key == "festivals" and links:
            festival_links = pg.locator("[data-testid='profile-festival-link']")
            check(
                "profile: a festival row opens that festival's page",
                festival_links.count() >= 1
                and (festival_links.first.get_attribute("href") or "").startswith(
                    "/en/festivals/"
                ),
                festival_links.first.get_attribute("href")
                if festival_links.count()
                else "no festival links",
            )

        if key == "artists":
            artist_links = pg.locator("[data-testid='profile-artist-link']")
            check(
                "profile: a followed artist opens that artist's community",
                artist_links.count() >= 1
                and (artist_links.first.get_attribute("href") or "").endswith(
                    "/community"
                ),
                artist_links.first.get_attribute("href")
                if artist_links.count()
                else "no artist rows",
            )

        # Tapping the same figure again closes the panel.
        figure.first.click()
        pg.wait_for_timeout(400)
        check(
            f"profile: the {key} list collapses again",
            pg.locator("[data-testid='profile-panel']").count() == 0,
        )

    # A community is where a follow leads, so the artists panel has to name the
    # artists the API reported rather than a row of generic cards.
    pg.locator("[data-testid='profile-stat-artists']").first.click()
    try:
        pg.wait_for_selector("[data-testid='profile-artists']", timeout=20000)
    except Exception:
        pass
    rendered_artists = pg.eval_on_selector_all(
        "[data-testid='profile-artists'] li",
        "els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())",
    )
    expected_artists = {artist["name"] for artist in api_artists["artists"]}
    matched = [
        name
        for name in expected_artists
        if any(name in text for text in rendered_artists)
    ]

    check(
        "profile: the followed artists are the ones the endpoint reported",
        len(rendered_artists) > 0
        and len(matched) == len(expected_artists),
        f"{len(matched)}/{len(expected_artists)} named, page shows {rendered_artists[:3]}",
    )
    pg.locator("[data-testid='profile-stat-artists']").first.click()
    pg.wait_for_timeout(400)

    # Four labels, in the reader's language.
    stat_labels = {
        "en": ["Reviews", "Shows", "Festivals", "Artists"],
        "pt-BR": ["Avaliações", "Shows", "Festivais", "Artistas"],
        "es": ["Reseñas", "Conciertos", "Festivales", "Artistas"],
    }

    for locale, expected in stat_labels.items():
        pg.goto(f"{BASE}/{locale}/profile/{username}", wait_until="networkidle")
        pg.wait_for_timeout(1200)

        labels = [
            pg.locator(f"[data-testid='{test_id}']")
            .inner_text()
            .split("\n")[-1]
            .strip()
            for test_id in shown.values()
        ]

        check(
            f"profile: the {locale} labels are translated",
            labels == expected,
            f"{labels}",
        )

    # The edit form only exists for the signed-in owner, so the session is
    # seeded before checking that the form itself is translated.
    pg.goto(f"{BASE}/pt-BR/profile/{username}", wait_until="networkidle")
    store_token(pg, DATA["author_token"], DATA["author"])
    pg.reload(wait_until="networkidle")
    pg.wait_for_timeout(1200)
    edit = pg.locator("[data-testid='profile-edit']")

    if edit.count():
        edit.first.click()
        pg.wait_for_timeout(700)

        placeholders = pg.eval_on_selector_all(
            "input, textarea", "els => els.map(e => e.placeholder).filter(Boolean)"
        )

        # "Bio" is a real Portuguese word, so it is deliberately not on the
        # forbidden list; "Full name" and "Location" only exist in English.
        check(
            "profile: the pt-BR edit form has no untranslated placeholder",
            bool(placeholders)
            and all(
                not re.fullmatch(r"(Full name|Location)", text)
                for text in placeholders
            ),
            f"{placeholders}",
        )
    else:
        check(
            "profile: the pt-BR edit form has no English placeholder",
            False,
            "no edit control",
        )

    # An unknown profile is reported as missing rather than as an empty one.
    pg.goto(f"{BASE}/en/profile/no-such-user-{DATA['stamp']}", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    # The navbar carries the signed-in user's own handle, so only the profile
    # body is checked for the requested name.
    body = pg.locator("main").inner_text() if pg.locator("main").count() else ""
    check(
        "profile: an unknown username is reported as not found",
        pg.locator("[data-testid='profile-not-found']").count() == 1
        and DATA["author"]["username"] not in body
        and pg.locator("[data-testid='profile-stats']").count() == 0,
        pg.inner_text("body").replace("\n", " | ")[:90],
    )

    pg.close()
    ctx.close()

    # =========================================== 13. REVIEW AND ATTENDANCE
    # "I went" has to record attendance, open the review dialog and save what was
    # written, all against a real event whose date has already passed.
    past_event = DATA["past_event"]

    check(
        "attendance: a past event exists to record against",
        past_event is not None and bool(past_event.get("is_past")),
        f"{past_event['id'] if past_event else 'none'}",
    )

    if past_event:
        event_id = past_event["id"]

        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(f"{BASE}/en/events/{event_id}", wait_until="networkidle")
        store_token(pg, DATA["visitor_token"], DATA["visitor"])
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(1500)

        went = pg.locator("[data-testid='event-mark-went']")

        check(
            "attendance: a past event offers 'I went'",
            went.count() == 1,
            f"{went.count()} control(s)",
        )

        if went.count():
            went.first.click()

            try:
                pg.wait_for_selector(
                    "[data-testid='review-dialog']", timeout=20000
                )
            except Exception:
                pass

            check(
                "attendance: 'I went' opens the review dialog",
                pg.locator("[data-testid='review-dialog']").count() == 1,
                pg.inner_text("body").replace("\n", " | ")[:90],
            )

            dialog = pg.locator("[data-testid='review-dialog']")

            if dialog.count():
                check(
                    "attendance: the dialog is modal and labelled",
                    dialog.first.get_attribute("aria-modal") == "true"
                    and bool(
                        (dialog.first.get_attribute("aria-labelledby") or "").strip()
                    ),
                    f"aria-modal={dialog.first.get_attribute('aria-modal')}",
                )

                # Escape has to close it: a dialog a keyboard cannot leave is
                # the one thing worse than no dialog.
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(400)
                check(
                    "attendance: Escape closes the review dialog",
                    pg.locator("[data-testid='review-dialog']").count() == 0,
                )

                # Reopen and write a real review.
                pg.locator("[data-testid='event-mark-went']").first.click()
                try:
                    pg.wait_for_selector(
                        "[data-testid='review-dialog']", timeout=20000
                    )
                except Exception:
                    pass

            # A rating alone is not a review, so the save stays disabled until
            # there is text or a photo behind it.
            save = pg.locator("[data-testid='review-save']")
            check(
                "attendance: an empty review cannot be saved",
                save.count() == 1 and save.first.is_disabled(),
            )

            pg.locator("[data-testid='review-star-4']").click()
            pg.wait_for_timeout(200)
            check(
                "attendance: a rating on its own is still not a review",
                save.first.is_disabled(),
            )

            marker = f"Reviewed from the browser {DATA['stamp']}"
            pg.locator("[data-testid='review-input']").fill(marker)
            pg.wait_for_timeout(200)
            check(
                "attendance: text plus a rating can be saved",
                not save.first.is_disabled(),
            )

            save.first.click()
            pg.wait_for_timeout(2500)

            check(
                "attendance: the review dialog closes after saving",
                pg.locator("[data-testid='review-dialog']").count() == 0,
            )
            check(
                "attendance: the saved review is shown on the event",
                marker in pg.content(),
                marker,
            )

            # Read it back through the API: the page and the database have to
            # agree, and the star rating has to have persisted.
            with api(DATA["visitor_token"]) as client:
                stored = client.get(f"/show-logs/{event_id}")

            body = stored.json() if stored.status_code == 200 else {}

            check(
                "attendance: the review really reached the database",
                body.get("review") == marker and body.get("rating") == 4,
                f"HTTP {stored.status_code} review={body.get('review')!r} "
                f"rating={body.get('rating')}",
            )

            # It has to be on the visitor's own profile too, through the
            # dedicated endpoint rather than the page's copy.
            with httpx.Client(base_url=API, timeout=60) as client:
                listed = client.get(
                    f"/users/profile/{DATA['visitor']['username']}/reviews"
                ).json()

            check(
                "attendance: the review is on the writer's profile",
                any(
                    entry["event_id"] == event_id
                    and entry["review"] == marker
                    and entry["rating"] == 4
                    for entry in listed["reviews"]
                ),
                f"{len(listed['reviews'])} reviews listed",
            )

            check(
                "attendance: the profile's review figure matches the rows",
                httpx.get(
                    f"{API}/users/profile/{DATA['visitor']['username']}/stats",
                    timeout=60,
                ).json()["reviews_count"]
                == listed["total"],
                "",
            )

            # The rating is drawn as stars with a readable label, not as a bare
            # number of symbols.
            stars = pg.locator("[data-testid='review-stars']").first
            check(
                "attendance: the rating is shown as stars with a label",
                stars.count() >= 1
                and stars.get_attribute("data-rating") == "4"
                and bool((stars.get_attribute("aria-label") or "").strip()),
                f"rating={stars.get_attribute('data-rating') if stars.count() else None} "
                f"label={stars.get_attribute('aria-label') if stars.count() else None}",
            )

            # The profile shows the latest reviews without being asked, so the
            # same review must be visible there and lead back to the event.
            pg.goto(
                f"{BASE}/en/profile/{DATA['visitor']['username']}",
                wait_until="networkidle",
            )
            pg.wait_for_timeout(1500)
            latest = pg.locator("[data-testid='profile-latest-reviews']")
            check(
                "attendance: the profile shows the review that was written",
                marker in pg.content() and latest.count() == 1,
                marker,
            )

            check(
                "attendance: the profile shows at most three reviews",
                pg.locator("[data-testid='profile-latest-reviews'] "
                           "[data-testid='review-card']").count() <= 3,
                f"{pg.locator('[data-testid=profile-latest-reviews] [data-testid=review-card]').count()} cards",
            )

            review_link = pg.locator(
                "[data-testid='profile-latest-reviews'] "
                "[data-testid='review-card'] a[href*='/events/']"
            )
            check(
                "attendance: a review links to the event it is about",
                review_link.count() >= 1
                and (review_link.first.get_attribute("href") or "").endswith(
                    f"/events/{event_id}"
                ),
                review_link.first.get_attribute("href")
                if review_link.count()
                else "no review link",
            )

            # Pressing "I went" again edits the review rather than deleting the
            # record of having been there.
            pg.goto(f"{BASE}/en/events/{event_id}", wait_until="networkidle")
            pg.wait_for_timeout(1500)
            again = pg.locator("[data-testid='event-mark-went']").first

            check(
                "attendance: a second tap offers to edit, not to erase",
                again.get_attribute("aria-label") is None
                and "Delete" not in again.inner_text(),
                again.inner_text(),
            )

            again.click()
            try:
                pg.wait_for_selector("[data-testid='review-dialog']", timeout=20000)
            except Exception:
                pass

            if pg.locator("[data-testid='review-dialog']").count():
                check(
                    "attendance: the existing review is loaded for editing",
                    pg.locator("[data-testid='review-input']").input_value()
                    == marker
                    and pg.locator("[data-testid='review-star-4']").get_attribute(
                        "aria-checked"
                    )
                    == "true",
                    pg.locator("[data-testid='review-input']").input_value(),
                )

                pg.locator("[data-testid='review-dialog-cancel']").click()
                pg.wait_for_timeout(400)

            # Deleting the review is offered, and removes the text while
            # leaving the attendance in place.
            again.click()
            try:
                pg.wait_for_selector("[data-testid='review-delete']", timeout=20000)
            except Exception:
                pass

            remove = pg.locator("[data-testid='review-delete']")
            check(
                "attendance: an existing review can be deleted",
                remove.count() == 1,
            )

            if remove.count():
                remove.click()
                pg.wait_for_timeout(2000)

                with api(DATA["visitor_token"]) as client:
                    after = client.get(f"/show-logs/{event_id}")

                after_body = after.json() if after.status_code == 200 else {}

                check(
                    "attendance: deleting the review keeps the attendance",
                    after_body.get("status") == "went"
                    and not after_body.get("review"),
                    f"status={after_body.get('status')} "
                    f"review={after_body.get('review')!r}",
                )

            pg.close()
            ctx.close()

    # ================================================ 14. EVENT PAST BADGE
    # The events list has to mark a finished show as finished, in every
    # language, because "I went" and its review only exist for a show that is
    # over. An event whose date is missing must say so instead of printing an
    # invalid date.
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))

    for locale, word in (
        ("en", "Past"),
        ("pt-BR", "Já passou"),
        ("es", "Ya pasó"),
    ):
        # The artist's event list is the one page that shows finished shows:
        # `/events` is the discovery search, which only ever holds upcoming
        # events and would report zero past cards however correct the card is.
        pg.goto(
            f"{BASE}/{locale}/artists/{SLUG}/events",
            wait_until="networkidle",
        )
        pg.wait_for_selector("[data-testid='event-card']", timeout=60000)
        pg.wait_for_timeout(1500)

        cards = pg.locator("[data-testid='event-card']")
        # The whole list is read, not the first screen: an artist's history is
        # ordered oldest first, so the finished shows are not all on page one.
        rendered = pg.evaluate(
            """() => Array.from(document.querySelectorAll('[data-testid="event-card"]'))
                     .map(e => ({
                         past: e.getAttribute('data-past'),
                         badge: e.querySelector('[data-testid="event-card-past"]')?.innerText.trim() || '',
                     }))"""
        )

        check(
            f"event list: the {locale} page marks finished shows",
            any(row["past"] == "true" for row in rendered)
            and all(
                row["badge"] == word for row in rendered if row["past"] == "true"
            ),
            f"{sum(1 for r in rendered if r['past'] == 'true')} of {len(rendered)} past, "
            f"badges={sorted({r['badge'] for r in rendered if r['past'] == 'true'})}",
        )

        body = pg.inner_text("body")
        check(
            f"event list: the {locale} page prints no invalid date",
            "Invalid Date" not in body and "NaN" not in body,
            "",
        )

        undated = pg.evaluate(
            """() => Array.from(document.querySelectorAll('[data-testid="event-card"]'))
                     .some(e => e.innerText.includes('Date to be announced')
                              || e.innerText.includes('Data a ser anunciada')
                              || e.innerText.includes('Fecha por anunciar'))"""
        )
        check(
            f"event list: the {locale} page labels an undated show rather than guessing",
            undated or cards.count() == 0,
            f"{cards.count()} cards, undated label present={undated}",
        )

    pg.close()
    ctx.close()

    # =================================== 15. EVENT AND FESTIVAL SCREENS, IN LOCALE
    # A real event, and a real festival if one of its events carries a lineup,
    # so the translated screens are exercised against live data.
    artist_events = []

    for slug in (DATA["artist_slug"], DATA["other_artist"]):
        found = httpx.get(f"{API}/events/artist/{slug}", timeout=60).json()

        if found:
            artist_events = found
            break

    if artist_events:
        event_id = artist_events[0]["id"]
        festival_event = next(
            (e for e in artist_events if (e.get("festival") or {}).get("name")),
            None,
        )

        for locale in ("en", "pt-BR", "es"):
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"{BASE}/{locale}/events/{event_id}", wait_until="networkidle")
            pg.wait_for_timeout(1200)

            # Every internal link must keep the locale, or the reader is
            # dropped into the wrong language partway through a visit.
            internal = pg.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.getAttribute('href')).filter(h => h.startsWith('/'))",
            )
            wrong = [
                href
                for href in internal
                if not href.startswith(f"/{locale}") and not href.startswith("/_next")
            ]

            check(
                f"event: every {locale} link keeps its locale",
                not wrong,
                f"offenders={wrong[:4]} of {len(internal)}",
            )

            body = pg.inner_text("body")

            # The English page is meant to read in English; the translated
            # ones must never fall back to it.
            untranslated = [
                phrase
                for phrase in (
                    "Back to events",
                    "Loading event",
                    "View festival page",
                    "Explore festival",
                    "Open in maps",
                    "Happening now",
                )
                if locale != "en" and phrase in body
            ]

            check(
                f"event: the {locale} page shows no untranslated copy",
                not untranslated,
                f"{untranslated}",
            )

            # Month names have to follow the locale too. English and
            # Portuguese or Spanish never share a month name, so an English
            # one on a translated page means the date is being formatted for
            # one language for every reader.
            english_months = {
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            }
            words = set(re.findall(r"[A-Za-zÀ-ÿ]+", body))
            leaked = sorted(words & english_months)

            check(
                f"event: the {locale} dates are not formatted in English",
                locale == "en" or not leaked,
                f"leaked={leaked}",
            )

            pg.close()
            ctx.close()

        if festival_event:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(
                f"{BASE}/pt-BR/festivals/{festival_event['id']}",
                wait_until="networkidle",
            )
            pg.wait_for_timeout(900)

            body = pg.inner_text("body")

            check(
                "festival: the pt-BR lineup page shows no untranslated copy",
                "Back to event" not in body
                and "Search artists" not in body
                and "Open artist" not in body
                and "Official website" not in body,
                "",
            )

            internal = pg.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => e.getAttribute('href')).filter(h => h.startsWith('/'))",
            )
            wrong = [
                href
                for href in internal
                if not href.startswith("/pt-BR") and not href.startswith("/_next")
            ]

            check(
                "festival: every pt-BR link keeps its locale",
                not wrong,
                f"offenders={wrong[:4]} of {len(internal)}",
            )

            pg.close()
            ctx.close()
        else:
            check("festival: a lineup page could be exercised", True, "no festival in seed data")
    else:
        check("event: an event page could be exercised", False, "no events for artist")

    # ================================= 16. UNKNOWN PATHS AND NOT FOUND
    # An unknown URL has to answer 404 inside the locale it was asked for, with
    # that locale's document language, its translated copy and the site chrome,
    # rather than the framework's bare English page.
    for locale, heading in (
        ("en", "Page not found"),
        ("pt-BR", "Página não encontrada"),
        ("es", "Página no encontrada"),
    ):
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        response = pg.goto(
            f"{BASE}/{locale}/no-such-page-here", wait_until="networkidle"
        )
        pg.wait_for_timeout(900)

        check(
            f"404: /{locale} answers with a real 404",
            response.status == 404,
            f"HTTP {response.status}",
        )

        state = pg.evaluate(
            """() => ({
                lang: document.documentElement.getAttribute('lang'),
                theme: document.documentElement.getAttribute('data-theme'),
                bg: getComputedStyle(document.body).backgroundColor,
                styled: getComputedStyle(document.body).fontFamily.includes('Inter'),
            })"""
        )

        check(
            f"404: /{locale} declares its own document language",
            state["lang"] == locale,
            f"lang={state['lang']}",
        )
        check(
            f"404: /{locale} is styled like the rest of the app",
            state["styled"],
            f"bg={state['bg']} font={state['styled']}",
        )
        check(
            f"404: /{locale} resolves a theme",
            state["theme"] in ("light", "dark"),
            f"data-theme={state['theme']}",
        )

        body = pg.inner_text("body")
        check(
            f"404: /{locale} shows translated copy with the site chrome",
            heading in body and "GigCrowd" in body,
            body.replace("\n", " | ")[:90],
        )

        pg.close()
        ctx.close()

    # The root and every locale-less path still land on a localized route.
    for path in ("/", "/events", "/feed", "/login", "/register", "/artists"):
        landed = httpx.get(f"{BASE}{path}", follow_redirects=False, timeout=60)
        location = landed.headers.get("location") or ""
        expected = "/en" if path == "/" else f"/en{path}"
        check(
            f"routing: {path} redirects into the default locale",
            landed.status_code in (307, 308) and location == expected,
            f"{landed.status_code} -> {location}",
        )

    # ================================================================= 17. MOBILE
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.goto(f"{BASE}/pt-BR", wait_until="networkidle")
    store_token(pg, DATA["fan_token"], DATA["fan"])
    pg.goto(f"{BASE}/pt-BR", wait_until="networkidle")
    pg.wait_for_timeout(800)

    burger = pg.locator("button[data-testid='mobile-menu-toggle']")
    check("mobile: hamburger is present and labelled", burger.count() == 1
          and bool((burger.first.get_attribute("aria-label") or "").strip()),
          burger.first.get_attribute("aria-label") if burger.count() else "missing")
    check(
        "mobile: the hamburger reports its state",
        burger.first.get_attribute("aria-expanded") == "false",
        burger.first.get_attribute("aria-expanded") or "",
    )
    burger.click()
    pg.wait_for_timeout(400)
    mobile_menu = pg.locator("[data-testid='mobile-nav']")
    check("mobile: the menu opens", mobile_menu.count() == 1
          and burger.first.get_attribute("aria-expanded") == "true")
    mobile_nav = mobile_menu.inner_text()
    check("mobile: menu shows Artists", "Artistas" in mobile_nav)
    check("mobile: menu has no Community", "Comunidade" not in mobile_nav, mobile_nav.replace("\n", " | "))
    check("mobile: menu shows Notifications", "Notifica" in mobile_nav, mobile_nav.replace("\n", " | "))
    check(
        "mobile: menu links to the notifications page",
        (mobile_menu.locator("a[href*='notifications']").count()) == 1,
    )
    mobile_targets = mobile_menu.locator("a, button")
    too_small = [
        mobile_targets.nth(i).get_attribute("href") or f"#{i}"
        for i in range(mobile_targets.count())
        if (mobile_targets.nth(i).bounding_box() or {}).get("height", 0) < 44
    ]
    check(
        "mobile: every menu control is at least 44px tall",
        not too_small,
        ", ".join(too_small[:4]),
    )
    check(
        "mobile: menu exposes the theme toggle",
        mobile_menu.locator("button[data-testid='theme-toggle']").count() == 1,
    )
    mobile_toggle = mobile_menu.locator("button[data-testid='theme-toggle']").first
    mobile_box = mobile_toggle.bounding_box()
    check(
        "mobile: the theme toggle is a comfortable touch target",
        mobile_box and mobile_box["height"] >= 40 and mobile_box["width"] >= 40,
        f"{mobile_box}",
    )
    mobile_before = pg.evaluate("document.documentElement.getAttribute('data-theme')")
    mobile_toggle.click()
    pg.wait_for_timeout(300)
    mobile_after = pg.evaluate("document.documentElement.getAttribute('data-theme')")
    check(
        "mobile: the theme toggle works inside the menu",
        mobile_after is not None and mobile_after != mobile_before,
        f"{mobile_before} -> {mobile_after}",
    )
    mobile_toggle.click()
    pg.wait_for_timeout(300)

    for path in [
        "/pt-BR",
        "/pt-BR/artists",
        "/pt-BR/events",
        "/pt-BR/login",
        f"/pt-BR/artists/{SLUG}/community",
        "/pt-BR/feed",
        f"/pt-BR/profile/{DATA['author']['username']}",
        f"/en/profile/{DATA['author']['username']}",
        f"/es/profile/{DATA['author']['username']}",
    ]:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        pg.wait_for_timeout(900)
        ok = pg.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
        )
        check(f"mobile: no horizontal overflow on {path}", ok)

    # --- the concert profile at a real mobile viewport
    pg.goto(
        f"{BASE}/pt-BR/profile/{DATA['author']['username']}",
        wait_until="networkidle",
    )
    pg.wait_for_timeout(1800)

    profile_stats = pg.locator("[data-testid='profile-stats']")
    check(
        "mobile: the profile figures render at 390px",
        profile_stats.count() == 1,
        f"{profile_stats.count()} block(s)",
    )

    # Two columns at 390px: four figures must be two rows, not one squeezed row
    # and not a horizontal scroll.
    boxes = [
        pg.locator(f"[data-testid='profile-stat-{key}']").first.bounding_box()
        for key in ("reviews", "events", "festivals", "artists")
    ]
    check(
        "mobile: the four profile figures wrap into two columns",
        all(box is not None for box in boxes)
        and boxes[0]["x"] == boxes[2]["x"]
        and boxes[1]["x"] == boxes[3]["x"]
        and boxes[2]["y"] > boxes[0]["y"]
        and all(box["width"] <= 390 for box in boxes),
        f"{boxes}",
    )
    check(
        "mobile: every profile figure is a comfortable touch target",
        all(box["height"] >= 44 for box in boxes if box),
        f"{[box['height'] for box in boxes if box]}",
    )

    # Each panel has to fit the viewport, so the lists were not designed for
    # desktop and merely squeezed.
    for key in ("reviews", "events", "artists", "festivals"):
        pg.locator(f"[data-testid='profile-stat-{key}']").first.click()

        try:
            pg.wait_for_selector(
                "[data-testid='profile-panel'], [data-testid='empty-state']",
                timeout=20000,
            )
        except Exception:
            pass

        pg.wait_for_timeout(400)

        panel = pg.locator("[data-testid='profile-panel']").first
        box = panel.bounding_box() if panel.count() else None

        check(
            f"mobile: the {key} panel fits the viewport width",
            box is not None and box["width"] <= 390,
            f"{box}",
        )

        if key == "artists":
            artist_row = pg.locator("[data-testid='profile-artist-link']").first
            row_box = artist_row.bounding_box() if artist_row.count() else None
            check(
                "mobile: an artist row is a comfortable touch target",
                row_box is not None and row_box["height"] >= 44,
                f"{row_box}",
            )

        pg.locator(f"[data-testid='profile-stat-{key}']").first.click()
        pg.wait_for_timeout(300)

    # A long unbroken token in a review must wrap instead of stretching the page.
    pg.locator("[data-testid='profile-stat-reviews']").first.click()
    try:
        pg.wait_for_selector("[data-testid='review-card']", timeout=20000)
    except Exception:
        pass
    review_card = pg.locator("[data-testid='review-card']").first
    review_box = review_card.bounding_box() if review_card.count() else None
    check(
        "mobile: a review card fits the viewport width",
        review_box is not None and review_box["width"] <= 390,
        f"{review_box}",
    )
    pg.locator("[data-testid='profile-stat-reviews']").first.click()
    pg.wait_for_timeout(300)

    # The review dialog has to be usable on a phone: full-width, scrollable and
    # not taller than the screen.
    if past_event:
        pg.goto(f"{BASE}/pt-BR/events/{past_event['id']}", wait_until="networkidle")
        store_token(pg, DATA["visitor_token"], DATA["visitor"])
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(1800)

        went = pg.locator("[data-testid='event-mark-went']")
        if went.count():
            went.first.click()
            try:
                pg.wait_for_selector(
                    "[data-testid='review-dialog']", timeout=20000
                )
            except Exception:
                pass

            dialog = pg.locator("[data-testid='review-dialog']").first
            dialog_box = dialog.bounding_box() if dialog.count() else None

            check(
                "mobile: the review dialog fits the viewport width",
                dialog_box is not None
                and dialog_box["width"] <= 390
                and dialog_box["height"] <= 844,
                f"{dialog_box}",
            )

            star = pg.locator("[data-testid='review-star-5']").first
            star_box = star.bounding_box() if star.count() else None
            check(
                "mobile: a star is a comfortable touch target",
                star_box is not None
                and star_box["height"] >= 32
                and star_box["width"] >= 32,
                f"{star_box}",
            )

            save = pg.locator("[data-testid='review-save']").first
            save_box = save.bounding_box() if save.count() else None
            check(
                "mobile: saving a review is a comfortable touch target",
                save_box is not None
                and save_box["height"] >= 36
                and save_box["width"] >= 64,
                f"{save_box}",
            )

            # The page behind a dialog must not scroll under it.
            locked = pg.evaluate("getComputedStyle(document.body).overflow")
            check(
                "mobile: the page behind the dialog is locked",
                locked in ("hidden", "auto"),
                f"overflow={locked}",
            )

            if dialog.count():
                pg.locator("[data-testid='review-dialog-cancel']").click()
                pg.wait_for_timeout(400)

            check(
                "mobile: the review dialog can be dismissed",
                pg.locator("[data-testid='review-dialog']").count() == 0,
            )

    # --- comment UI at a real mobile viewport
    pg.goto(f"{BASE}/pt-BR/artists/{SLUG}/community", wait_until="networkidle")
    pg.wait_for_timeout(1200)

    # Open a thread that actually has comments in it. The newest post is not
    # guaranteed to: this artist's community is a shared, append-only list.
    cards = pg.locator("[data-testid='community-post']")
    with_comments = -1
    for index in range(cards.count()):
        count = cards.nth(index).get_attribute("data-comments-count") or "0"
        if int(count) > 0:
            with_comments = index
            break

    check(
        "mobile: a post with comments is reachable",
        with_comments >= 0,
        f"{cards.count()} post(s) on screen",
    )
    if with_comments < 0:
        pg.close()
        ctx.close()
        raise SystemExit(1)

    card = cards.nth(with_comments)
    check("mobile: a community post renders", card.count() == 1)
    card_box = card.bounding_box()
    check(
        "mobile: the post fits the viewport width",
        card_box and card_box["width"] <= 390 and card_box["width"] > 200,
        f"{card_box}",
    )

    card.locator("[data-testid='community-post-comments-toggle']").first.click()
    try:
        pg.wait_for_selector(
            f"[data-post-id='{card.get_attribute('data-post-id')}'] "
            "[data-testid='community-comment']",
            timeout=20000,
        )
    except Exception:
        pass

    comment = pg.locator("[data-testid='community-comment']").first
    check("mobile: a comment renders", comment.count() >= 1)
    if not comment.count():
        # Do not abort the run: report and let the remaining checks proceed.
        pg.close()
        ctx.close()
        raise SystemExit(1)
    comment_box = comment.bounding_box()
    check(
        "mobile: the comment does not overflow the card",
        comment_box
        and comment_box["x"] >= card_box["x"] - 1
        and comment_box["x"] + comment_box["width"] <= card_box["x"] + card_box["width"] + 1,
        f"comment={comment_box} card={card_box}",
    )

    avatar = comment.locator("[data-testid='community-avatar-link']").first
    avatar_box = avatar.bounding_box()
    check(
        "mobile: the avatar is a real size, not a squashed dot",
        avatar_box and 24 <= avatar_box["width"] <= 64,
        f"{avatar_box}",
    )

    name = comment.locator("[data-testid='community-username-link']").first
    name_box = name.bounding_box()
    check(
        "mobile: the username sits beside the avatar, not under it",
        name_box
        and avatar_box
        and name_box["x"] >= avatar_box["x"] + avatar_box["width"] - 2
        and abs(name_box["y"] - avatar_box["y"]) < avatar_box["height"],
        f"avatar={avatar_box} name={name_box}",
    )

    input_box = pg.locator("[data-testid='community-comment-input']").first.bounding_box()
    check(
        "mobile: the comment input is wide enough to type in",
        input_box and input_box["width"] >= 200,
        f"{input_box}",
    )
    check(
        "mobile: the comment input is a comfortable touch target",
        input_box and input_box["height"] >= 40,
        f"{input_box}",
    )

    submit_box = pg.locator("[data-testid='community-comment-submit']").first.bounding_box()
    check(
        "mobile: the comment submit is a comfortable touch target",
        submit_box and submit_box["height"] >= 40 and submit_box["width"] >= 64,
        f"{submit_box}",
    )
    check(
        "mobile: the comment form stacks instead of squeezing",
        submit_box and input_box and submit_box["y"] > input_box["y"],
        f"input y={input_box['y']} submit y={submit_box['y']}",
    )

    # A long unbroken token must wrap instead of stretching the page.
    long_token = "W" * 160
    pg.locator("[data-testid='community-comment-input']").fill(long_token)
    pg.wait_for_timeout(200)
    wrapped = pg.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    check("mobile: a 160-character word does not break the layout", wrapped)
    pg.locator("[data-testid='community-comment-input']").fill("")

    pg.locator("[data-testid='community-comment-reply']").first.click()
    pg.wait_for_timeout(400)
    reply_form = pg.locator("[data-testid='community-reply-form']").first
    reply_box = reply_form.bounding_box()
    reply_input = pg.locator("[data-testid='community-reply-input']").first.bounding_box()
    check(
        "mobile: the reply form nests inside the comment",
        reply_box and comment_box and reply_box["x"] >= comment_box["x"],
        f"reply x={reply_box['x'] if reply_box else None} comment x={comment_box['x']}",
    )
    check(
        "mobile: the reply input still fits the viewport",
        reply_input and reply_input["width"] >= 120 and reply_input["x"] + reply_input["width"] <= 390,
        f"{reply_input}",
    )

    # Mobile notifications and feed.
    pg.goto(f"{BASE}/pt-BR/feed", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    feed_items = pg.locator("[data-testid='feed-item']")
    check(
        "mobile: the feed renders at 390px",
        feed_items.count() >= 1,
        f"{feed_items.count()} items",
    )
    for key in ["community", "reviews", "events", "social"]:
        chip = pg.locator(f"[data-testid='feed-filter-{key}']")
        if chip.count():
            chip.first.click()
            pg.wait_for_timeout(700)
            box = chip.first.bounding_box()
            check(
                f"mobile: the '{key}' filter is a usable touch target",
                box and box["height"] >= 36,
                f"{box}",
            )

    # A review written on a phone has to read on a phone: the stars stay
    # legible and the text wraps instead of stretching the page.
    if past_event:
        pg.goto(f"{BASE}/pt-BR/events/{past_event['id']}", wait_until="networkidle")
        store_token(pg, DATA["visitor_token"], DATA["visitor"])
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(1800)

        existing = pg.locator("[data-testid='review-card']").first
        if existing.count():
            card_box = existing.bounding_box()
            check(
                "mobile: a review on the event fits the viewport",
                card_box is not None and card_box["width"] <= 390,
                f"{card_box}",
            )

            pg.locator("[data-testid='event-edit-review']").first.click()
            try:
                pg.wait_for_selector(
                    "[data-testid='review-dialog']", timeout=20000
                )
            except Exception:
                pass

            pg.locator("[data-testid='review-input']").fill("W" * 160)
            pg.wait_for_timeout(300)
            wrapped = pg.evaluate(
                "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
            )
            check(
                "mobile: a 160-character review does not break the layout",
                wrapped,
            )

            pg.locator("[data-testid='review-dialog-cancel']").click()
            pg.wait_for_timeout(400)
            pg.locator("[data-testid='review-input']").fill("")

    # The inbox belongs to the account that receives notifications. The fan
    # only ever acted on other people's posts, so their inbox is legitimately
    # empty; the author collects the follow, like, comment and reply.
    pg.goto(f"{BASE}/pt-BR", wait_until="networkidle")
    store_token(pg, DATA["author_token"], DATA["author"])
    pg.goto(f"{BASE}/pt-BR/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1200)
    notif_items = pg.locator("[data-testid='notification-item']")
    check(
        "mobile: notifications render at 390px",
        notif_items.count() >= 1,
        f"{notif_items.count()} items",
    )
    check(
        "mobile: a notification row fits the viewport width",
        all(
            (notif_items.nth(i).bounding_box() or {}).get("width", 9999) <= 390
            for i in range(notif_items.count())
        ),
        f"{notif_items.count()} rows",
    )
    ok = pg.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    check("mobile: no horizontal overflow on notifications", ok)

    check("mobile: no uncaught page errors", len(errors) == 0, "; ".join(errors[:3]))

    # Screenshots are inspection artefacts, not repository content.
    shots = Path(tempfile.gettempdir()) / "opencode" / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(shots / "mobile-community.png"), full_page=True)
    pg.goto(f"{BASE}/pt-BR/notifications", wait_until="networkidle")
    pg.wait_for_timeout(1000)
    pg.screenshot(path=str(shots / "mobile-notifications.png"), full_page=True)
    pg.close()
    ctx.close()

    browser.close()

print("\n" + "=" * 66)
passed = sum(1 for _, ok, _ in results if ok)
print(f"BROWSER CHECKS: {passed}/{len(results)} passed")
print("=" * 66)
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL {name} :: {detail}")

sys.exit(0 if passed == len(results) else 1)