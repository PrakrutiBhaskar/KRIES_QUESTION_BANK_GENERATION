import type { User, AppSettings } from '../types';

// ============================================================
// Session storage — the JWT issued by the backend + a cached copy of the user.
// "Keep me signed in" -> localStorage (survives closing the browser);
// otherwise sessionStorage (cleared when the tab closes).
// ============================================================

const TOKEN_KEY = 'kries_token';
const AUTH_KEY = 'kries_auth';
const SETTINGS_KEY = 'kries_settings';

/** Fired by the API client when the server rejects the stored token. */
export const UNAUTHORIZED_EVENT = 'kries:unauthorized';

function readKey(key: string): string | null {
  try {
    return localStorage.getItem(key) ?? sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return readKey(TOKEN_KEY);
}

export function getUser(): User | null {
  try {
    const raw = readKey(AUTH_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getToken() !== null && getUser() !== null;
}

export function clearSession(): void {
  try {
    for (const store of [localStorage, sessionStorage]) {
      store.removeItem(TOKEN_KEY);
      store.removeItem(AUTH_KEY);
    }
  } catch {
    /* storage unavailable */
  }
}

export function saveSession(token: string, user: User, remember: boolean): void {
  clearSession();
  try {
    const store = remember ? localStorage : sessionStorage;
    store.setItem(TOKEN_KEY, token);
    store.setItem(AUTH_KEY, JSON.stringify(user));
  } catch {
    /* storage unavailable: the session lasts until the page is reloaded */
  }
}

/** Refresh the cached user (after /auth/me) without changing where it lives. */
export function updateStoredUser(user: User): void {
  try {
    const store = localStorage.getItem(TOKEN_KEY) !== null ? localStorage : sessionStorage;
    store.setItem(AUTH_KEY, JSON.stringify(user));
  } catch {
    /* ignore */
  }
}

export const DEFAULT_SETTINGS: AppSettings = {
  theme: 'light',
  notifications: true,
  defaultQuestionCount: 10,
  defaultDifficulty: 'mixed',
  defaultQuestionType: 'Mixed',
  defaultMarks: 2,
};

export function getSettings(): AppSettings {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    return raw ? { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<AppSettings>) } : DEFAULT_SETTINGS;
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export function saveSettings(settings: AppSettings): void {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
}
