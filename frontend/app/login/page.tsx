'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { authAPI } from '../lib/api';
import { saveAuth } from '../lib/auth';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] =
    useState('');

  const [password, setPassword] =
    useState('');

  const [loading, setLoading] =
    useState(false);

  const [error, setError] =
    useState('');

  async function handleSubmit(
    e: React.FormEvent
  ) {
    e.preventDefault();

    setLoading(true);
    setError('');

    try {
      const response =
        await authAPI.login(
          email,
          password
        );

      saveAuth(response);

      window.location.href = '/feed';
    } catch (err: any) {
      setError(
        err.response?.data?.detail ??
          'Unable to login.'
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">

      <Card className="w-full max-w-md p-8">

        <h1 className="mb-6 text-center text-[28px] font-bold text-foreground">
          Welcome Back
        </h1>

        {error && (
          <div className="mb-4 rounded-lg bg-red-500/20 border border-red-500 p-3 text-red-300">
            {error}
          </div>
        )}

        <form
          onSubmit={handleSubmit}
          className="space-y-4"
        >

          <Input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) =>
              setEmail(e.target.value)
            }
          />

          <Input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) =>
              setPassword(e.target.value)
            }
          />

          <Button
            type="submit"
            disabled={loading}
            className="w-full"
            size="lg"
          >
            {loading
              ? 'Signing In...'
              : 'Sign In'}
          </Button>

        </form>

        <div className="mt-6 text-center text-gray-400">

          Don't have an account?{' '}

          <Link
            href="/register"
            className="text-accent hover:text-accent/80 transition-colors"
          >
            Register
          </Link>

        </div>

      </Card>

    </div>
  );
}