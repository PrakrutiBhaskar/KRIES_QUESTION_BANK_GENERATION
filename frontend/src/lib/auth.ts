import type { User, AppSettings } from '../types';

// ============================================================
// Auth helpers — mock login using localStorage
// ============================================================

const AUTH_KEY = 'kries_auth';
const SETTINGS_KEY = 'kries_settings';

export const MOCK_USER: User = {
  id: 'user-001',
  name: 'Priya Sharma',
  email: 'priya.sharma@school.edu.in',
  role: 'Teacher',
};

export const DEFAULT_SETTINGS: AppSettings = {
  theme: 'light',
  notifications: true,
  defaultQuestionCount: 10,
  defaultDifficulty: 'mixed',
  defaultQuestionType: 'Mixed',
  defaultMarks: 2,
};

export function login(email: string, _password: string): User {
  const user = { ...MOCK_USER, email };
  localStorage.setItem(AUTH_KEY, JSON.stringify(user));
  return user;
}

export function logout(): void {
  localStorage.removeItem(AUTH_KEY);
}

export function getUser(): User | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getUser() !== null;
}

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
