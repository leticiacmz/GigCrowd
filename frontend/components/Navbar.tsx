'use client';

import Button from '@/components/ui/Button';
import { logout, isAuthenticated, getUser, clearStaleAuth } from '@/app/lib/auth';
import { useTheme } from '@/components/use-theme';
import { locales, defaultLocale } from '@/app/i18n';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { useEffect, useRef, useState } from 'react';

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
  const { theme, toggleTheme } = useTheme();
  const userMenuRef = useRef<HTMLDivElement>(null);

  const locale = resolveLocale(pathname);
  const pathnameWithoutLocale = pathname.replace(new RegExp(`^/${locale}`), '') || '/';

  function loadCurrentUser() {
    if (isAuthenticated()) {
      const user = getUser();
      if (user) {
        setCurrentUser(user);
      } else {
        setCurrentUser(null);
        clearStaleAuth();
      }
    } else {
      setCurrentUser(null);
    }
  }

  useEffect(() => {
    loadCurrentUser();
    window.addEventListener('auth-changed', loadCurrentUser);
    return () => window.removeEventListener('auth-changed', loadCurrentUser);
  }, []);

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
  const common = messages?.common ?? {};

  const logoHref = isLoggedIn ? `/${locale}/feed` : `/${locale}`;

  const navLinks = isLoggedIn
    ? [
        { href: `/${locale}/feed`, label: nav.feed ?? 'Feed' },
        { href: `/${locale}/artists`, label: nav.artists ?? 'Artists' },
        { href: `/${locale}/events`, label: nav.events ?? 'Events' },
      ]
    : [
        { href: `/${locale}/artists`, label: nav.artists ?? 'Artists' },
        { href: `/${locale}/events`, label: nav.events ?? 'Events' },
      ];

  const authLinks = (
    <>
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
    </>
  );

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

  const baseLinkClass = 'transition-all duration-300';
  const activeLinkClass =
    'font-medium bg-gradient-to-r from-accent to-secondary bg-clip-text text-transparent';
  const inactiveLinkClass = 'text-gray-400 hover:text-foreground';

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link href={logoHref} onClick={handleNavigation} className="shrink-0">
          <span className="bg-gradient-to-r from-accent to-secondary bg-clip-text text-2xl font-bold text-transparent">
            GigCrowd
          </span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={pathname === link.href ? 'page' : undefined}
              className={`${baseLinkClass} ${
                pathname === link.href ? activeLinkClass : inactiveLinkClass
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center gap-3 md:flex">
          {isLoggedIn && currentUser ? (
            <div ref={userMenuRef} className="relative">
              <button
                onClick={() => setUserMenuOpen(!userMenuOpen)}
                className="flex items-center gap-1 text-gray-300 hover:text-foreground"
                aria-haspopup="menu"
                aria-expanded={userMenuOpen}
              >
                @{currentUser.username}
                <span className="text-xs">▾</span>
              </button>

              {userMenuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 mt-3 w-48 rounded-xl border border-border bg-card-bg p-2 shadow-xl"
                >
                  <Link
                    href={`/${locale}/profile/${currentUser.username}`}
                    onClick={handleNavigation}
                    className="block rounded-lg px-3 py-2 text-sm text-gray-300 hover:bg-card-hover hover:text-foreground"
                  >
                    {nav.profile ?? 'My Profile'}
                  </Link>

                  <div className="my-2 border-t border-border" />

                  <button
                    onClick={handleLogout}
                    className="w-full rounded-lg px-3 py-2 text-left text-sm text-gray-300 hover:bg-card-hover hover:text-foreground"
                  >
                    {nav.logout ?? 'Logout'}
                  </button>
                </div>
              )}
            </div>
          ) : (
            authLinks
          )}
        </div>

        <button
          onClick={toggleTheme}
          data-testid="theme-toggle"
          aria-label={common.theme ?? 'Theme'}
          title={theme === 'dark' ? (common.light ?? 'Light') : (common.dark ?? 'Dark')}
          className="hidden shrink-0 rounded-lg border border-border px-3 py-1.5 text-sm text-gray-300 hover:bg-card-hover md:block"
        >
          {theme === 'dark' ? (common.light ?? 'Light') : (common.dark ?? 'Dark')}
        </button>

        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          aria-label="Toggle navigation menu"
          aria-expanded={mobileMenuOpen}
          className="shrink-0 rounded-lg px-2 py-1 text-gray-300 hover:bg-card-hover md:hidden"
        >
          ☰
        </button>
      </div>

      {mobileMenuOpen && (
        <div className="border-t border-border bg-card-bg md:hidden">
          <div className="flex flex-col gap-4 p-4">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={handleNavigation}
                aria-current={pathname === link.href ? 'page' : undefined}
                className={pathname === link.href ? 'text-foreground' : 'text-gray-300'}
              >
                {link.label}
              </Link>
            ))}

            <div className="border-t border-border pt-4">
              {isLoggedIn && currentUser ? (
                <div className="flex flex-col gap-4">
                  <Link
                    href={`/${locale}/profile/${currentUser.username}`}
                    onClick={handleNavigation}
                    className="text-gray-300"
                  >
                    @{currentUser.username}
                  </Link>

                  <button
                    onClick={handleLogout}
                    className="text-left text-gray-300"
                  >
                    {nav.logout ?? 'Logout'}
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">{authLinks}</div>
              )}

              <button
                onClick={toggleTheme}
                data-testid="theme-toggle-mobile"
                aria-label={common.theme ?? 'Theme'}
                className="mt-4 w-full rounded-lg border border-border px-3 py-2 text-sm text-gray-300 hover:bg-card-hover"
              >
                {theme === 'dark'
                  ? (common.light ?? 'Light')
                  : (common.dark ?? 'Dark')}
              </button>
            </div>
          </div>
        </div>
      )}
    </nav>
  );
}