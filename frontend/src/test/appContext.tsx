import { vi } from 'vitest';
import type { User } from '../types';

/** A signed-in user with the given role. */
export const makeUser = (role: User['role'], overrides: Partial<User> = {}): User =>
  ({ id: `${role}-1`, name: `${role} Person`, email: `${role.toLowerCase()}@school.test`, role, ...overrides }) as User;

/**
 * The value `useApp()` returns in tests: just what the pages under test read.
 * Mock the hook with it:
 *
 *   vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));
 */
export const testApp: { current: Record<string, unknown> } = { current: {} };

export function setApp(role: User['role'] | null, extra: Record<string, unknown> = {}) {
  testApp.current = {
    user: role ? makeUser(role) : null,
    showToast: vi.fn(),
    questionBanks: [],
    banksLoading: false,
    banksError: null,
    refreshBanks: vi.fn(),
    upsertBank: vi.fn(),
    deleteQuestionBank: vi.fn(),
    settings: { theme: 'light' },
    logout: vi.fn(),
    ...extra,
  };
  return testApp.current as { showToast: ReturnType<typeof vi.fn> } & Record<string, unknown>;
}

