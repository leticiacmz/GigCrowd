'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

import { isAuthenticated } from './lib/auth';
import Button from '../components/ui/Button';
import Card from '../components/ui/Card';

export default function Home() {

  const router = useRouter();

  useEffect(() => {

    if (isAuthenticated()) {

      router.replace('/feed');

    }

  }, [router]);

  return (

    <div className="min-h-screen flex flex-col items-center justify-center px-4">

      <Card className="max-w-3xl text-center p-8">

        <h1 className="text-[36px] font-bold mb-6 bg-gradient-to-r from-accent to-secondary bg-clip-text text-transparent">

          GigCrowd

        </h1>

        <p className="text-[18px] text-gray-400 mb-8">

          Track your concerts, discover live events, and connect with music lovers worldwide.

        </p>

        <div className="flex gap-4 justify-center">

          <Link
            href="/login"
            className="w-full"
          >
            <Button variant="primary" size="lg" className="w-full">
              Login
            </Button>
          </Link>

          <Link
            href="/register"
            className="w-full"
          >
            <Button variant="outline" size="lg" className="w-full">
              Register
            </Button>
          </Link>

        </div>

      </Card>

    </div>

  );

}