'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

interface CurrentUser {
  username: string;
}

export default function Navbar() {
  const pathname = usePathname();

  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [isLoaded, setIsLoaded] = useState(false);

  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const userStr = localStorage.getItem('user');

    if (userStr) {
      try {
        setCurrentUser(JSON.parse(userStr));
      } catch {
        localStorage.removeItem('user');
        setCurrentUser(null);
      }
    }

    setIsLoaded(true);
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

    document.addEventListener(
      'mousedown',
      handleClickOutside
    );

    return () => {
      document.removeEventListener(
        'mousedown',
        handleClickOutside
      );
    };
  }, []);


  const isLoggedIn = !!currentUser;

  const isLoginPage = pathname === '/login';
  const isRegisterPage = pathname === '/register';

  const logoHref = isLoggedIn ? '/feed' : '/';


  const navLinks = isLoggedIn
    ? [
        {
          href: '/feed',
          label: 'Feed',
        },
        {
          href: '/artists',
          label: 'Artists',
        },
        {
          href: '/events',
          label: 'Events',
        },
      ]
    : [
        {
          href: '/artists',
          label: 'Artists',
        },
        {
          href: '/events',
          label: 'Events',
        },
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
              className={
                pathname === link.href
                  ? 'font-medium text-accent'
                  : 'text-gray-400 transition-colors hover:text-white'
              }
            >
              {link.label}
            </Link>

          ))}

        </div>




        {/* Desktop Actions */}

        <div className="hidden items-center md:flex">

          {isLoaded && (

            isLoggedIn ? (

              <div
                ref={userMenuRef}
                className="relative"
              >

                <button
                  onClick={() =>
                    setUserMenuOpen(!userMenuOpen)
                  }
                  className="flex items-center gap-1 text-gray-300 transition-colors hover:text-white"
                >

                  @{currentUser.username}

                  <span className="text-xs">
                    ▾
                  </span>

                </button>



                {userMenuOpen && (

                  <div className="absolute right-0 mt-3 w-48 rounded-xl border border-border bg-card-bg p-2 shadow-xl">


                    <Link
                      href={`/profile/${currentUser.username}`}
                      onClick={() =>
                        setUserMenuOpen(false)
                      }
                      className="block rounded-lg px-3 py-2 text-sm text-gray-300 transition hover:bg-card-hover hover:text-white"
                    >
                      My Profile
                    </Link>



                    <Link
                      href="/settings"
                      onClick={() =>
                        setUserMenuOpen(false)
                      }
                      className="block rounded-lg px-3 py-2 text-sm text-gray-300 transition hover:bg-card-hover hover:text-white"
                    >
                      Settings
                    </Link>



                    <div className="my-2 border-t border-border" />



                    <button
                      onClick={handleLogout}
                      className="block w-full rounded-lg px-3 py-2 text-left text-sm text-gray-300 transition hover:bg-card-hover hover:text-white"
                    >
                      Logout
                    </button>


                  </div>

                )}

              </div>


            ) : (

              <div className="flex items-center gap-3">


                {!isLoginPage && (

                  <Link
                    href="/login"
                    className="
                      relative
                      rounded-md
                      p-[1px]
                      bg-gradient-to-r
                      from-accent
                      to-secondary
                      transition
                      hover:opacity-90
                    "
                  >
                    <span
                      className="
                        block
                        rounded-md
                        bg-background
                        px-4
                        py-2
                        text-sm
                        font-medium
                        text-white
                      "
                    >
                      Sign In
                    </span>
                  </Link>

                )}



                {!isRegisterPage && (

                  <Link
                    href="/register"
                    className="
                      rounded-md
                      bg-gradient-to-r
                      from-accent
                      to-secondary
                      px-4
                      py-2
                      text-sm
                      font-medium
                      text-white
                      transition
                      hover:opacity-90
                    "
                  >
                    Create Account
                  </Link>

                )}


              </div>

            )

          )}

        </div>




        {/* Mobile Menu Button */}

        <button
          onClick={() =>
            setMobileMenuOpen(!mobileMenuOpen)
          }
          className="text-gray-400 hover:text-white md:hidden"
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
                onClick={() =>
                  setMobileMenuOpen(false)
                }
                className="text-gray-300"
              >
                {link.label}
              </Link>

            ))}



            {isLoggedIn ? (

              <>

                <Link
                  href={`/profile/${currentUser.username}`}
                  className="text-gray-300"
                >
                  @{currentUser.username}
                </Link>


                <Link
                  href="/settings"
                  className="text-gray-300"
                >
                  Settings
                </Link>


                <button
                  onClick={handleLogout}
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
                    className="
                      relative
                      rounded-md
                      p-[1px]
                      bg-gradient-to-r
                      from-accent
                      to-secondary
                      transition
                      hover:opacity-90
                    "
                  >
                    <span
                      className="
                        block
                        rounded-md
                        bg-background
                        px-4
                        py-2
                        text-sm
                        font-medium
                        text-white
                      "
                    >
                      Sign In
                    </span>
                  </Link>

                )}



                {!isRegisterPage && (

                  <Link
                    href="/register"
                    className="
                      rounded-md
                      bg-gradient-to-r
                      from-accent
                      to-secondary
                      px-4
                      py-2
                      text-sm
                      font-medium
                      text-white
                      transition
                      hover:opacity-90
                    "
                  >
                    Create Account
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