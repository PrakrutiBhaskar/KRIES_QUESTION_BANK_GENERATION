import { useEffect, useState } from 'react';
import { CircleHelp, Download, Loader2, ShieldCheck, TriangleAlert } from 'lucide-react';
import type { Difficulty, Question, QuestionType } from '../types';

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
// Question type badge
// ============================================================
const TYPE_STYLES: Record<string, string> = {
  MCQ: 'bg-blue-100 text-blue-700 border-blue-200',
  Short: 'bg-violet-100 text-violet-700 border-violet-200',
  Long: 'bg-indigo-100 text-indigo-700 border-indigo-200',
  Fill: 'bg-teal-100 text-teal-700 border-teal-200',
  Match: 'bg-amber-100 text-amber-700 border-amber-200',
  Mixed: 'bg-pink-100 text-pink-700 border-pink-200',
};

export const TYPE_LABELS: Record<string, string> = {
  Short: 'Short Answer',
  Long: 'Long Answer',
  Fill: 'Fill in the Blank',
  Match: 'Match the Following',
};

/** Whether `opt` is the option to highlight as correct. A Match key pairs every
 * item with a different option, so no single option is "the answer". */
export function isKeyOption(question: { type: QuestionType; answer: string }, opt: string): boolean {
  return question.type !== 'Match' && opt === question.answer;
}

/** A Match question split for display: the lead-in line plus one Column A / Column B row per pair. */
export function parseMatch(question: { type: QuestionType; text: string; options?: string[] | null }) {
  if (question.type !== 'Match' || !question.options?.length) return null;
  const re = /^\s*(\d{1,2})\s*[.)]\s+(\S.*?)\s*$/;
  const left: string[] = [];
  const stem: string[] = [];
  for (const line of question.text.split('\n')) {
    const m = re.exec(line);
    if (m) left.push(m[2]);
    else if (line.trim()) stem.push(line.trim());
  }
  if (left.length === 0) return null;
  const rows = Array.from({ length: Math.max(left.length, question.options.length) }, (_, i) => ({
    a: left[i] ? `${i + 1}. ${left[i]}` : '',
    b: question.options?.[i] ? `(${String.fromCharCode(97 + i)}) ${question.options[i]}` : '',
  }));
  return { stem: stem.join('\n') || 'Match the following:', rows };
}

/** Match the Following as a two-column table. */
export function MatchTable({ rows }: { rows: { a: string; b: string }[] }) {
  return (
    <table className="w-full my-2 text-xs border-collapse">
      <thead>
        <tr className="bg-slate-100 text-slate-700">
          <th className="w-1/2 text-left font-semibold border border-slate-300 px-3 py-1.5">Column A</th>
          <th className="w-1/2 text-left font-semibold border border-slate-300 px-3 py-1.5">Column B</th>
        </tr>
      </thead>
      <tbody className="text-slate-600">
        {rows.map((r, i) => (
          <tr key={i}>
            <td className="border border-slate-300 px-3 py-1.5 align-top">{r.a}</td>
            <td className="border border-slate-300 px-3 py-1.5 align-top">{r.b}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function TypeBadge({ type }: { type: QuestionType | 'Mixed' | string }) {
  const label = TYPE_LABELS[type] ?? type;
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${TYPE_STYLES[type] ?? 'bg-slate-100 text-slate-600 border-slate-200'}`}
    >
      {label}
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

// ============================================================
// Export dialog — asks whether the PDF should carry the answer key
// ============================================================
interface ExportModalProps {
  open: boolean;
  /** Name of the bank being exported, shown under the title. */
  name?: string;
  /** True while the export request is in flight. */
  exporting?: boolean;
  onConfirm: (includeAnswerKey: boolean) => void;
  onCancel: () => void;
}

export function ExportModal(props: ExportModalProps) {
  // The body mounts fresh on every open, so the toggle always starts on and one
  // export's choice never leaks into the next.
  if (!props.open) return null;
  return <ExportModalBody {...props} />;
}

function ExportModalBody({ name, exporting = false, onConfirm, onCancel }: ExportModalProps) {
  // On by default: it is what the export has always produced.
  const [includeAnswerKey, setIncludeAnswerKey] = useState(true);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !exporting) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [exporting, onCancel]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby="export-modal-title">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={exporting ? undefined : onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm">
        <h3 id="export-modal-title" className="text-base font-semibold text-slate-900">Export PDF</h3>
        {name && <p className="text-sm text-slate-500 mt-0.5 truncate" title={name}>{name}</p>}

        <div className="mt-5 flex items-start gap-3 rounded-xl border border-slate-200 p-3.5">
          <div className="flex-1 min-w-0">
            <p id="export-key-label" className="text-sm font-medium text-slate-900">Include answer key</p>
            <p className="text-xs text-slate-500 mt-0.5">
              {includeAnswerKey
                ? 'Adds an Answer Key section at the end, with explanations.'
                : 'Question paper only, ready to hand out to students.'}
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={includeAnswerKey}
            aria-labelledby="export-key-label"
            disabled={exporting}
            onClick={() => setIncludeAnswerKey((v) => !v)}
            className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:opacity-60 ${
              includeAnswerKey ? 'bg-indigo-600' : 'bg-slate-300'
            }`}
          >
            <span
              className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                includeAnswerKey ? 'translate-x-5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>

        <div className="flex gap-3 justify-end mt-6">
          <button
            onClick={onCancel}
            disabled={exporting}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => onConfirm(includeAnswerKey)}
            disabled={exporting}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            Export
          </button>
        </div>
      </div>
    </div>
  );
}

// Re-export React to avoid import issues
import React from 'react';

// ------------------------------------------------------------
// Answer-key verification
// ------------------------------------------------------------
const VERIFICATION_STYLES = {
  verified: {
    label: 'Answer verified',
    Icon: ShieldCheck,
    cls: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  },
  flagged: {
    label: 'Check answer',
    Icon: TriangleAlert,
    cls: 'bg-amber-50 text-amber-800 border-amber-300',
  },
  unverified: {
    label: 'Not verified',
    Icon: CircleHelp,
    cls: 'bg-slate-50 text-slate-500 border-slate-200',
  },
} as const;

/** Small pill showing whether the answer key was checked. */
export function VerificationBadge({ question }: { question: Question }) {
  const status = question.verificationStatus ?? 'unverified';
  const { label, Icon, cls } = VERIFICATION_STYLES[status];
  return (
    <span
      title={question.verificationNote || label}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${cls}`}
    >
      <Icon className="w-3 h-3" />
      {label}
    </span>
  );
}

/** Always-visible warning under a question whose answer key looked wrong. */
export function VerificationWarning({ question }: { question: Question }) {
  if (question.verificationStatus !== 'flagged') return null;
  return (
    <div
      role="alert"
      className="mt-2 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
    >
      <TriangleAlert className="w-3.5 h-3.5 mt-0.5 shrink-0" />
      <p>
        <span className="font-semibold">The answer key may be wrong.</span>{' '}
        {question.verificationNote} Review or replace this question before using it.
      </p>
    </div>
  );
}

/** The verification note, shown with the answer. */
export function VerificationNote({ question }: { question: Question }) {
  if (!question.verificationNote || question.verificationStatus === 'flagged') return null;
  return <p className="text-xs text-slate-500">Answer check: {question.verificationNote}</p>;
}
