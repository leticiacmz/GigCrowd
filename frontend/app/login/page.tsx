'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

import { authAPI } from '../lib/api';
import { saveAuth } from '../lib/auth';

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

      router.push('/feed');
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
    <div className="min-h-screen flex items-center justify-center bg-gray-950">

      <div className="w-full max-w-md rounded-xl bg-gray-900 p-8 shadow-xl">

        <h1 className="mb-6 text-center text-3xl font-bold text-white">
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

          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) =>
              setEmail(e.target.value)
            }
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-white"
          />

          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) =>
              setPassword(e.target.value)
            }
            className="w-full rounded-lg border border-gray-700 bg-gray-800 px-4 py-3 text-white"
          />

          <button
            disabled={loading}
            className="w-full rounded-lg bg-purple-600 py-3 text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {loading
              ? 'Signing In...'
              : 'Sign In'}
          </button>

        </form>

        <div className="mt-6 text-center text-gray-400">

          Don't have an account?{' '}

          <Link
            href="/register"
            className="text-purple-400"
          >
            Register
          </Link>

        </div>

      </div>

    </div>
  );
}