import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="max-w-3xl text-center">
        <h1 className="text-6xl font-bold mb-6 bg-gradient-to-r from-purple-500 to-pink-500 bg-clip-text text-transparent">
          GigCrowd
        </h1>
        <p className="text-xl text-gray-400 mb-8">
          Track your concerts, discover live events, and connect with music lovers worldwide.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/login"
            className="px-8 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg font-semibold transition-colors"
          >
            Login
          </Link>
          <Link
            href="/register"
            className="px-8 py-3 bg-gray-800 hover:bg-gray-700 text-white rounded-lg font-semibold transition-colors"
          >
            Register
          </Link>
        </div>
      </div>
    </div>
  );
}
