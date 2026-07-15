'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { authAPI } from '../lib/api';
import { saveAuth } from '../lib/auth';

export default function RegisterPage() {
  const router = useRouter();

  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
  });

  const [error, setError] = useState('');

  const [loading, setLoading] =
    useState(false);

  function handleChange(
    e: React.ChangeEvent<HTMLInputElement>
  ) {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  }

  async function handleSubmit(
    e: React.FormEvent
  ) {

    e.preventDefault();

    setLoading(true);

    setError('');

    try {

      const response =
        await authAPI.register(
          formData
        );

      saveAuth(response);

      router.push('/feed');

    } catch (err: any) {

      setError(
        err.response?.data?.detail ??
          'Registration failed'
      );

    } finally {

      setLoading(false);

    }

  }

  return (

    <div className="min-h-screen flex items-center justify-center px-4">

      <div className="max-w-md w-full">

        <div className="text-center mb-8">

          <h1 className="text-4xl font-bold mb-2 bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent">

            GigCrowd

          </h1>

          <p className="text-gray-400">

            Create your account

          </p>

        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4"
        >

          <div>

            <label
              htmlFor="email"
              className="block text-sm font-medium mb-2"
            >

              Email

            </label>

            <input
              id="email"
              name="email"
              type="email"
              value={formData.email}
              onChange={handleChange}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
              required
            />

          </div>

          <div>

            <label
              htmlFor="username"
              className="block text-sm font-medium mb-2"
            >

              Username

            </label>

            <input
              id="username"
              name="username"
              type="text"
              value={formData.username}
              onChange={handleChange}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
              required
              minLength={3}
            />

          </div>

          <div>

            <label
              htmlFor="full_name"
              className="block text-sm font-medium mb-2"
            >

              Full Name

            </label>

            <input
              id="full_name"
              name="full_name"
              type="text"
              value={formData.full_name}
              onChange={handleChange}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
            />

          </div>

          <div>

            <label
              htmlFor="password"
              className="block text-sm font-medium mb-2"
            >

              Password

            </label>

            <input
              id="password"
              name="password"
              type="password"
              value={formData.password}
              onChange={handleChange}
              className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg focus:outline-none focus:border-purple-500 transition-colors"
              required
              minLength={8}
            />

          </div>

          {error && (

            <div className="text-red-500 text-sm">

              {error}

            </div>

          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 text-white rounded-lg font-semibold transition-colors"
          >

            {loading
              ? 'Creating account...'
              : 'Register'}

          </button>

        </form>

        <p className="text-center mt-6 text-gray-400">

          Already have an account?{' '}

          <Link
            href="/login"
            className="text-purple-500 hover:text-purple-400"
          >

            Login

          </Link>

        </p>

      </div>

    </div>

  );

}