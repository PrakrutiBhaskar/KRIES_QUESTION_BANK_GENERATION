import { useState, type FormEvent } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { Check, Loader2 } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { ApiError, errorMessage } from '../lib/api';
import { AuthField, AuthShell, FormError, PasswordField } from '../components/AuthShell';

// Keep in sync with backend/app/schemas/auth.py
const MIN_PASSWORD_LENGTH = 8;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

type Role = 'Teacher' | 'Student';
type FieldErrors = Partial<Record<'name' | 'email' | 'password' | 'confirm', string>>;

export default function SignUpPage() {
  const { signUp, isLoggedIn } = useApp();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('Teacher');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState('');

  if (isLoggedIn) return <Navigate to="/dashboard" replace />;

  const rules = [
    { label: `At least ${MIN_PASSWORD_LENGTH} characters`, ok: password.length >= MIN_PASSWORD_LENGTH },
    { label: 'A letter', ok: /[A-Za-z]/.test(password) },
    { label: 'A number', ok: /\d/.test(password) },
  ];

  const validate = (): FieldErrors => {
    const e: FieldErrors = {};
    if (!name.trim()) e.name = 'Please enter your name.';
    if (!EMAIL_RE.test(email.trim())) e.email = 'Please enter a valid email address.';
    if (!rules.every((r) => r.ok)) e.password = 'Password does not meet the requirements below.';
    if (confirm !== password) e.confirm = 'Passwords do not match.';
    return e;
  };

  const handleSubmit = async (ev: FormEvent) => {
    ev.preventDefault();
    setFormError('');

    const found = validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setLoading(true);
    try {
      await signUp({ name: name.trim(), email: email.trim(), password, role }, true);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'email_taken') {
        setErrors({ email: 'An account with this email already exists.' });
      } else {
        setFormError(errorMessage(err));
      }
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start generating syllabus-aligned question banks."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-indigo-600 hover:text-indigo-700">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <AuthField
          id="name"
          label="Full name"
          autoComplete="name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Priya Sharma"
          error={errors.name}
        />

        <AuthField
          id="email"
          label="Email address"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@school.edu.in"
          error={errors.email}
        />

        <div>
          <span className="block text-sm font-medium text-slate-700 mb-1.5">I am a</span>
          <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Role">
            {(['Teacher', 'Student'] as const).map((r) => (
              <button
                key={r}
                type="button"
                role="radio"
                aria-checked={role === r}
                onClick={() => setRole(r)}
                className={`px-3 py-2 rounded-lg border text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                  role === r
                    ? 'border-indigo-600 bg-indigo-50 text-indigo-700'
                    : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div>
          <PasswordField
            id="password"
            label="Password"
            autoComplete="new-password"
            required
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
          label="Confirm password"
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
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </AuthShell>
  );
}
