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
   * there is no global Community destination to link to.
   */
  const publicLinks = [
    { href: `/${locale}/artists`, label: nav.artists ?? 'Artists' },
    { href: `/${locale}/events`, label: nav.events ?? 'Events' },
  ];

  const navLinks = isLoggedIn
    ? [
        { href: `/${locale}/feed`, label: nav.feed ?? 'Feed' },
        ...publicLinks,
      ]
    : publicLinks;

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
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? 'page' : undefined}
              className={`transition-colors duration-200 ${
                pathname === link.href ? activeLinkClass : inactiveLinkClass
              }`}
            >
              {link.label}
            </Link>
          ))}
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
                aria-current={pathname === link.href ? 'page' : undefined}
                className={`flex min-h-[44px] items-center rounded-lg px-3 py-2 transition-colors hover:bg-card-hover ${
                  pathname === link.href
                    ? 'bg-card-hover font-semibold text-foreground'
                    : 'text-muted'
                }`}
              >
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
