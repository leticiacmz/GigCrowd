import { notFound } from 'next/navigation';

/**
 * Catch-all for any path under a locale that matches no page.
 *
 * The locale is always the first segment, because the next-intl middleware
 * redirects every locale-less path. Catching the remainder here means an
 * unknown URL is resolved inside that locale's layout, so the 404 renders
 * with the right document language, the site chrome and translated copy.
 * Without it an unknown URL falls through to the framework's root
 * not-found route, which sits outside the localized tree and comes back as
 * a bare unstyled English page.
 */
export default function UnknownLocalePath(): never {
  notFound();
}
