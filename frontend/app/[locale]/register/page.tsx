'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

import { authAPI } from '../../lib/api';
import { apiErrorMessage } from '../../lib/apiError';
import {
  saveAuth,
  getNextParam,
  isAuthenticated,
} from '../../lib/auth';
import Input from '../../../components/ui/Input';
import Button from '../../../components/ui/Button';
import Card from '../../../components/ui/Card';
import LoadingState from '../../../components/LoadingState';

export default function RegisterPage() {
  const t = useTranslations('auth');
  const tCommon = useTranslations('common');
  const params = useParams();
  const router = useRouter();
  const locale = (params?.locale as string) || 'en';

  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    full_name: ''
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionChecked, setSessionChecked] = useState(false);

  /*
    Registration is for people who are not signed in.

    The session lives in localStorage, so the check runs on the client.
    Until it has run - and while a signed-in visitor is being sent on - the
    form is not rendered: a form that flashes before it is taken away reads
    as a glitch, and a registration form under an existing session is a
    contradiction. The redirect honors the same `next` target login does, so
    a person sent here on the way to a page still arrives there.
    `auth-changed` re-runs the check, so signing out in another tab returns
    the form instead of stranding this one.
  */
  useEffect(() => {
    function evaluate() {
      if (isAuthenticated()) {
        router.replace(getNextParam() ?? `/${locale}/feed`);
        return;
      }

      setSessionChecked(true);
    }

    evaluate();

    window.addEventListener('auth-changed', evaluate);

    return () => window.removeEventListener('auth-changed', evaluate);
  }, [locale, router]);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    setLoading(true);
    setError('');

    try {
      const response = await authAPI.register(formData);

      /*
        The registration answers with the same session login returns. If a
        deployment ever answers without one, the failure is said here rather
        than stored as a session that is not there - a silently broken
        session would surface as a bounce, not as a message.
      */
      if (!response?.access_token) {
        throw new Error('registration did not return a session');
      }

      saveAuth(response);

      // Return the user to the page they were trying to reach,
      // preserving the active locale.
      const next = getNextParam();

      router.replace(next ?? `/${locale}/feed`);
    } catch (err) {
      setError(apiErrorMessage(err, t('registerFailed')));
    } finally {
      setLoading(false);
    }
  }

  /*
    No frame of this page shows the form to a session that already exists.
  */
  if (!sessionChecked) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background px-4">
        <LoadingState message={tCommon('loading')} />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-md p-8">
        <div className="mb-8 text-center">
          <h1 className="mb-2 bg-gradient-to-r from-accent to-secondary bg-clip-text text-[36px] font-bold text-transparent">
            GigCrowd
          </h1>

          <p className="text-[18px] text-muted">{t('createAccount')}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            label={t('email')}
            value={formData.email}
            onChange={handleChange}
            required
          />

          <Input
            id="username"
            name="username"
            type="text"
            autoComplete="username"
            label={t('username')}
            value={formData.username}
            onChange={handleChange}
            required
            minLength={3}
          />

          <Input
            id="full_name"
            name="full_name"
            type="text"
            autoComplete="name"
            label={t('fullName')}
            value={formData.full_name}
            onChange={handleChange}
          />

          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="new-password"
            label={t('password')}
            value={formData.password}
            onChange={handleChange}
            required
            minLength={8}
          />

          {error && (
            <div
              role="alert"
              className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
            >
              {error}
            </div>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full"
            size="lg"
          >
            {loading ? t('creatingAccount') : t('registerButton')}
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-muted">
          {t('alreadyHaveAccount')}{' '}
          <Link
            href={`/${locale}/login`}
            className="text-accent transition-colors hover:text-accent/80"
          >
            {t('loginLink')}
          </Link>
        </p>
      </Card>
    </div>
  );
}