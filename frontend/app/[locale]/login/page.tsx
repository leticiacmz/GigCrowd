'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { authAPI } from '../../lib/api';
import { saveAuth, getNextParam } from '../../lib/auth';
import Input from '../../../components/ui/Input';
import Button from '../../../components/ui/Button';
import Card from '../../../components/ui/Card';

export default function LoginPage() {
  const t = useTranslations('auth');
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    setLoading(true);
    setError('');

    try {
      const response = await authAPI.login(email, password);

      saveAuth(response);

      // Return the user to the page they were trying to reach,
      // preserving the active locale.
      const next = getNextParam();

      router.replace(next ?? `/${locale}/feed`);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? t('signInFailed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md p-8">
        <h1 className="mb-6 text-center text-[28px] font-bold text-foreground">
          {t('welcomeBack')}
        </h1>

        {error && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-red-500 bg-red-500/20 p-3 text-sm text-red-400"
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="email"
            name="email"
            autoComplete="email"
            label={t('email')}
            placeholder={t('emailPlaceholder')}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <Input
            type="password"
            name="password"
            autoComplete="current-password"
            label={t('password')}
            placeholder={t('passwordPlaceholder')}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />

          <Button
            type="submit"
            disabled={loading}
            className="w-full"
            size="lg"
          >
            {loading ? t('signingIn') : t('signIn')}
          </Button>
        </form>

        <div className="mt-6 text-center text-sm text-gray-400">
          {t('dontHaveAccount')}{' '}
          <Link
            href={`/${locale}/register`}
            className="text-accent transition-colors hover:text-accent/80"
          >
            {t('register')}
          </Link>
        </div>
      </Card>
    </div>
  );
}