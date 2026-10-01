"""Real-browser verification of theme, i18n, navigation, auth states and mobile."""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://localhost:3100"
results = []


def check(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()

    # ============================================================ THEME
    ctx = browser.new_context(color_scheme="dark")
    pg = ctx.new_page()
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    check(
        "system=dark -> dark",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == "dark",
    )
    pg.close()
    ctx.close()

    ctx = browser.new_context(color_scheme="light")
    pg = ctx.new_page()
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    check(
        "system=light -> light",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == "light",
    )

    # explicit toggle wins over system, and both themes really differ
    pg.locator("button[data-testid='theme-toggle']").first.click()
    pg.wait_for_timeout(250)
    toggled = pg.evaluate("document.documentElement.getAttribute('data-theme')")
    check("toggle overrides system", toggled == "dark", f"->{toggled}")
    check(
        "toggle persisted",
        pg.evaluate("localStorage.getItem('gigcrowd-theme')") == toggled,
    )

    pg.reload(wait_until="networkidle")
    check(
        "theme survives reload",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == toggled,
    )
    pg.goto(f"{BASE}/en/artists", wait_until="networkidle")
    check(
        "theme survives navigation",
        pg.evaluate("document.documentElement.getAttribute('data-theme')") == toggled,
    )

    bg_dark = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    fg_dark = pg.evaluate("getComputedStyle(document.body).color")
    pg.evaluate("document.documentElement.setAttribute('data-theme','light')")
    pg.wait_for_timeout(200)
    bg_light = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    fg_light = pg.evaluate("getComputedStyle(document.body).color")
    check(
        "light/dark backgrounds differ",
        bg_light != bg_dark,
        f"light={bg_light} dark={bg_dark}",
    )
    check(
        "light/dark text colors differ",
        fg_light != fg_dark,
        f"light={fg_light} dark={fg_dark}",
    )
    pg.close()
    ctx.close()

    # ============================================================ I18N (public pages)
    ctx = browser.new_context()
    pg = ctx.new_page()
    errors = []
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
        body = pg.content()
        check(f"i18n {path} renders '{expected[:28]}'", expected in body)

    # no English leakage on localized pages
    leaks = {
        "/pt-BR": ["Your Feed", "Welcome Back", "Create your account", "Every concert"],
        "/es": ["Your Feed", "Welcome Back", "Create your account", "Every concert"],
    }
    for path, bad in leaks.items():
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        body = pg.content()
        found = [b for b in bad if b in body]
        check(f"no English leak on {path}", not found, ", ".join(found))

    # html lang
    for path, lang in [("/pt-BR", "pt-BR"), ("/es", "es")]:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        check(
            f"html lang={lang} on {path}",
            pg.evaluate("document.documentElement.getAttribute('lang')") == lang,
        )

    # ============================================================ NAV (logged out)
    pg.goto(f"{BASE}/en", wait_until="networkidle")
    nav = pg.locator("nav").first.inner_text()
    check("logged-out nav shows Artists", "Artists" in nav, nav.replace("\n", " | "))
    check("logged-out nav shows Events", "Events" in nav)
    check("logged-out nav hides Feed", "Feed" not in nav)
    check("logged-out nav hides Community", "Community" not in nav)

    pg.goto(f"{BASE}/en/login", wait_until="networkidle")
    login_nav = pg.locator("nav").first.inner_text()
    check("login page hides 'Sign In' CTA", "Sign In" not in login_nav)
    check("login page still shows Artists", "Artists" in login_nav)

    hrefs = pg.eval_on_selector_all("nav a", "e => e.map(x => x.getAttribute('href'))")
    check(
        "nav hrefs locale-prefixed",
        all((h or "").startswith("/en") for h in hrefs),
        str(hrefs),
    )

    # ============================================================ AUTH GUARD (feed/community)
    for path in ["/en/feed", "/en/community"]:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        pg.wait_for_timeout(700)
        check(
            f"logged-out {path} redirects to login",
            "/login" in pg.url,
            pg.url.replace(BASE, ""),
        )

    check("no uncaught page errors", len(errors) == 0, "; ".join(errors[:2]))
    pg.close()
    ctx.close()

    # ============================================================ MOBILE
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    pg = ctx.new_page()
    pg.goto(f"{BASE}/pt-BR", wait_until="networkidle")

    burger = pg.locator("button[aria-label='Toggle navigation menu']")
    check("mobile hamburger present", burger.count() > 0)
    burger.click()
    pg.wait_for_timeout(300)
    check(
        "mobile menu shows Artists",
        "Artistas" in pg.locator("nav").first.inner_text(),
    )
    check(
        "mobile menu exposes theme toggle",
        pg.locator("nav button[data-testid='theme-toggle-mobile']").count() > 0,
    )

    for path in ["/pt-BR", "/pt-BR/artists", "/pt-BR/events", "/pt-BR/login"]:
        pg.goto(f"{BASE}{path}", wait_until="networkidle")
        ok = pg.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
        )
        check(f"no horizontal overflow {path}", ok)
    pg.close()
    ctx.close()
    browser.close()

print("\n" + "=" * 62)
passed = sum(1 for _, ok, _ in results if ok)
print(f"BROWSER CHECKS: {passed}/{len(results)} passed")
print("=" * 62)
for name, ok, detail in results:
    if not ok:
        print(f"  FAIL {name} :: {detail}")

sys.exit(0 if passed == len(results) else 1)
