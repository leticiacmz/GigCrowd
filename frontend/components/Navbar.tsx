'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

interface CurrentUser {
  username: string;
}

export default function Navbar() {
  const pathname = usePathname();

  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const userStr = localStorage.getItem('user');

    if (userStr) {
      try {
        setCurrentUser(JSON.parse(userStr));
      } catch {
        localStorage.removeItem('user');
        setCurrentUser(null);
      }
    } else {
      setCurrentUser(null);
    }

    setIsLoaded(true);
  }, []);

  const isLoggedIn = !!currentUser;

  const isLoginPage = pathname === '/login';
  const isRegisterPage = pathname === '/register';

  const logoHref = isLoggedIn ? '/feed' : '/';

  const navLinks = isLoggedIn
    ? [
        { href: '/feed', label: 'Feed' },
        { href: '/artists', label: 'Artists' },
        { href: '/events', label: 'Events' },
      ]
    : [
        { href: '/artists', label: 'Artists' },
        { href: '/events', label: 'Events' },
      ];

  function handleLogout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user');

    window.location.href = '/login';
  }

  return (
    <nav className="sticky top-0 z-50 border-b border-border bg-background">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Logo */}
        <Link href={logoHref}>
          <span className="bg-gradient-to-r from-accent to-secondary bg-clip-text text-2xl font-bold text-transparent">
            GigCrowd
          </span>
        </Link>

        {/* Desktop Navigation */}
        <div className="hidden items-center gap-8 md:flex">
          {navLinks.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`transition-colors ${
                pathname === link.href
                  ? 'font-medium text-accent'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Desktop Actions */}
        <div className="hidden items-center gap-6 md:flex">
          {isLoaded &&
            (isLoggedIn ? (
              <>
                <Link
                  href={`/profile/${currentUser.username}`}
                  className="font-medium text-gray-300 transition-colors hover:text-white"
                >
                  @{currentUser.username}
                </Link>

                <button
                  onClick={handleLogout}
                  className="text-gray-400 transition-colors hover:text-white"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                {!isLoginPage && (
                  <Link
                    href="/login"
                    className="text-gray-400 transition-colors hover:text-white"
                  >
                    Sign In
                  </Link>
                )}

                {!isRegisterPage && (
                  <Link
                    href="/register"
                    className="rounded-md border border-accent px-3 py-1.5 text-sm font-medium text-accent transition-all hover:bg-accent hover:text-white"
                  >
                    Create Account
                  </Link>
                )}
              </>
            ))}
        </div>

        {/* Mobile Button */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="p-2 text-gray-400 hover:text-white md:hidden"
        >
          ☰
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="border-t border-border bg-card-bg md:hidden">
          <div className="flex flex-col gap-4 p-4">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`transition-colors ${
                  pathname === link.href
                    ? 'font-medium text-accent'
                    : 'text-gray-300'
                }`}
              >
                {link.label}
              </Link>
            ))}

            {isLoaded &&
              (isLoggedIn ? (
                <>
                  <Link
                    href={`/profile/${currentUser.username}`}
                    onClick={() => setMobileMenuOpen(false)}
                    className="font-medium text-gray-300"
                  >
                    @{currentUser.username}
                  </Link>

                  <button
                    onClick={() => {
                      setMobileMenuOpen(false);
                      handleLogout();
                    }}
                    className="text-left text-gray-300"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  {!isLoginPage && (
                    <Link
                      href="/login"
                      onClick={() => setMobileMenuOpen(false)}
                      className="text-gray-300"
                    >
                      Sign In
                    </Link>
                  )}

                  {!isRegisterPage && (
                    <Link
                      href="/register"
                      onClick={() => setMobileMenuOpen(false)}
                      className="font-medium text-accent"
                    >
                      Create Account
                    </Link>
                  )}
                </>
              ))}
          </div>
        </div>
      )}
    </nav>
  );
}