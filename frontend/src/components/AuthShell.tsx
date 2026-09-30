import { useState, type ReactNode } from 'react';
import { GraduationCap, Eye, EyeOff } from 'lucide-react';

const INPUT_CLASS =
  'w-full px-3.5 py-2.5 rounded-lg border text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-shadow';

/** Two-column layout shared by the sign-in and sign-up pages. */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}) {
  return (
    <div className="min-h-screen flex">
      {/* Left — brand panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-indigo-500 rounded-xl flex items-center justify-center">
            <GraduationCap className="w-6 h-6 text-white" />
          </div>
          <div>
            <p className="text-white font-bold text-lg tracking-wide">KRIES</p>
            <p className="text-indigo-300 text-xs">Question Bank Generation System</p>
          </div>
        </div>

        <div>
          <blockquote className="text-2xl font-light text-white/90 leading-relaxed mb-6">
            "Empowering Karnataka teachers with AI-generated, syllabus-aligned question banks for
            Grades 7–9."
          </blockquote>
          <div className="flex flex-col gap-3">
            {[
              { label: 'Subjects', value: '5 Karnataka State Board Subjects' },
              { label: 'Question Types', value: 'MCQ · Short Answer · Long Answer' },
              { label: 'Grades', value: 'Grade 7 · Grade 8 · Grade 9' },
            ].map(({ label, value }) => (
              <div key={label} className="flex items-center gap-3">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                <span className="text-sm text-slate-400">
                  <span className="text-white font-medium">{label}:</span> {value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-slate-600">
          © 2026 KRIES · Karnataka Regional Institute of Education System
        </p>
      </div>

      {/* Right — form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-white">
        <div className="w-full max-w-sm">
          <div className="flex lg:hidden items-center gap-3 mb-8">
            <div className="w-9 h-9 bg-indigo-600 rounded-xl flex items-center justify-center">
              <GraduationCap className="w-5 h-5 text-white" />
            </div>
            <div>
              <p className="font-bold text-slate-900">KRIES</p>
              <p className="text-xs text-slate-500">Question Bank System</p>
            </div>
          </div>

          <h2 className="text-2xl font-bold text-slate-900 mb-1">{title}</h2>
          <p className="text-sm text-slate-500 mb-8">{subtitle}</p>

          {children}

          <p className="text-sm text-center text-slate-500 mt-8">{footer}</p>
        </div>
      </div>
    </div>
  );
}

/** Labelled text input with an optional inline error. */
export function AuthField({
  id,
  label,
  error,
  ...input
}: {
  id: string;
  label: string;
  error?: string;
} & React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-1.5">
        {label}
      </label>
      <input
        id={id}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        {...input}
        className={`${INPUT_CLASS} ${error ? 'border-red-400' : 'border-slate-300'}`}
      />
      {error && (
        <p id={`${id}-error`} className="text-xs text-red-600 mt-1">
          {error}
        </p>
      )}
    </div>
  );
}

/** Password input with a show/hide toggle. */
export function PasswordField({
  id,
  label,
  error,
  ...input
}: {
  id: string;
  label: string;
  error?: string;
} & Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-slate-700 mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={show ? 'text' : 'password'}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : undefined}
          {...input}
          className={`${INPUT_CLASS} pr-10 ${error ? 'border-red-400' : 'border-slate-300'}`}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
          aria-label={show ? 'Hide password' : 'Show password'}
        >
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      {error && (
        <p id={`${id}-error`} className="text-xs text-red-600 mt-1">
          {error}
        </p>
      )}
    </div>
  );
}

export function FormError({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="bg-red-50 border border-red-200 rounded-lg px-3.5 py-2.5 text-sm text-red-700"
    >
      {message}
    </div>
  );
}
