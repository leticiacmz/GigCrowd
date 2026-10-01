'use client';

import Button from '@/components/ui/Button';
import { logout, isAuthenticated, getUser, clearStaleAuth } from '@/app/lib/auth';
import { useTheme } from '@/components/use-theme';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

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

export default function Navbar({ messages }: { messages?: any }) {
  const nav = messages?.nav || { 
    feed: 'Feed', 
    artists: 'Artists', 
    events: 'Events', 
    profile: 'My Profile', 
    settings: 'Settings', 
    login: 'Sign In', 
    register: 'Create Account', 
    logout: 'Logout' 
  };
  const common = messages?.common || { 
    light: 'Light', 
    dark: 'Dark' 
  };

  const pathname = usePathname();
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const userMenuRef = useRef<HTMLDivElement>(null);

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

  const isLoggedIn = !!currentUser;
  const isLoginPage = pathname === '/login';
  const isRegisterPage = pathname === '/register';
  const isHomePage = pathname === '/';

  const logoHref = isLoggedIn ? '/feed' : '/';

  const navLinks = isLoggedIn
    ? [
        { href: '/feed', label: nav.feed ?? 'Feed' },
        { href: '/artists', label: nav.artists ?? 'Artists' },
        { href: '/events', label: nav.events ?? 'Events' },
      ]
      : isHomePage
        ? []
        : [
            { href: '/artists', label: nav.artists ?? 'Artists' },
            { href: '/events', label: nav.events ?? 'Events' },
          ];

  function handleLogout() {
    logout();
    setCurrentUser(null);
    setUserMenuOpen(false);
    router.replace('/login');
  }

  function handleNavigation() {
    setMobileMenuOpen(false);
    setUserMenuOpen(false);
  }

  const baseLinkClass = 'transition-all duration-300';
  const activeLinkClass = 'font-medium bg-gradient-to-r from-accent to-secondary bg-clip-text text-transparent';
  const inactiveLinkClass = 'text-gray-400 hover:text-white';

  return (
    <nav
      className="sticky top-0 z-50 border-b border-border bg-background"
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link href={logoHref} onClick={handleNavigation}>
          <span
            className="bg-gradient-to-r from-accent to-secondary bg-clip-text text-2xl font-bold text-transparent"
          >
            GigCrowd
          </span>
        </Link>

        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={
                pathname === link.href
                  ? `${baseLinkClass} ${activeLinkClass}`
                  : `${baseLinkClass} ${inactiveLinkClass}`
              }
            >
              {link.label}
            </Link>
          ))}
        </div>

        <div className="hidden items-center md:flex">
          {isLoggedIn && currentUser ? (
            <>
              <div ref={userMenuRef} className="relative">
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  className="flex items-center gap-1 text-gray-300 hover:text-white"
                >
                  @{currentUser.username}
                  <span className="text-xs">▾</span>
                </button>

                {userMenuOpen && (
                  <div
                    className="absolute right-0 mt-3 w-48 rounded-xl border border-border bg-card-bg p-2 shadow-xl"
                  >
                    <Link
                      href={`/profile/${currentUser.username}`}
                      onClick={handleNavigation}
                      className="block rounded-lg px-3 py-2 text-sm text-gray-300 hover:bg-card-hover hover:text-white"
                    >
                      {nav.profile ?? 'My Profile'}
                    </Link>
                    <Link
                      href="/settings"
                      onClick={handleNavigation}
                      className="block rounded-lg px-3 py-2 text-sm text-gray-300 hover:bg-card-hover hover:text-white"
                    >
                      {nav.settings ?? 'Settings'}
                    </Link>
                    <div className="my-2 border-t border-border" />
                    <button
                      onClick={handleLogout}
                      className="w-full rounded-lg px-3 py-2 text-left text-sm text-gray-300 hover:bg-card-hover hover:text-white"
                    >
                      {nav.logout ?? 'Logout'}
                    </button>
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              {!isLoginPage && (
                <Link href="/login">
                  <Button variant="outlineGradient" size="sm">{nav.login ?? 'Sign In'}</Button>
                </Link>
              )}

              {!isRegisterPage && (
                <Link href="/register">
                  <Button variant="neon" size="sm">{nav.register ?? 'Create Account'}</Button>
                </Link>
              )}
            </>
          )}
        </div>

        <Button
          variant="outline"
          size="sm"
          onClick={toggleTheme}
          className="hidden md:block mx-2"
        >
          {theme === 'dark' ? (common.light ?? 'Light') : (common.dark ?? 'Dark')}
        </Button>

        <div />

        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="text-gray-400 hover:text-white md:hidden"
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
                className="text-gray-300"
              >
                {link.label}
              </Link>
            ))}

            {isLoggedIn && currentUser ? (
              <>
                <Link
                  href={`/profile/${currentUser.username}`}
                  className="text-gray-300"
                >
                  @{currentUser.username}
                </Link>
                <Link href="/settings" className="text-gray-300">
                  {nav.settings ?? 'Settings'}
                </Link>
                <button onClick={handleLogout} className="text-left text-gray-300">
                  {nav.logout ?? 'Logout'}
                </button>
              </>
            ) : (
              <>
                {!isLoginPage && (
                  <Link href="/login">
                    <Button variant="outlineGradient" size="sm">{nav.login ?? 'Sign In'}</Button>
                  </Link>
                )}

                {!isRegisterPage && (
                  <Link href="/register">
                    <Button variant="neon" size="sm">{nav.register ?? 'Create Account'}</Button>
                  </Link>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </nav>
  );
}
