import type { Difficulty, QuestionBankStatus, QuestionType, BloomsLevel } from '../types';

// ============================================================
// Difficulty badge
// ============================================================
const DIFF_STYLES: Record<string, string> = {
  easy: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  medium: 'bg-amber-100 text-amber-700 border-amber-200',
  hard: 'bg-red-100 text-red-700 border-red-200',
  mixed: 'bg-purple-100 text-purple-700 border-purple-200',
};

export function DifficultyBadge({ difficulty }: { difficulty: Difficulty | string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${DIFF_STYLES[difficulty] ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}
    >
      {difficulty}
    </span>
  );
}

// ============================================================
// Status badge
// ============================================================
const STATUS_STYLES: Record<QuestionBankStatus, string> = {
  published: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  draft: 'bg-slate-100 text-slate-600 border-slate-200',
  archived: 'bg-zinc-100 text-zinc-500 border-zinc-200',
};

export function StatusBadge({ status }: { status: QuestionBankStatus }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border capitalize ${STATUS_STYLES[status]}`}
    >
      {status}
    </span>
  );
}

// ============================================================
// Question type badge
// ============================================================
const TYPE_STYLES: Record<string, string> = {
  MCQ: 'bg-blue-100 text-blue-700 border-blue-200',
  Short: 'bg-violet-100 text-violet-700 border-violet-200',
  Long: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  Mixed: 'bg-pink-100 text-pink-700 border-pink-200',
};

export function TypeBadge({ type }: { type: QuestionType | 'Mixed' | string }) {
  const label = type === 'Short' ? 'Short Answer' : type === 'Long' ? 'Long Answer' : type;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${TYPE_STYLES[type] ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}
    >
      {label}
    </span>
  );
}

// ============================================================
// Bloom's level badge
// ============================================================
const BLOOMS_COLORS: Record<string, string> = {
  Remember: 'bg-sky-100 text-sky-700',
  Understand: 'bg-teal-100 text-teal-700',
  Apply: 'bg-lime-100 text-lime-700',
  Analyse: 'bg-orange-100 text-orange-700',
  Evaluate: 'bg-rose-100 text-rose-700',
  Create: 'bg-fuchsia-100 text-fuchsia-700',
};

export function BloomsBadge({ level }: { level: BloomsLevel | string }) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${BLOOMS_COLORS[level] ?? 'bg-slate-100 text-slate-600'}`}
    >
      {level}
    </span>
  );
}

// ============================================================
// Subject color dot
// ============================================================
const SUBJECT_COLORS: Record<string, string> = {
  Math: 'bg-blue-500',
  Science: 'bg-emerald-500',
  'Social Science': 'bg-amber-500',
  English: 'bg-violet-500',
  Kannada: 'bg-rose-500',
};

export function SubjectDot({ subject }: { subject: string }) {
  return (
    <span className={`inline-block w-2 h-2 rounded-full ${SUBJECT_COLORS[subject] ?? 'bg-slate-400'}`} />
  );
}

// ============================================================
// Generic stat card
// ============================================================
interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  trend?: string;
  trendUp?: boolean;
  color?: string;
}

export function StatCard({ label, value, icon, trend, trendUp, color = 'bg-indigo-50 text-indigo-600' }: StatCardProps) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5 flex items-start gap-4 shadow-sm hover:shadow-md transition-shadow">
      <div className={`p-3 rounded-lg ${color}`}>{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-slate-500 font-medium">{label}</p>
        <p className="text-2xl font-bold text-slate-900 mt-0.5">{value}</p>
        {trend && (
          <p className={`text-xs mt-1 ${trendUp ? 'text-emerald-600' : 'text-red-500'}`}>
            {trendUp ? '↑' : '↓'} {trend}
          </p>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Empty state
// ============================================================
interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
      <div className="w-14 h-14 bg-slate-100 rounded-full flex items-center justify-center mb-4 text-slate-400">
        {icon}
      </div>
      <h3 className="text-base font-semibold text-slate-900 mb-1">{title}</h3>
      <p className="text-sm text-slate-500 max-w-xs">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// ============================================================
// Confirmation modal
// ============================================================
interface ConfirmModalProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  danger?: boolean;
}

export function ConfirmModal({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  onConfirm,
  onCancel,
  danger = false,
}: ConfirmModalProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">
        <h3 className="text-base font-semibold text-slate-900 mb-2">{title}</h3>
        <p className="text-sm text-slate-600 mb-6">{message}</p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
              danger
                ? 'bg-red-600 text-white hover:bg-red-700'
                : 'bg-indigo-600 text-white hover:bg-indigo-700'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

// Re-export React to avoid import issues
import React from 'react';
