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

export default function RegisterPage() {
  const t = useTranslations('auth');
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

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    setLoading(true);
    setError('');

    try {
      const response = await authAPI.register(formData);

      saveAuth(response);

      // Return the user to the page they were trying to reach,
      // preserving the active locale.
      const next = getNextParam();

      router.replace(next ?? `/${locale}/feed`);
    } catch (err: any) {
      setError(err.response?.data?.detail ?? t('registerFailed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-md p-8">
        <div className="mb-8 text-center">
          <h1 className="mb-2 bg-gradient-to-r from-accent to-secondary bg-clip-text text-[36px] font-bold text-transparent">
            GigCrowd
          </h1>

          <p className="text-[18px] text-gray-400">{t('createAccount')}</p>
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
            <div role="alert" className="text-sm text-red-500">
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

        <p className="mt-6 text-center text-sm text-gray-400">
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