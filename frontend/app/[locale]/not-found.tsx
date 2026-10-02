'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';

import Button from '@/components/ui/Button';

/**
 * Shown for a path the app has no route for.
 *
 * It lives inside the locale segment so it renders within that locale's
 * document, chrome and messages rather than falling back to the framework's
 * bare English page.
 */
export default function NotFound() {
  const params = useParams();
  const locale = (params?.locale as string) || 'en';
  const t = useTranslations('notFound');

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="text-center max-w-md">
        <p className="text-5xl font-bold text-accent mb-4">404</p>

        <h1 className="text-2xl font-bold mb-2">{t('title')}</h1>

        <p className="text-muted mb-6">{t('description')}</p>

        <Link href={`/${locale}`}>
          <Button variant="outline">{t('backHome')}</Button>
        </Link>
      </div>
    </div>
  );
}
