import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { QuestionBank, User, AppSettings } from '../types';
import { getUser, login as authLogin, logout as authLogout, getSettings, saveSettings } from '../lib/auth';
import { loadQuestionBanks, saveQuestionBanks } from '../lib/storage';

// ============================================================
// Context shape
// ============================================================

interface AppContextValue {
  // Auth
  user: User | null;
  isLoggedIn: boolean;
  login: (email: string, password: string) => void;
  logout: () => void;

  // Question banks
  questionBanks: QuestionBank[];
  addQuestionBank: (bank: QuestionBank) => void;
  updateQuestionBank: (bank: QuestionBank) => void;
  deleteQuestionBank: (id: string) => void;
  getQuestionBank: (id: string) => QuestionBank | undefined;

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
  const [questionBanks, setQuestionBanks] = useState<QuestionBank[]>(() => loadQuestionBanks());
  const [settings, setSettings] = useState<AppSettings>(() => getSettings());
  const [toast, setToast] = useState<Toast | null>(null);

  // Persist question banks whenever they change
  useEffect(() => {
    saveQuestionBanks(questionBanks);
  }, [questionBanks]);

  const login = useCallback((email: string, password: string) => {
    const loggedInUser = authLogin(email, password);
    setUser(loggedInUser);
  }, []);

  const logout = useCallback(() => {
    authLogout();
    setUser(null);
  }, []);

  const addQuestionBank = useCallback((bank: QuestionBank) => {
    setQuestionBanks((prev) => [bank, ...prev]);
  }, []);

  const updateQuestionBank = useCallback((updated: QuestionBank) => {
    setQuestionBanks((prev) => prev.map((b) => (b.id === updated.id ? updated : b)));
  }, []);

  const deleteQuestionBank = useCallback((id: string) => {
    setQuestionBanks((prev) => prev.filter((b) => b.id !== id));
  }, []);

  const getQuestionBank = useCallback(
    (id: string) => questionBanks.find((b) => b.id === id),
    [questionBanks],
  );

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
    isLoggedIn: user !== null,
    login,
    logout,
    questionBanks,
    addQuestionBank,
    updateQuestionBank,
    deleteQuestionBank,
    getQuestionBank,
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

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used inside AppProvider');
  return ctx;
}
