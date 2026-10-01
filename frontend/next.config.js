const createNextIntlPlugin = require('next-intl/plugin');
const os = require('os');

const withNextIntl = createNextIntlPlugin('./i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'localhost',
      },
      {
        protocol: 'https',
        hostname: '**.spotifycdn.com',
      },
      {
        protocol: 'https',
        hostname: '**.scdn.co',
      },
    ],
  },

  // Development only: allow LAN IP access for Next.js dev server
  // Auto-detects the machine's non-loopback IPv4 addresses via os.networkInterfaces()
  // so that LAN development works without hardcoding IPs or editing .env.local
  allowedDevOrigins: (() => {
    try {
      const interfaces = os.networkInterfaces();
      const allowed = new Set();

      for (const iface of Object.values(interfaces)) {
        if (!iface) continue;
        for (const alias of iface) {
          if (
            alias.family === 'IPv4' &&
            !alias.internal &&
            alias.address !== '127.0.0.1'
          ) {
            allowed.add(alias.address);
          }
        }
      }

      // Always include localhost
      allowed.add('localhost');

      return Array.from(allowed);
    } catch {
      // Fallback if os.networkInterfaces fails
      return ['localhost'];
    }
  })(),
};

module.exports = withNextIntl(nextConfig);