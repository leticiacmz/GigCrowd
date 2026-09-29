const TOKEN_KEY = 'token';

const USER_KEY = 'user';


export interface AuthResponse {

  access_token: string;

  token_type?: string;

  user?: any;

}


export function getToken(): string | null {

  if (typeof window === 'undefined') {
    return null;
  }

  return localStorage.getItem(TOKEN_KEY);

}


export function getStoredUser(): any | null {

  if (typeof window === 'undefined') {
    return null;
  }

  const raw = localStorage.getItem(USER_KEY);

  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw);

  } catch {
    localStorage.removeItem(USER_KEY);

    return null;
  }

}


export function saveAuth(response: AuthResponse): void {

  if (typeof window === 'undefined') {
    return;
  }

  if (response?.access_token) {
    localStorage.setItem(TOKEN_KEY, response.access_token);
  }

  if (response?.user) {
    localStorage.setItem(USER_KEY, JSON.stringify(response.user));
  }

}


export function isAuthenticated(): boolean {

  return Boolean(getToken());

}


export function logout(): void {

  if (typeof window === 'undefined') {
    return;
  }

  localStorage.removeItem(TOKEN_KEY);

  localStorage.removeItem(USER_KEY);

}
