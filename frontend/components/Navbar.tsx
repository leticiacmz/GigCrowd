'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import Button from '@/components/ui/Button';
import ThemeToggle from '@/components/ui/ThemeToggle';
import NotificationBell from '@/components/NotificationBell';
import {
  logout,
  isAuthenticated,
  getUser,
  clearStaleAuth,
} from '@/app/lib/auth';
import { locales, defaultLocale } from '@/app/i18n';
import { publicNavItems } from '@/app/lib/navigation';

interface AuthUser {
  id: string;
  email: string;
  username: string;
  full_name?: string;
  avatar_url?: string;
  bio?: string;
  location?: string;
  role: string;
}

interface NavbarMessages {
  nav?: Record<string, string>;
  common?: Record<string, string>;
}

/**
 * The magnifier, drawn twice: as the submit button inside the header's search
 * field, and beside the Events entry in the mobile menu.
 *
 * Decorative on purpose: both callers carry their own accessible names - the
 * field's placeholder labels the input and its button - so the drawing is
 * hidden from assistive technology and never the only thing naming anything.
 */
function SearchIcon({ className = 'h-5 w-5' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      aria-hidden="true"
      className={className}
    >
      <circle cx="11" cy="11" r="7" />
      <path d="M20 20l-3.5-3.5" />
    </svg>
  );
}

/**
 * The header's search field: the desktop bar's Events destination, as a box
 * a question can be typed into rather than an icon that only ever says
 * "events page".
 *
 * Enter (or the magnifier) goes to `/{locale}/events` with the term in the
 * address - `?q=...`, encoded - and the events page reads that parameter on
 * arrival and runs the lookup. The address, not any component state, is what
 * carries the term, so the search can be reloaded, shared and read the same
 * by whoever opens it next.
 */
function HeaderSearch({
  locale,
  placeholder,
}: {
  locale: string;
  placeholder: string;
}) {
  const router = useRouter();
  const [term, setTerm] = useState('');

  function submit(event: React.FormEvent) {
    event.preventDefault();

    const query = term.trim();
    const target = query
      ? `/${locale}/events?q=${encodeURIComponent(query)}`
      : `/${locale}/events`;

    /*
     * Already on the events page: a client-side push would leave the page
     * mounted, and the page reads `?q=` on arrival - so the press navigates
     * for real and the term is read by exactly the effect that owns it. From
     * anywhere else the push is enough, since the page mounts either way.
     */
    if (window.location.pathname === `/${locale}/events`) {
      window.location.assign(target);
      return;
    }

    router.push(target);
  }

  return (
    <form
      onSubmit={submit}
      role="search"
      data-testid="nav-search"
      className="
        flex
        items-center
        gap-1
        rounded-lg
        border
        border-border
        bg-card-bg
        px-2
        transition-colors
        focus-within:border-accent
      "
    >
      <input
        type="search"
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        data-testid="nav-search-input"
        className="
          h-9
          w-40
          bg-transparent
          text-sm
          text-foreground
          outline-none
          placeholder:text-muted-subtle
          md:w-56
        "
      />

      <button
        type="submit"
        aria-label={placeholder}
        data-testid="nav-search-submit"
        className="
          flex
          h-9
          w-9
          shrink-0
          items-center
          justify-center
          text-muted
          transition-colors
          hover:text-foreground
        "
      >
        <SearchIcon className="h-4 w-4" />
      </button>
    </form>
  );
}

function resolveLocale(pathname: string): string {
  const segment = pathname.split('/')[1];
  return locales.includes(segment as (typeof locales)[number])
    ? segment
    : defaultLocale;
}

export default function Navbar({ messages }: { messages?: NavbarMessages }) {
  const pathname = usePathname() || '';
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  const locale = resolveLocale(pathname);
  const pathnameWithoutLocale =
    pathname.replace(new RegExp(`^/${locale}`), '') || '/';

  const loadCurrentUser = useCallback(() => {
    if (isAuthenticated()) {
      const user = getUser();
      if (user) {
        setCurrentUser(user);
        return;
      }
      clearStaleAuth();
    }
    setCurrentUser(null);
  }, []);

  useEffect(() => {
    loadCurrentUser();
    window.addEventListener('auth-changed', loadCurrentUser);
    return () => window.removeEventListener('auth-changed', loadCurrentUser);
  }, [loadCurrentUser]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(event.target as Node)
      ) {
        setUserMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close transient menus whenever navigation happens.
  useEffect(() => {
    setMobileMenuOpen(false);
    setUserMenuOpen(false);
  }, [pathname]);

  const isLoggedIn = !!currentUser;
  const isLoginPage = pathnameWithoutLocale === '/login';
  const isRegisterPage = pathnameWithoutLocale === '/register';

  const nav = messages?.nav ?? {};

  const logoHref = isLoggedIn ? `/${locale}/feed` : `/${locale}`;

  /*
   * Community is deliberately absent: it only exists inside an artist, so
   * there is no global Community destination to link to. The general
   * Artists tab is absent too - artists are opened one at a time from a
   * lineup, an event or a search - and the one list both the desktop bar
   * and the mobile menu read lives in `lib/navigation`.
   *
   * A Feed tab is absent for the same reason: the logo is the timeline,
   * for a signed-in reader, and it is one press away from anywhere.
   */
  const navLinks = publicNavItems(locale, nav);

  function handleLogout() {
    logout();
    setCurrentUser(null);
    setUserMenuOpen(false);
    setMobileMenuOpen(false);
    router.replace(`/${locale}/login`);
  }

  function handleNavigation() {
    setMobileMenuOpen(false);
    setUserMenuOpen(false);
  }

  const activeLinkClass =
    'font-semibold bg-gradient-to-r from-gradient-text-from to-gradient-text-to bg-clip-text text-transparent';
  const inactiveLinkClass = 'text-muted hover:text-foreground';

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6 lg:px-8">
        <Link href={logoHref} onClick={handleNavigation} className="shrink-0">
          <span className="bg-gradient-to-r from-gradient-text-from to-gradient-text-to bg-clip-text text-2xl font-bold text-transparent">
            GigCrowd
          </span>
        </Link>

        <div className="hidden flex-1 items-center justify-center gap-7 md:flex">
          {/*
            The search destination is drawn as the search field itself on the
            bar - a box a question can be typed into says "find events" better
            than an icon that only ever means the events page - while every
            other destination stays a link with its localised label. The
            destination's own `nav.events` label keeps its job in the mobile
            menu, where the list reads as words.
          */}
          {navLinks.map((link) =>
            link.icon === 'search' ? (
              <HeaderSearch
                key={link.href}
                locale={locale}
                placeholder={nav.searchPlaceholder ?? 'Search events'}
              />
            ) : (
              <Link
                key={link.href}
                href={link.href}
                aria-current={pathname === link.href ? 'page' : undefined}
                className={`inline-flex min-h-[44px] items-center gap-2 rounded-lg px-2 transition-colors duration-200 ${
                  pathname === link.href ? activeLinkClass : inactiveLinkClass
                }`}
              >
                {link.label}
              </Link>
            ),
          )}
        </div>

        <div className="ml-auto flex items-center gap-2 sm:gap-3">
          <ThemeToggle className="hidden md:inline-flex" />

          {isLoggedIn && currentUser ? (
            <>
              <NotificationBell locale={locale} />

              <div ref={userMenuRef} className="relative hidden md:block">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex h-11 items-center gap-2 rounded-lg px-2 text-sm text-muted transition-colors hover:bg-card-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
                  aria-haspopup="menu"
                  aria-expanded={userMenuOpen}
                >
                  {/*
                    The same photo the profile saved - the stored session
                    copy, refreshed by the `auth-changed` event the save
                    fires. Decorative: the button already names who it is.
                  */}
                  {currentUser.avatar_url && (
                    <img
                      src={currentUser.avatar_url}
                      alt=""
                      aria-hidden="true"
                      className="h-7 w-7 shrink-0 rounded-full object-cover"
                      data-testid="navbar-avatar"
                    />
                  )}
                  @{currentUser.username}
                  <span aria-hidden="true" className="text-xs">
                    ▾
                  </span>
                </button>

                {userMenuOpen && (
                  <div
                    role="menu"
                    className="absolute right-0 mt-2 w-52 rounded-xl border border-border bg-card-bg p-2 shadow-xl"
                  >
                    <Link
                      href={`/${locale}/profile/${currentUser.username}`}
                      onClick={handleNavigation}
                      className="block rounded-lg px-3 py-2.5 text-sm text-muted hover:bg-card-hover hover:text-foreground"
                    >
                      {nav.profile ?? 'Profile'}
                    </Link>

                    <div className="my-2 border-t border-border" />

                    <button
                      onClick={handleLogout}
                      className="w-full rounded-lg px-3 py-2.5 text-left text-sm text-muted hover:bg-card-hover hover:text-foreground"
                    >
                      {nav.logout ?? 'Logout'}
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="hidden items-center gap-3 md:flex">
              {!isLoginPage && (
                <Link href={`/${locale}/login`}>
                  <Button variant="outlineGradient" size="sm">
                    {nav.login ?? 'Sign In'}
                  </Button>
                </Link>
              )}

              {!isRegisterPage && (
                <Link href={`/${locale}/register`}>
                  <Button variant="neon" size="sm">
                    {nav.register ?? 'Create Account'}
                  </Button>
                </Link>
              )}
            </div>
          )}

          <button
            onClick={() => setMobileMenuOpen((open) => !open)}
            aria-label={nav.menu ?? 'Menu'}
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav"
            data-testid="mobile-menu-toggle"
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-foreground transition-colors hover:bg-card-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent md:hidden"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.8}
              strokeLinecap="round"
              aria-hidden="true"
              className="h-6 w-6"
            >
              {mobileMenuOpen ? (
                <path d="M6 6l12 12M18 6L6 18" />
              ) : (
                <path d="M4 7h16M4 12h16M4 17h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {mobileMenuOpen && (
        <div
          id="mobile-nav"
          data-testid="mobile-nav"
          className="border-t border-border bg-card-bg md:hidden"
        >
          <div className="mx-auto flex max-w-7xl flex-col gap-1 px-4 py-3">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={handleNavigation}
                data-testid={link.icon ? 'nav-events' : undefined}
                aria-current={pathname === link.href ? 'page' : undefined}
                className={`flex min-h-[44px] items-center gap-2 rounded-lg px-3 py-2 transition-colors hover:bg-card-hover ${
                  pathname === link.href
                    ? 'bg-card-hover font-semibold text-foreground'
                    : 'text-muted'
                }`}
              >
                {/*
                  In the menu the label is written out beside the icon:
                  here there is room for both, and a list of destinations
                  reads faster as words than as a row of glyphs.
                */}
                {link.icon === 'search' && (
                  <SearchIcon className="h-5 w-5 shrink-0" />
                )}
                {link.label}
              </Link>
            ))}

            <div className="my-2 border-t border-border" />

            {isLoggedIn && currentUser ? (
              <>
                <Link
                  href={`/${locale}/notifications`}
                  onClick={handleNavigation}
                  className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-muted hover:bg-card-hover"
                >
                  {nav.notifications ?? 'Notifications'}
                </Link>

                <Link
                  href={`/${locale}/profile/${currentUser.username}`}
                  onClick={handleNavigation}
                  className="flex min-h-[44px] items-center gap-2 rounded-lg px-3 py-2 text-muted hover:bg-card-hover"
                >
                  {currentUser.avatar_url && (
                    <img
                      src={currentUser.avatar_url}
                      alt=""
                      aria-hidden="true"
                      className="h-6 w-6 shrink-0 rounded-full object-cover"
                    />
                  )}
                  @{currentUser.username}
                </Link>

                <button
                  onClick={handleLogout}
                  className="flex min-h-[44px] items-center rounded-lg px-3 py-2 text-left text-muted hover:bg-card-hover"
                >
                  {nav.logout ?? 'Logout'}
                </button>
              </>
            ) : (
              <div className="flex flex-col gap-3 py-2">
                {!isLoginPage && (
                  <Link href={`/${locale}/login`} onClick={handleNavigation}>
                    <Button variant="outlineGradient" size="sm" className="w-full">
                      {nav.login ?? 'Sign In'}
                    </Button>
                  </Link>
                )}

                {!isRegisterPage && (
                  <Link href={`/${locale}/register`} onClick={handleNavigation}>
                    <Button variant="neon" size="sm" className="w-full">
                      {nav.register ?? 'Create Account'}
                    </Button>
                  </Link>
                )}
              </div>
            )}

            <div className="mt-3 flex items-center justify-between gap-3 border-t border-border pt-3">
              <span className="text-sm text-muted">
                {messages?.common?.themeToggle ?? 'Theme'}
              </span>
              <ThemeToggle />
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}
