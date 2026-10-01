import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { ArrowLeft, Loader2, MailCheck } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { ApiError, errorMessage, requestPasswordReset } from '../lib/api';
import { AuthField, AuthShell, FormError } from '../components/AuthShell';

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const RESEND_SECONDS = 30;

export default function ForgotPasswordPage() {
  const { isLoggedIn } = useApp();
  const location = useLocation();
  const prefill = (location.state as { email?: string } | null)?.email ?? '';

  const [email, setEmail] = useState(prefill);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);

  if (isLoggedIn) return <Navigate to="/dashboard" replace />;

  const startCooldown = () => {
    setCooldown(RESEND_SECONDS);
    const timer = window.setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };

  const send = async () => {
    setError('');
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      setError('Please enter a valid email address.');
      return;
    }
    setLoading(true);
    try {
      await requestPasswordReset(value);
      setSentTo(value);
      startCooldown();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setError('Too many requests. Please wait a few minutes and try again.');
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void send();
  };

  const footer = (
    <Link
      to="/login"
      className="inline-flex items-center gap-1.5 font-semibold text-indigo-600 hover:text-indigo-700"
    >
      <ArrowLeft className="w-4 h-4" />
      Back to sign in
    </Link>
  );

  if (sentTo) {
    return (
      <AuthShell
        title="Check your email"
        subtitle="If that address has an account, a reset link is on its way."
        footer={footer}
      >
        <div className="space-y-5">
          <div className="flex items-start gap-3 bg-emerald-50 border border-emerald-200 rounded-lg px-3.5 py-3">
            <MailCheck className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <p className="text-sm text-emerald-800">
              We sent instructions to <span className="font-semibold break-all">{sentTo}</span>. The
              link works once and expires in 30 minutes. Check your spam folder if it doesn't arrive.
            </p>
          </div>

          {error && <FormError message={error} />}

          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || cooldown > 0}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 border border-slate-300 hover:bg-slate-50 disabled:opacity-60 text-slate-700 text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin" />}
            {cooldown > 0 ? `Resend email in ${cooldown}s` : 'Resend email'}
          </button>

          <button
            type="button"
            onClick={() => {
              setSentTo(null);
              setError('');
            }}
            className="w-full text-sm text-slate-500 hover:text-slate-700"
          >
            Use a different email
          </button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot your password?"
      subtitle="Enter your email and we'll send you a link to reset it."
      footer={footer}
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField
          id="email"
          label="Email address"
          type="email"
          autoComplete="email"
          required
          autoFocus
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@school.edu.in"
        />

        {error && <FormError message={error} />}

        <button
          type="submit"
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          {loading && <Loader2 className="w-4 h-4 animate-spin" />}
          {loading ? 'Sending…' : 'Send reset link'}
        </button>
      </form>
    </AuthShell>
  );
}
