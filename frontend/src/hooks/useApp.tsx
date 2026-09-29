import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { QuestionBank, User, AppSettings } from '../types';
import { getUser, login as authLogin, logout as authLogout, getSettings, saveSettings } from '../lib/auth';
import { fetchBanks, deleteBank as apiDeleteBank, errorMessage } from '../lib/api';

// ============================================================
// Context shape
// ============================================================

interface AppContextValue {
  // Auth (mock — the backend has no auth in the MVP)
  user: User | null;
  isLoggedIn: boolean;
  login: (email: string, password: string) => void;
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
  const [user, setUser] = useState<User | null>(() => getUser());
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

  const login = useCallback((email: string, password: string) => {
    const loggedInUser = authLogin(email, password);
    setUser(loggedInUser);
  }, []);

  const logout = useCallback(() => {
    authLogout();
    setUser(null);
    setQuestionBanks([]);
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
