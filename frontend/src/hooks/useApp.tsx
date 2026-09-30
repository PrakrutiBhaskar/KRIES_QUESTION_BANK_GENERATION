import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { QuestionBank, User, AppSettings } from '../types';
import {
  UNAUTHORIZED_EVENT,
  clearSession,
  getSettings,
  getToken,
  getUser,
  isAuthenticated,
  saveSession,
  saveSettings,
  updateStoredUser,
} from '../lib/auth';
import {
  fetchBanks,
  fetchMe,
  deleteBank as apiDeleteBank,
  errorMessage,
  signIn,
  signUp,
  type SignUpInput,
} from '../lib/api';

// ============================================================
// Context shape
// ============================================================

interface AppContextValue {
  // Auth (JWT issued by the backend's /auth endpoints)
  user: User | null;
  isLoggedIn: boolean;
  /** Rejects with an ApiError (e.g. 401 invalid_credentials) on failure. */
  login: (email: string, password: string, remember?: boolean) => Promise<void>;
  /** Creates the account and signs the user in. Rejects with an ApiError (e.g. 409 email_taken). */
  signUp: (input: SignUpInput, remember?: boolean) => Promise<void>;
  logout: () => void;

  // Question banks (server state: papers from the backend)
  questionBanks: QuestionBank[];
  banksLoading: boolean;
  banksError: string | null;
  refreshBanks: () => Promise<void>;
  upsertBank: (bank: QuestionBank) => void;
  deleteQuestionBank: (id: string) => Promise<void>;

  // Settings
  settings: AppSettings;
  updateSettings: (s: AppSettings) => void;

  // Toast
  toast: Toast | null;
  showToast: (message: string, type?: Toast['type']) => void;
}

export interface Toast {
  id: string;
  message: string;
  type: 'success' | 'error' | 'info' | 'warning';
}

const AppContext = createContext<AppContextValue | null>(null);

// ============================================================
// Provider
// ============================================================

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(() => (isAuthenticated() ? getUser() : null));
  const [questionBanks, setQuestionBanks] = useState<QuestionBank[]>([]);
  const [banksLoading, setBanksLoading] = useState(false);
  const [banksError, setBanksError] = useState<string | null>(null);
  const [settings, setSettings] = useState<AppSettings>(() => getSettings());
  const [toast, setToast] = useState<Toast | null>(null);

  const refreshBanks = useCallback(async () => {
    setBanksLoading(true);
    try {
      setQuestionBanks(await fetchBanks());
      setBanksError(null);
    } catch (err) {
      setBanksError(errorMessage(err));
    } finally {
      setBanksLoading(false);
    }
  }, []);

  // Load banks from the backend once the user is signed in.
  const isLoggedIn = user !== null;
  useEffect(() => {
    if (isLoggedIn) void refreshBanks();
  }, [isLoggedIn, refreshBanks]);

  const login = useCallback(async (email: string, password: string, remember = true) => {
    const { token, user: signedIn } = await signIn(email, password);
    saveSession(token, signedIn, remember);
    setUser(signedIn);
  }, []);

  const signUpUser = useCallback(async (input: SignUpInput, remember = true) => {
    const { token, user: created } = await signUp(input);
    saveSession(token, created, remember);
    setUser(created);
  }, []);

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    setQuestionBanks([]);
  }, []);

  // The API client fires this when the server rejects our token.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null);
      setQuestionBanks([]);
    };
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  // On first load, confirm the stored token is still valid (it may have
  // expired). A 401 is handled by the event above; a network error just keeps
  // the cached user so the app still opens while the backend is down.
  useEffect(() => {
    if (!getToken()) return;
    fetchMe()
      .then((fresh) => {
        updateStoredUser(fresh);
        setUser(fresh);
      })
      .catch(() => {
        /* 401 -> handled by the UNAUTHORIZED_EVENT listener; anything else: keep the cached user */
      });
  }, []);

  /** Insert a new bank, or replace an existing one with the same id. */
  const upsertBank = useCallback((bank: QuestionBank) => {
    setQuestionBanks((prev) =>
      prev.some((b) => b.id === bank.id)
        ? prev.map((b) => (b.id === bank.id ? bank : b))
        : [bank, ...prev],
    );
  }, []);

  const deleteQuestionBank = useCallback(async (id: string) => {
    await apiDeleteBank(id);
    setQuestionBanks((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const updateSettings = useCallback((s: AppSettings) => {
    setSettings(s);
    saveSettings(s);
  }, []);

  const showToast = useCallback((message: string, type: Toast['type'] = 'success') => {
    const id = Math.random().toString(36).slice(2);
    setToast({ id, message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const value: AppContextValue = {
    user,
    isLoggedIn,
    login,
    signUp: signUpUser,
    logout,
    questionBanks,
    banksLoading,
    banksError,
    refreshBanks,
    upsertBank,
    deleteQuestionBank,
    settings,
    updateSettings,
    toast,
    showToast,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

// ============================================================
// Hook
// ============================================================

// eslint-disable-next-line react-refresh/only-export-components
export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
