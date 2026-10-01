'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

import { isAuthenticated } from '@/app/lib/auth';

interface RequireAuthProps {
  locale: string;
  children: React.ReactNode;
}

/**
 * Client-side route guard for pages that require a session
 * (Feed, Community, own profile).
 *
 * The session lives in localStorage, so the guard has to run on the client.
 * A signed-out visitor is sent to the localized home page. Private content
 * is not rendered until the session state is known, which avoids flashing
 * personalized data to a signed-out visitor.
 */
export default function RequireAuth({
  locale,
  children,
}: RequireAuthProps) {
  const router = useRouter();
  const [authorized, setAuthorized] = useState<boolean | null>(null);

  useEffect(() => {
    function evaluate() {
      if (isAuthenticated()) {
        setAuthorized(true);
        return;
      }

      setAuthorized(false);
      router.replace(`/${locale}`);
    }

    evaluate();

    // Re-evaluate when the session changes, e.g. logging out while the
    // user is still on a private page.
    window.addEventListener('auth-changed', evaluate);

    return () => {
      window.removeEventListener('auth-changed', evaluate);
    };
  }, [locale, router]);

  if (authorized !== true) {
    return null;
  }

  return <>{children}</>;
}