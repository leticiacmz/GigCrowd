'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

import RequireAuth from '@/components/auth/RequireAuth';
import LoadingState from '@/components/LoadingState';
import { getUser } from '@/app/lib/auth';

/**
 * Own profile area.
 *
 * This is the signed-in user's private entry point. It resolves to the
 * existing public profile page for their own username, so there is a single
 * profile implementation. Signed-out visitors are redirected to the
 * localized home page by the guard.
 */
function OwnProfileContent() {
  const params = useParams();
  const router = useRouter();

  const locale = (params?.locale as string) || 'en';

  useEffect(() => {
    const user = getUser();

    if (!user?.username) {
      router.replace(`/${locale}`);
      return;
    }

    router.replace(`/${locale}/profile/${user.username}`);
  }, [locale, router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <LoadingState message="" />
    </div>
  );
}

export default function OwnProfilePage() {
  const params = useParams();
  const locale = (params?.locale as string) || 'en';

  return (
    <RequireAuth locale={locale}>
      <OwnProfileContent />
    </RequireAuth>
  );
}