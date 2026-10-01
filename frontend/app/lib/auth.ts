export interface AuthUser {
  id: string;
  email: string;  
  username: string;
  full_name?: string;
  avatar_url?: string;
  bio?: string;
  location?: string;
  role: string;
}

// Token payload decoded from JWT
export interface JwtPayload {
  sub: string;      // user ID  
  exp: number;      // expiration timestamp (seconds since epoch)
  iat: number;      // issued-at timestamp
}

// Check if a JWT token is expired
function isTokenExpired(token: string): boolean {
  if (!token) return true;
  
  try {
    const payload = JSON.parse(
      atob(token.split('.')[1])
    );
    
    if (!payload.exp) return true;
    
    const expirationTime = payload.exp * 1000; // JWT uses seconds, JS uses milliseconds
    return expirationTime < Date.now();
  } catch {
    return true;
  }
}

const TOKEN_KEY = 'token';
const USER_KEY = 'user';

export function saveAuth(data: {
  access_token: string;
  user: AuthUser;
}) {
  if (typeof window === 'undefined') return;

  localStorage.setItem(
    TOKEN_KEY,
    data.access_token
  );

  localStorage.setItem(
    USER_KEY,
    JSON.stringify(data.user)
  );

  window.dispatchEvent(new Event('auth-changed'));
}

export function getToken(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const user =
    localStorage.getItem(USER_KEY);

  if (!user) {
    return null;
  }

  return JSON.parse(user);
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  return !isTokenExpired(token);
}

// Clear stale authentication state (expired/invalid token)
export function clearStaleAuth() {
  if (typeof window === 'undefined') {
    return;
  }
  
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event('auth-changed'));
}

export function logout() {
  if (typeof window === 'undefined') {
    return;
  }

  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);

  window.dispatchEvent(new Event('auth-changed'));
  
}

// ---------------------------------------------------------------------------
// Locale-aware navigation helpers
//
// The session is client-side (localStorage), so route guards live on the
// client too. These helpers only build URLs; they never change how the
// session is stored or read.
// ---------------------------------------------------------------------------

/** Localized login URL, optionally returning the user to `next`. */
export function getLoginPath(
  locale: string,
  next?: string
): string {
  const query = next
    ? `?next=${encodeURIComponent(next)}`
    : '';

  return `/${locale}/login${query}`;
}

/**
 * Accepts a `next` value only when it is a same-origin, locale-prefixed
 * relative path. Anything else (absolute URL, protocol-relative, path
 * outside the app) is discarded so it cannot be used as an open redirect.
 */
export function sanitizeNext(
  value: string | null | undefined
): string | undefined {
  if (!value) {
    return undefined;
  }

  if (!value.startsWith('/') || value.startsWith('//')) {
    return undefined;
  }

  if (value.includes('\\')) {
    return undefined;
  }

  return value;
}

/** Current locale-prefixed path, used as the default `next` target. */
export function getCurrentPath(): string {
  if (typeof window === 'undefined') {
    return '/';
  }

  return `${window.location.pathname}${window.location.search}`;
}

/**
 * Read the validated `next` return target from the current URL.
 *
 * Read imperatively instead of through `useSearchParams()` so the auth
 * pages stay statically prerenderable (a `useSearchParams()` bailout
 * requires a Suspense boundary per route).
 */
export function getNextParam(): string | undefined {
  if (typeof window === 'undefined') {
    return undefined;
  }

  return sanitizeNext(
    new URLSearchParams(window.location.search).get('next')
  );
}