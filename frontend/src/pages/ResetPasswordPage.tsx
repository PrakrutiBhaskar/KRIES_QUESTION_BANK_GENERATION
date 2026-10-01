import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Check, CheckCircle2, Loader2 } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { ApiError, errorMessage, resetPassword } from '../lib/api';
import { AuthShell, FormError, PasswordField } from '../components/AuthShell';

// Keep in sync with backend/app/schemas/auth.py
const MIN_PASSWORD_LENGTH = 8;

export default function ResetPasswordPage() {
  const { isLoggedIn } = useApp();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<{ password?: string; confirm?: string }>({});
  const [formError, setFormError] = useState('');
  const [linkInvalid, setLinkInvalid] = useState(false);
  const [done, setDone] = useState(false);

  if (isLoggedIn && !done) return <Navigate to="/dashboard" replace />;

  const rules = [
    { label: `At least ${MIN_PASSWORD_LENGTH} characters`, ok: password.length >= MIN_PASSWORD_LENGTH },
    { label: 'A letter', ok: /[A-Za-z]/.test(password) },
    { label: 'A number', ok: /\d/.test(password) },
  ];

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setFormError('');

    const found: typeof errors = {};
    if (!rules.every((r) => r.ok)) found.password = 'Password does not meet the requirements below.';
    if (confirm !== password) found.confirm = 'Passwords do not match.';
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setLoading(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.code === 'invalid_reset_token') {
        setLinkInvalid(true);
      } else {
        setFormError(errorMessage(err));
      }
    } finally {
      setLoading(false);
    }
  };

  // No token in the URL, or the server said it's used/expired.
  if (!token || linkInvalid) {
    return (
      <AuthShell
        title="Link expired"
        subtitle="This password reset link is invalid, has expired, or was already used."
        footer={
          <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
            Back to sign in
          </Link>
        }
      >
        <button
          type="button"
          onClick={() => navigate('/forgot-password')}
          className="w-full px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Request a new link
        </button>
      </AuthShell>
    );
  }

  if (done) {
    return (
      <AuthShell
        title="Password updated"
        subtitle="You can now sign in with your new password."
        footer={<span />}
      >
        <div className="space-y-5">
          <div className="flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-lg px-3.5 py-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <p className="text-sm text-emerald-800">Your password has been changed.</p>
          </div>
          <button
            type="button"
            onClick={() => navigate('/login', { replace: true })}
            className="w-full px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Go to sign in
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Set a new password"
      subtitle="Choose a password you haven't used here before."
      footer={
        <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <div>
          <PasswordField
            id="password"
            label="New password"
            autoComplete="new-password"
            required
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
            error={errors.password}
          />
          <ul className="mt-2 space-y-1">
            {rules.map((r) => (
              <li
                key={r.label}
                className={`flex items-center gap-1.5 text-xs ${r.ok ? 'text-emerald-600' : 'text-slate-400'}`}
              >
                <Check className={`w-3 h-3 ${r.ok ? 'opacity-100' : 'opacity-30'}`} />
                {r.label}
              </li>
            ))}
          </ul>
        </div>

        <PasswordField
          id="confirm"
          label="Confirm new password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="••••••••"
          error={errors.confirm}
        />

        {formError && <FormError message={formError} />}

        <button
          type="submit"
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          {loading ? 'Updating…' : 'Update password'}
        </button>
      </form>
    </AuthShell>
  );
}
