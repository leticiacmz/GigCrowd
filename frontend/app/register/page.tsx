'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

import { authAPI } from '../lib/api';
import { saveAuth } from '../lib/auth';
import Input from '../../components/ui/Input';
import Button from '../../components/ui/Button';
import Card from '../../components/ui/Card';

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
    <div className="min-h-screen flex items-center justify-center px-4 bg-background">

      <Card className="max-w-md w-full p-8">

        <div className="text-center mb-8">

          <h1 className="text-[36px] font-bold mb-2 bg-gradient-to-r from-accent to-secondary bg-clip-text text-transparent">

            GigCrowd

          </h1>

          <p className="text-[18px] text-gray-400">

            Create your account

          </p>

        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4"
        >

          <Input
            id="email"
            name="email"
            type="email"
            label="Email"
            value={formData.email}
            onChange={handleChange}
            required
          />

          <Input
            id="username"
            name="username"
            type="text"
            label="Username"
            value={formData.username}
            onChange={handleChange}
            required
            minLength={3}
          />

          <Input
            id="full_name"
            name="full_name"
            type="text"
            label="Full Name"
            value={formData.full_name}
            onChange={handleChange}
          />

          <Input
            id="password"
            name="password"
            type="password"
            label="Password"
            value={formData.password}
            onChange={handleChange}
            required
            minLength={8}
          />

          {error && (
            <div className="text-red-500 text-sm">
              {error}
            </div>
          )}

          <Button
            type="submit"
            disabled={loading}
            className="w-full"
            size="lg"
          >
            {loading
              ? 'Creating account...'
              : 'Register'}
          </Button>

        </form>

        <p className="text-center mt-6 text-gray-400">

          Already have an account?{' '}

          <Link
            href="/login"
            className="text-accent hover:text-accent/80 transition-colors"
          >
            Login
          </Link>

        </p>

      </Card>

    </div>

  );

}