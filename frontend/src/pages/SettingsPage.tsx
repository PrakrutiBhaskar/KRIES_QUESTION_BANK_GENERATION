import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { User as UserIcon, Sliders, LogOut, Save, CheckCircle2, Loader2, Lock, Info } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { errorMessage } from '../lib/api';
import { DEFAULT_SETTINGS } from '../lib/auth';
import { applyTheme } from '../lib/theme';
import { FormError } from '../components/AuthShell';
import type { AppSettings, Difficulty, User } from '../types';

type Tab = 'profile' | 'preferences' | 'account';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'profile', label: 'Profile', icon: <UserIcon className="w-4 h-4" /> },
  { id: 'preferences', label: 'Preferences', icon: <Sliders className="w-4 h-4" /> },
  { id: 'account', label: 'Account', icon: <LogOut className="w-4 h-4" /> },
];

const INPUT =
  'w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
const SECTION_TITLE = 'text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100';

const sameSettings = (a: AppSettings, b: AppSettings) =>
  (Object.keys(a) as (keyof AppSettings)[]).every((k) => a[k] === b[k]);

export default function SettingsPage() {
  const { user, settings } = useApp();
  const [activeTab, setActiveTab] = useState<Tab>('profile');
  if (!user) return null;

  // The form is re-created whenever the saved account or preferences change (after a
  // save, or when the server's copy arrives on page load), so it never shows stale values.
  return (
    <SettingsForm
      key={JSON.stringify([user, settings])}
      user={user}
      settings={settings}
      activeTab={activeTab}
      onTabChange={setActiveTab}
    />
  );
}

function SettingsForm({
  user,
  settings,
  activeTab,
  onTabChange,
}: {
  user: User;
  settings: AppSettings;
  activeTab: Tab;
  onTabChange: (t: Tab) => void;
}) {
  const { saveProfile, logout, showToast } = useApp();
  const navigate = useNavigate();

  // Drafts: nothing is saved until the user presses Save.
  const [name, setName] = useState(user.name);
  const [role, setRole] = useState<User['role']>(user.role);
  const [draft, setDraft] = useState<AppSettings>(settings);

  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [nameError, setNameError] = useState('');
  const [formError, setFormError] = useState('');

  const setField = <K extends keyof AppSettings>(key: K, val: AppSettings[K]) =>
    setDraft((p) => ({ ...p, [key]: val }));

  const dirty = name.trim() !== user.name || role !== user.role || !sameSettings(draft, settings);

  // Preview the chosen theme straight away; if the user leaves without saving, go back to the saved one.
  const savedTheme = useRef(settings.theme);
  useEffect(() => {
    applyTheme(draft.theme);
  }, [draft.theme]);
  useEffect(() => () => applyTheme(savedTheme.current), []);

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    setFormError('');
    setNameError('');

    const trimmed = name.trim();
    if (!trimmed) {
      setNameError('Name cannot be empty.');
      onTabChange('profile');
      return;
    }
    if (trimmed.length > 100) {
      setNameError('Name must be 100 characters or fewer.');
      onTabChange('profile');
      return;
    }

    // Send only what changed. The email is never part of the request.
    const changes: Parameters<typeof saveProfile>[0] = {};
    if (trimmed !== user.name) changes.name = trimmed;
    if (role !== user.role && role !== 'Admin') changes.role = role;
    if (!sameSettings(draft, settings)) changes.settings = draft;
    if (Object.keys(changes).length === 0) return;

    setSaving(true);
    try {
      await saveProfile(changes);
      showToast('Settings saved.', 'success');
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    } catch (err) {
      setFormError(errorMessage(err));
      showToast(errorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setFormError('');
    setSaving(true);
    try {
      await saveProfile({ settings: DEFAULT_SETTINGS });
      showToast('Preferences reset to defaults.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Settings</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Manage your profile and preferences. Changes are saved to your account.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Tab bar */}
        <div className="flex border-b border-slate-200 overflow-x-auto scrollbar-thin">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => onTabChange(tab.id)}
              className={`flex items-center gap-2 px-5 py-3.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-700'
                  : 'border-transparent text-slate-500 hover:text-slate-800 hover:bg-slate-50'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>

        <form onSubmit={handleSave} className="p-6" noValidate>
          {/* Profile tab */}
          {activeTab === 'profile' && (
            <div className="space-y-5">
              <div className="flex items-center gap-4 pb-5 border-b border-slate-100">
                <div className="w-14 h-14 rounded-full bg-indigo-500 flex items-center justify-center text-xl font-bold text-white shrink-0">
                  {(name.trim() || user.name).charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">{name.trim() || user.name}</p>
                  <p className="text-xs text-slate-500">{role}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="settings-name" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Full Name
                  </label>
                  <input
                    id="settings-name"
                    type="text"
                    maxLength={100}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    aria-invalid={nameError ? true : undefined}
                    className={`${INPUT} ${nameError ? 'border-red-400' : ''}`}
                  />
                  {nameError && <p className="text-xs text-red-600 mt-1">{nameError}</p>}
                </div>

                <div>
                  <label htmlFor="settings-email" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Email Address
                  </label>
                  <div className="relative">
                    <input
                      id="settings-email"
                      type="email"
                      value={user.email}
                      readOnly
                      disabled
                      aria-describedby="settings-email-note"
                      className={`${INPUT} pr-9 !bg-slate-100 text-slate-500 cursor-not-allowed`}
                    />
                    <Lock className="w-4 h-4 text-slate-400 absolute right-3 top-1/2 -translate-y-1/2" />
                  </div>
                  <p id="settings-email-note" className="text-xs text-slate-500 mt-1">
                    Your email is your sign-in and can't be changed.
                  </p>
                </div>

                <div>
                  <label htmlFor="settings-role" className="block text-sm font-medium text-slate-700 mb-1.5">
                    Role
                  </label>
                  {user.role === 'Admin' ? (
                    <>
                      <input id="settings-role" value="Admin" readOnly disabled className={`${INPUT} !bg-slate-100 text-slate-500 cursor-not-allowed`} />
                      <p className="text-xs text-slate-500 mt-1">Administrator accounts can't change their role.</p>
                    </>
                  ) : (
                    <select
                      id="settings-role"
                      value={role}
                      onChange={(e) => setRole(e.target.value as User['role'])}
                      className={INPUT}
                    >
                      <option>Teacher</option>
                      <option>Student</option>
                    </select>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Preferences tab (appearance, notifications, and the generation defaults) */}
          {activeTab === 'preferences' && (
            <div className="space-y-7">
              <div>
                <h4 className={SECTION_TITLE}>Appearance</h4>
                <label className="block text-sm font-medium text-slate-700 mb-2">Theme</label>
                <div className="flex gap-3" role="radiogroup" aria-label="Theme">
                  {(['light', 'dark', 'system'] as const).map((theme) => (
                    <button
                      key={theme}
                      type="button"
                      role="radio"
                      aria-checked={draft.theme === theme}
                      onClick={() => setField('theme', theme)}
                      className={`flex-1 py-2.5 text-sm rounded-lg border font-medium capitalize transition-colors ${
                        draft.theme === theme
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'
                      }`}
                    >
                      {theme}
                    </button>
                  ))}
                </div>
                {draft.theme === 'system' && (
                  <p className="text-xs text-slate-500 mt-2">Follows your device's light or dark setting.</p>
                )}
              </div>

              <div>
                <h4 className={SECTION_TITLE}>Notifications</h4>
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-sm font-medium text-slate-900">In-app Notifications</p>
                    <p className="text-xs text-slate-500 mt-0.5">
                      Show pop-up messages for actions (errors are always shown)
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setField('notifications', !draft.notifications)}
                    className={`relative w-11 h-6 rounded-full transition-colors shrink-0 ${
                      draft.notifications ? 'bg-indigo-600' : 'bg-slate-300'
                    }`}
                    role="switch"
                    aria-checked={draft.notifications}
                    aria-label="In-app notifications"
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-5 h-5 bg-[#fff] rounded-full shadow transition-transform ${
                        draft.notifications ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              <div>
                <h4 className={SECTION_TITLE}>Generation Defaults</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <div>
                    <label htmlFor="pref-count" className="block text-sm font-medium text-slate-700 mb-1.5">
                      Default Question Count:{' '}
                      <span className="font-bold text-indigo-600">{draft.defaultQuestionCount}</span>
                    </label>
                    <input
                      id="pref-count"
                      type="range"
                      min={3}
                      max={30}
                      value={draft.defaultQuestionCount}
                      onChange={(e) => setField('defaultQuestionCount', parseInt(e.target.value, 10))}
                      className="w-full accent-indigo-600"
                    />
                  </div>

                  <div>
                    <label htmlFor="pref-difficulty" className="block text-sm font-medium text-slate-700 mb-1.5">
                      Default Difficulty
                    </label>
                    <select
                      id="pref-difficulty"
                      value={draft.defaultDifficulty}
                      onChange={(e) => setField('defaultDifficulty', e.target.value as Difficulty)}
                      className={INPUT}
                    >
                      {['easy', 'medium', 'hard', 'mixed'].map((d) => (
                        <option key={d} value={d}>
                          {d.charAt(0).toUpperCase() + d.slice(1)}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label htmlFor="pref-type" className="block text-sm font-medium text-slate-700 mb-1.5">
                      Default Question Type
                    </label>
                    <select
                      id="pref-type"
                      value={draft.defaultQuestionType}
                      onChange={(e) =>
                        setField('defaultQuestionType', e.target.value as AppSettings['defaultQuestionType'])
                      }
                      className={INPUT}
                    >
                      {['MCQ', 'Short', 'Long', 'Fill', 'Match', 'Mixed'].map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <span className="block text-sm font-medium text-slate-700 mb-1.5">Default Marks per Question</span>
                    <div className="flex gap-2" role="radiogroup" aria-label="Default marks">
                      {([1, 2, 3, 5] as const).map((m) => (
                        <button
                          key={m}
                          type="button"
                          role="radio"
                          aria-checked={draft.defaultMarks === m}
                          onClick={() => setField('defaultMarks', m)}
                          className={`flex-1 py-2.5 text-sm rounded-lg border font-medium transition-colors ${
                            draft.defaultMarks === m
                              ? 'bg-indigo-600 text-white border-indigo-600'
                              : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'
                          }`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 mt-5">
                  <div className="flex gap-3">
                    <Info className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-medium text-amber-800">Marks-Aware Generation</p>
                      <p className="text-xs text-amber-700 mt-1">
                        Questions are automatically generated with answer depth matching the Karnataka State Board
                        marking scheme: 1 mark → direct answer, 2 marks → brief with supporting point, 3 marks → 3
                        distinct points, 5 marks → detailed multi-part answer.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Account tab */}
          {activeTab === 'account' && (
            <div className="space-y-5">
              <div className="border border-slate-200 rounded-xl p-5">
                <h4 className="text-sm font-semibold text-slate-900 mb-1">Sign Out</h4>
                <p className="text-sm text-slate-500 mb-4">You will be logged out and your session will be cleared.</p>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                  Sign Out
                </button>
              </div>

              <div className="border border-slate-200 rounded-xl p-5">
                <h4 className="text-sm font-semibold text-slate-900 mb-1">Reset to Defaults</h4>
                <p className="text-sm text-slate-500 mb-4">
                  Reset theme, notifications and generation defaults to their original values. This is saved right away.
                </p>
                <button
                  type="button"
                  onClick={() => void handleReset()}
                  disabled={saving}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100 disabled:opacity-60 transition-colors"
                >
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                  Reset Preferences
                </button>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">System Info</p>
                <dl className="space-y-2">
                  {[
                    { label: 'Version', value: '1.0.0' },
                    { label: 'Board', value: 'Karnataka State Board' },
                    { label: 'Grades', value: '7 · 8 · 9' },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex items-center gap-3">
                      <dt className="text-xs text-slate-400 w-24 shrink-0">{label}</dt>
                      <dd className="text-xs text-slate-700 font-medium">{value}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          )}

          {formError && activeTab !== 'account' && (
            <div className="mt-5">
              <FormError message={formError} />
            </div>
          )}

          {/* Save button (not shown on the account tab) */}
          {activeTab !== 'account' && (
            <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-end gap-3">
              {dirty && !saving && <span className="text-xs text-slate-500">You have unsaved changes</span>}
              <button
                type="submit"
                disabled={saving || (!dirty && !justSaved)}
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg transition-colors bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Saving…
                  </>
                ) : justSaved ? (
                  <>
                    <CheckCircle2 className="w-4 h-4" />
                    Saved!
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    Save Changes
                  </>
                )}
              </button>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
