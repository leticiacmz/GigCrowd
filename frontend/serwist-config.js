const { withSerwist } = require('@serwist/next');

module.exports = withSerwist({
  sw: {
    // Exclude routes that should NOT be cached
    // These will use a network-first or stale-while-revalidate strategy
    // or be completely excluded from the cache
    additionalPrecache: null,

    // Runtime caching configuration
    workboxConfig: {
      // Don't precache or runtime-cache these routes
      // They will fall back to network-only or delegated handling
      runtimeCaching: [

        // Feed endpoint - should always go to network, not cached
        {
          urlPattern: new RegExp('^https?://localhost:8000/feed'),
          handler: 'NetworkFirst',
          options: {
            cache: {
              // Don't cache feed responses
              name: 'feed-responses',
              maxEntries: 0,
              maxAgeSeconds: 0,
            },
          },
        },

        // API routes that should not be cached
        {
          urlPattern: new RegExp('^https?://localhost:8000/auth'),
          handler: 'NetworkFirst',
          options: {
            cache: {
              name: 'auth-responses',
              maxEntries: 0,
              maxAgeSeconds: 0,
            },
          },
        },

        // Public static assets can be cached
        {
          urlPattern: /^https?.*\.(png|jpg|jpeg|svg|gif|webp|avif|js|css|woff|woff2|ttf|map)$/,
          handler: 'CacheFirst',
          options: {
            cache: {
              name: 'static-assets',
              maxEntries: 100,
              maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
            },
          },
        },
      ],
    },
  },
});