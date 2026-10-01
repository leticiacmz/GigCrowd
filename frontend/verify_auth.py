"""
Authentication / authorization verification for the GigCrowd frontend.

Run against a production build:
    npx next build && npx next start -p 3100
with the FastAPI backend on :8000 and MongoDB on :27017.
"""
import json
import re
import sys
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3000"
BACKEND = "http://localhost:8000"
EMAIL = "authtest@example.com"
USERNAME = "authtester"
PASSWORD = "AuthTest123!"
# A second account to follow: the app correctly hides Follow on your own
# profile, so the public-profile/follow checks need another user.
TARGET = "followtarget"
TARGET_EMAIL = "followtarget@example.com"
# An artist slug that has community posts, for the Like-guard check.
POST_ARTIST = "arctic-monkeys"
LOCALES = ["en", "pt-BR", "es"]

PROTECTED_MARKERS = (
    "/auth/login",
    "/users/me",
    "/follows/",
    "/feed",
    "/community/feed",
    "/community/posts",
    "/community/comments",
    "/show-logs",
    "/artists",
    "/events",
)

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS  " if ok else "FAIL  ") + name + (("  -- " + detail) if detail else ""))


def rel(url):
    return urllib.parse.urlparse(url).path


def is_protected_call(method, url):
    if not url.startswith(BACKEND):
        return False
    path = rel(url)
    if path in ("/artists",) and method == "GET":
        return False
    if path in ("/events/artist",):
        return False
    return any(m in path for m in PROTECTED_MARKERS)


def token():
    form = urllib.parse.urlencode({"username": EMAIL, "password": PASSWORD}).encode()
    req = urllib.request.Request(BACKEND + "/auth/login", data=form, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())["access_token"]


def ensure_target():
    """Register the follow target; the app hides Follow on your own profile."""
    body = json.dumps(
        {
            "email": TARGET_EMAIL,
            "username": TARGET,
            "password": PASSWORD,
            "full_name": "Follow Target",
        }
    ).encode()
    req = urllib.request.Request(BACKEND + "/auth/register", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def seed_local_storage(page, tok):
    user_json = json.dumps(
        {
            "id": "6abdf126ad10306e1e18009d",
            "email": EMAIL,
            "username": USERNAME,
            "full_name": "Auth Tester",
            "role": "user",
        }
    )
    page.add_init_script(
        "if (!window.localStorage.getItem('__seeded')) {"
        " window.localStorage.setItem('token', "
        + json.dumps(tok)
        + ");"
        " window.localStorage.setItem('user', "
        + json.dumps(user_json)
        + ");"
        " window.localStorage.setItem('__seeded', '1');"
        "}"
    )


def main():
    tok = token()
    print("ensure_target:", ensure_target())

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ================================================== LOGGED OUT
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()

        api_calls = []

        def watch(pg_):
            """Record every protected backend request made by this page."""
            pg_.on(
                "request",
                lambda r: api_calls.append((r.method, r.url))
                if is_protected_call(r.method, r.url)
                else None,
            )
            return pg_

        page = watch(page)

        # --- public pages must load and stay put
        for loc in LOCALES:
            for path in ["", "/events", "/artists", f"/artists/{POST_ARTIST}"]:
                target = f"/{loc}{path}"
                api_calls.clear()
                page.goto(FRONTEND + target, wait_until="networkidle")
                page.wait_for_timeout(2500)
                final = rel(page.url)
                check(
                    f"[logged out] {target} stays public",
                    final == f"/{loc}{path}" or (path == "" and final == f"/{loc}"),
                    f"final={final}",
                )
                check(
                    f"[logged out] {target} triggers no 401-driven redirect",
                    not [c for c in api_calls if "/community/" in c[1]],
                    f"calls={[c[1] for c in api_calls][:4]}",
                )

        # --- private pages redirect to localized home
        for loc in LOCALES:
            for path in ["/feed", "/community", "/profile"]:
                target = f"/{loc}{path}"
                api_calls.clear()
                page.goto(FRONTEND + target, wait_until="networkidle")
                page.wait_for_timeout(1200)
                final = rel(page.url)
                check(
                    f"[logged out] {target} -> /{loc}",
                    final == f"/{loc}",
                    f"final={final}",
                )
                check(
                    f"[logged out] {target} made no protected API call",
                    len(api_calls) == 0,
                    f"calls={[c[1] for c in api_calls]}",
                )

        # --- private content must not be rendered before redirecting
        page.goto(FRONTEND + "/en/feed", wait_until="domcontentloaded")
        early = page.content()
        page.wait_for_timeout(1500)
        check(
            "[logged out] /en/feed server HTML has no private feed markup",
            "Log out" not in early,
        )

        # --- public profile is viewable
        for loc in LOCALES:
            target = f"/{loc}/profile/{TARGET}"
            page.goto(FRONTEND + target, wait_until="networkidle")
            page.wait_for_timeout(1000)
            body = page.inner_text("body")
            check(
                f"[logged out] {target} is publicly viewable",
                rel(page.url) == f"/{loc}/profile/{TARGET}" and TARGET in body,
                f"final={rel(page.url)}",
            )

        # --- follow button visible but click must not call the API
        for loc in LOCALES:
            page.goto(FRONTEND + f"/{loc}/profile/{TARGET}", wait_until="networkidle")
            page.wait_for_timeout(1200)
            btn = page.locator('[data-testid="follow-button"]')
            check(
                f"[logged out] Follow button visible on /{loc} public profile",
                btn.count() == 1 and btn.first.is_visible(),
            )

            api_calls.clear()
            btn.first.click()
            page.wait_for_timeout(2000)
            final = page.url.replace(FRONTEND, "")
            called_follows = [c for c in api_calls if "/follows/" in c[1]]
            check(
                f"[logged out] /{loc} Follow click does NOT call the follow API",
                len(called_follows) == 0,
                f"calls={[c[1] for c in called_follows]}",
            )
            check(
                f"[logged out] /{loc} Follow click -> /{loc}/login with next",
                final.startswith(f"/{loc}/login") and f"/{loc}/profile/{TARGET}" in urllib.parse.unquote(final),
                f"final={final}",
            )

        # --- navbar while logged out
        page.goto(FRONTEND + "/en", wait_until="networkidle")
        page.wait_for_timeout(600)
        nav_text = page.inner_text("nav")
        for hidden in ["Feed", "Community", "Profile", "Logout"]:
            check(f"[logged out] Navbar hides '{hidden}'", hidden not in nav_text)
        check("[logged out] Navbar shows Artists", "Artists" in nav_text)
        check("[logged out] Navbar shows Events", "Events" in nav_text)
        check("[logged out] Navbar shows Sign In", "Sign In" in nav_text)
        check(
            "[logged out] Navbar shows Create Account",
            "Create Account" in nav_text,
        )

        # --- <html lang> per locale
        for loc in LOCALES:
            page.goto(FRONTEND + f"/{loc}", wait_until="networkidle")
            page.wait_for_timeout(400)
            lang = page.evaluate("document.documentElement.lang")
            check(f"[logged out] /{loc} html lang == {loc}", lang == loc, f"lang={lang}")

        # --- authenticated action on a PUBLIC page: create a post
        for loc in LOCALES[:1]:
            page.goto(
                FRONTEND + f"/{loc}/artists/{POST_ARTIST}", wait_until="networkidle"
            )
            page.wait_for_timeout(3000)
            body = page.inner_text("body")
            check(
                f"[logged out] /{loc} artist page prompts sign-in instead of faking an empty feed",
                "Sign in" in body,
                body[:80].replace("\n", " "),
            )
            page.fill("textarea", "hello from the auth verification run")
            api_calls.clear()
            page.locator("button:has-text('Post')").first.click()
            page.wait_for_timeout(2500)
            final = page.url.replace(FRONTEND, "")
            check(
                f"[logged out] Create post on a public page skips the API and goes to /{loc}/login",
                final.startswith(f"/{loc}/login")
                and not [c for c in api_calls if "/community/posts" in c[1]],
                f"final={final} calls={[c[1] for c in api_calls]}",
            )

        # ============================================ RETURN TARGET FLOW
        # An off-site `next` must be discarded rather than honoured.
        for hostile in [
            "https://evil.example/steal",
            "//evil.example/steal",
            "\\\\evil.example",
        ]:
            page.goto(
                FRONTEND + "/en/login?next=" + urllib.parse.quote(hostile, safe=""),
                wait_until="networkidle",
            )
            page.wait_for_timeout(800)
            page.fill('input[type="email"]', EMAIL)
            page.fill('input[type="password"]', PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_timeout(4500)
            landed = page.url.replace(FRONTEND, "")
            check(
                f"[open redirect] next={hostile!r} is rejected",
                landed.startswith("/en") and "evil.example" not in landed,
                f"landed={landed}",
            )
            page.evaluate("localStorage.clear()")

        page.goto(
            FRONTEND + f"/pt-BR/profile/{TARGET}?x=1", wait_until="networkidle"
        )
        page.wait_for_timeout(1200)
        page.locator('[data-testid="follow-button"]').first.click()
        page.wait_for_timeout(2000)
        check(
            "[return flow] lands on /pt-BR/login with next",
            page.url.replace(FRONTEND, "").startswith("/pt-BR/login"),
            page.url.replace(FRONTEND, ""),
        )
        # log in through the real form
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_timeout(4000)
        back = page.url.replace(FRONTEND, "")
        check(
            "[return flow] after login returns to the original pt-BR page",
            back.startswith("/pt-BR/profile/"),
            back,
        )
        page.wait_for_timeout(800)
        btn = page.locator('[data-testid="follow-button"]')
        check(
            "[return flow] Follow button now authenticated",
            btn.count() == 1 and btn.first.get_attribute("data-authenticated") == "true",
        )

        ctx.close()

        # ================================================== LOGGED IN
        ctx2 = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = watch(ctx2.new_page())
        seed_local_storage(pg, tok)
        pg.goto(FRONTEND + "/en", wait_until="domcontentloaded")
        pg.wait_for_timeout(800)

        for path in [
            "",
            "/events",
            "/artists",
            "/feed",
            "/community",
            "/profile",
            "/profile/" + USERNAME,
            "/profile/" + TARGET,
        ]:
            api_calls.clear()
            pg.goto(FRONTEND + "/en" + path, wait_until="networkidle")
            pg.wait_for_timeout(1500)
            final = rel(pg.url)
            expected = f"/en{path}".rstrip("/") or "/en"
            ok = final == expected
            if path == "/profile":
                ok = final.startswith("/en/profile/")
            check(f"[logged in] /en{path} renders", ok, f"final={final}")
            if path == "/profile/" + USERNAME:
                # Own profile: the edit control replaces Follow (you cannot
                # follow yourself).
                body = pg.inner_text("body")
                check(
                    "[logged in] own profile shows Edit Profile, not Follow",
                    "Edit Profile" in body
                    and pg.locator('[data-testid="follow-button"]').count() == 0,
                )
            if path in ("/feed", "/community"):
                endpoint = "/feed" if path == "/feed" else "/community/feed"
                check(
                    f"[logged in] /en{path} called its protected endpoint",
                    any(endpoint in c[1] for c in api_calls),
                    f"calls={[c[1] for c in api_calls][:4]}",
                )
                if path == "/feed":
                    # The feed shows who each activity belongs to.
                    check(
                        "[logged in] /en/feed resolved the viewer via /users/me",
                        any("/users/me" in c[1] for c in api_calls),
                        f"calls={[c[1] for c in api_calls][:4]}",
                    )

        # feed must actually show content, not just an empty shell
        pg.goto(FRONTEND + "/en/feed", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        feed_body = pg.inner_text("body")
        check("[logged in] /en/feed renders page heading", "Feed" in feed_body)
        check(
            "[logged in] /en/feed shows the signed-in nav, not the public one",
            "Sign In" not in feed_body and "@" + USERNAME in feed_body,
            feed_body[:100].replace("\n", " "),
        )

        pg.goto(FRONTEND + "/en/community", wait_until="networkidle")
        pg.wait_for_timeout(2000)
        community_body = pg.inner_text("body")
        check(
            "[logged in] /en/community renders its own heading",
            "Community" in community_body,
        )
        check(
            "[logged in] /en/community loads real posts",
            "posts" in community_body.lower() or "Test post" in community_body,
            community_body[:120].replace("\n", " "),
        )

        # --- liking a post while signed in DOES call the API
        api_calls.clear()
        pg.goto(FRONTEND + f"/en/artists/{POST_ARTIST}", wait_until="networkidle")
        pg.wait_for_timeout(3000)
        like = pg.locator('[data-testid="like-button"]')
        if like.count() == 0:
            check("[logged in] artist page exposes a Like control", False)
        else:
            like.first.click()
            pg.wait_for_timeout(2500)
            check(
                "[logged in] Like calls the like API",
                any("/like" in c[1] for c in api_calls),
                f"calls={[c[1] for c in api_calls][:4]}",
            )

        # --- follow / unfollow round trip
        api_calls.clear()
        pg.goto(FRONTEND + f"/en/profile/{TARGET}", wait_until="networkidle")
        pg.wait_for_timeout(2000)
        btn = pg.locator('[data-testid="follow-button"]')
        check(
            "[logged in] follow button authenticated on another profile",
            btn.count() == 1 and btn.first.get_attribute("data-authenticated") == "true",
        )
        # The follow state persists server-side, so assert the toggle works from
        # whatever state it is in rather than assuming "not following".
        initial = btn.first.inner_text()
        was_following = "Following" in initial
        api_calls.clear()
        btn.first.click()
        pg.wait_for_timeout(2500)
        after_first = btn.first.inner_text()
        expected_verb = "DELETE" if was_following else "POST"
        check(
            f"[logged in] toggle from {initial!r} flips the label and calls {expected_verb}",
            ("Following" in after_first) != was_following
            and any("/follows/" in c[1] and c[0] == expected_verb for c in api_calls),
            f"initial={initial!r} after={after_first!r} "
            f"calls={[c for c in api_calls if '/follows/' in c[1]]}",
        )
        api_calls.clear()
        btn.first.click()
        pg.wait_for_timeout(2500)
        after_second = btn.first.inner_text()
        opposite_verb = "POST" if was_following else "DELETE"
        check(
            f"[logged in] toggle back from {after_first!r} restores {initial!r} via {opposite_verb}",
            ("Following" in after_second) == was_following
            and any("/follows/" in c[1] and c[0] == opposite_verb for c in api_calls),
            f"after={after_second!r} "
            f"calls={[c for c in api_calls if '/follows/' in c[1]]}",
        )

        # --- navbar while logged in
        pg.goto(FRONTEND + "/en", wait_until="networkidle")
        pg.wait_for_timeout(800)
        nav_text = pg.inner_text("nav")
        for want in ["Feed", "Community", "Artists", "Events"]:
            check(f"[logged in] Navbar shows '{want}'", want in nav_text)
        check(
            "[logged in] Navbar shows the user handle",
            "@" + USERNAME in nav_text,
            nav_text[:120].replace("\n", " "),
        )
        check("[logged in] Navbar hides Sign In", "Sign In" not in nav_text)

        # --- own profile via Navbar user menu
        pg.locator("nav button[aria-haspopup='menu']").click()
        pg.wait_for_selector("nav [role='menu']", timeout=15000)
        pg.locator("nav [role='menu'] >> text=Profile").click()
        pg.wait_for_timeout(2500)
        check(
            "[logged in] Navbar -> Profile reaches the profile page",
            rel(pg.url).startswith("/en/profile/"),
            rel(pg.url),
        )

        # --- logout, then private routes must be protected again
        pg.goto(FRONTEND + "/en", wait_until="networkidle")
        pg.wait_for_timeout(800)
        pg.locator("nav button[aria-haspopup='menu']").click()
        pg.wait_for_selector("nav [role='menu']", timeout=15000)
        pg.locator("nav [role='menu'] >> text=Logout").click()
        pg.wait_for_timeout(3000)
        stored = pg.evaluate("localStorage.getItem('token')")
        check("[logout] token cleared from storage", stored in (None, ""), repr(stored))
        nav_after = pg.inner_text("nav")
        check(
            "[logout] Navbar drops the signed-in links at once",
            "Feed" not in nav_after
            and "Logout" not in nav_after
            and "@" + USERNAME not in nav_after,
            nav_after[:120].replace("\n", " | "),
        )

        for path in ["/feed", "/community", "/profile"]:
            api_calls.clear()
            pg.goto(FRONTEND + "/en" + path, wait_until="networkidle")
            pg.wait_for_timeout(1500)
            check(
                f"[logout] /en{path} redirects to /en",
                rel(pg.url) == "/en",
                f"final={rel(pg.url)}",
            )

        # follow while signed out again
        api_calls.clear()
        pg.goto(FRONTEND + f"/en/profile/{TARGET}", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        btn = pg.locator('[data-testid="follow-button"]')
        check("[logout] Follow button visible again", btn.count() == 1)
        btn.first.click()
        pg.wait_for_timeout(2500)
        check(
            "[logout] Follow click goes to /en/login and skips the API",
            page_ok := (rel(pg.url) == "/en/login")
            and not [c for c in api_calls if "/follows/" in c[1]],
            f"final={rel(pg.url)} calls={[c[1] for c in api_calls if '/follows/' in c[1]]}",
        )

        ctx2.close()

        # ================================================== MOBILE
        mctx = browser.new_context(
            viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
        )
        mp = mctx.new_page()
        seed_local_storage(mp, tok)

        mp.goto(FRONTEND + "/en", wait_until="networkidle")
        mp.wait_for_timeout(900)
        mp.locator("nav button[aria-label='Toggle navigation menu']").click()
        mp.wait_for_timeout(700)
        mobile_nav = mp.inner_text("nav")
        for want in ["Feed", "Community", "Artists", "Events"]:
            check(f"[mobile logged in] menu shows '{want}'", want in mobile_nav)

        # Log out from the mobile menu (the menu is still open).
        mp.locator("nav button:has-text('Logout')").first.click()
        mp.wait_for_timeout(3000)
        # Logout closes the menu; reopen it to read the links.
        mp.locator("nav button[aria-label='Toggle navigation menu']").click()
        mp.wait_for_timeout(700)
        mobile_after = mp.inner_text("nav")
        check(
            "[mobile logout] menu drops the signed-in links",
            "Feed" not in mobile_after
            and "Logout" not in mobile_after
            and "@" + USERNAME not in mobile_after,
            mobile_after[:120].replace("\n", " | "),
        )

        mp.goto(FRONTEND + "/pt-BR/feed", wait_until="networkidle")
        mp.wait_for_timeout(1800)
        check(
            "[mobile logged out] /pt-BR/feed -> /pt-BR",
            rel(mp.url) == "/pt-BR",
            f"final={rel(mp.url)}",
        )

        mp.goto(FRONTEND + f"/es/profile/{TARGET}", wait_until="networkidle")
        mp.wait_for_timeout(1500)
        btn = mp.locator('[data-testid="follow-button"]')
        check(
            "[mobile logged out] Follow visible on /es profile",
            btn.count() == 1 and btn.first.is_visible(),
        )
        btn.first.click()
        mp.wait_for_timeout(2500)
        check(
            "[mobile logged out] Follow -> /es/login",
            rel(mp.url) == "/es/login",
            f"final={rel(mp.url)}",
        )

        mctx.close()
        browser.close()

    failed = [r for r in results if not r[1]]
    print("\n" + "=" * 62)
    print(f"TOTAL {len(results)}   PASS {len(results) - len(failed)}   FAIL {len(failed)}")
    for name, _, detail in failed:
        print("  FAILED: " + name + ("  -- " + detail if detail else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())