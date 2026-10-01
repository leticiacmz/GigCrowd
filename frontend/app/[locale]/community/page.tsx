'use client';

import { useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';

/**
 * The global community page has been retired.
 * Community is now artist-specific and accessed through artist profiles.
 * This page redirects to the artists page.
 */
export default function CommunityPage() {
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

  useEffect(() => {
    router.replace(`/${locale}/artists`);
  }, [router, locale]);

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-gray-400">Redirecting to artists...</p>
    </div>
  );
}
