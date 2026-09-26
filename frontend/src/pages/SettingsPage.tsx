import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { User, Bell, Sliders, Wand2, LogOut, Save, CheckCircle2 } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import type { AppSettings, Difficulty, BloomsLevel } from '../types';

type Tab = 'profile' | 'preferences' | 'generation' | 'account';

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: 'profile', label: 'Profile', icon: <User className="w-4 h-4" /> },
  { id: 'preferences', label: 'Preferences', icon: <Bell className="w-4 h-4" /> },
  { id: 'generation', label: 'Generation', icon: <Wand2 className="w-4 h-4" /> },
  { id: 'account', label: 'Account', icon: <LogOut className="w-4 h-4" /> },
];

export default function SettingsPage() {
  const { user, settings, updateSettings, logout, showToast } = useApp();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<Tab>('profile');
  const [saved, setSaved] = useState(false);

  // Profile fields (local state only — no backend)
  const [name, setName] = useState(user?.name ?? '');
  const [email, setEmail] = useState(user?.email ?? '');
  const [role, setRole] = useState(user?.role ?? 'Teacher');

  // Settings state
  const [localSettings, setLocalSettings] = useState<AppSettings>(settings);

  const setSettingField = <K extends keyof AppSettings>(key: K, val: AppSettings[K]) =>
    setLocalSettings((p) => ({ ...p, [key]: val }));

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    updateSettings(localSettings);
    setSaved(true);
    showToast('Settings saved.', 'success');
    setTimeout(() => setSaved(false), 2000);
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
          Manage your profile, preferences, and generation defaults.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Tab bar */}
        <div className="flex border-b border-slate-200 overflow-x-auto scrollbar-thin">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
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

        {/* Content */}
        <form onSubmit={handleSave} className="p-6">
          {/* Profile tab */}
          {activeTab === 'profile' && (
            <div className="space-y-5">
              <div className="flex items-center gap-4 pb-5 border-b border-slate-100">
                <div className="w-14 h-14 rounded-full bg-indigo-500 flex items-center justify-center text-xl font-bold text-white shrink-0">
                  {name.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">{name}</p>
                  <p className="text-xs text-slate-500">{role}</p>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Full Name</label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Email Address</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1.5">Role</label>
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value as 'Teacher' | 'Student' | 'Admin')}
                    className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    <option>Teacher</option>
                    <option>Student</option>
                    <option>Admin</option>
                  </select>
                </div>
              </div>

              <p className="text-xs text-slate-400">
                Profile changes are saved locally and reset on logout (demo mode).
              </p>
            </div>
          )}

          {/* Preferences tab */}
          {activeTab === 'preferences' && (
            <div className="space-y-5">
              <div>
                <h4 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
                  Appearance
                </h4>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-2">Theme</label>
                  <div className="flex gap-3">
                    {(['light', 'dark', 'system'] as const).map((theme) => (
                      <button
                        key={theme}
                        type="button"
                        onClick={() => setSettingField('theme', theme)}
                        className={`flex-1 py-2.5 text-sm rounded-lg border font-medium capitalize transition-colors ${
                          localSettings.theme === theme
                            ? 'bg-indigo-600 text-white border-indigo-600'
                            : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'
                        }`}
                      >
                        {theme}
                      </button>
                    ))}
                  </div>
                  <p className="text-xs text-slate-400 mt-2">Dark/system themes are noted but apply on light mode in this demo.</p>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
                  Notifications
                </h4>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-slate-900">In-app Notifications</p>
                    <p className="text-xs text-slate-500 mt-0.5">Show toast notifications for actions</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSettingField('notifications', !localSettings.notifications)}
                    className={`relative w-11 h-6 rounded-full transition-colors ${
                      localSettings.notifications ? 'bg-indigo-600' : 'bg-slate-200'
                    }`}
                    role="switch"
                    aria-checked={localSettings.notifications}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                        localSettings.notifications ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
                  Question Defaults
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">
                      Default Question Count: <span className="font-bold text-indigo-600">{localSettings.defaultQuestionCount}</span>
                    </label>
                    <input
                      type="range"
                      min={3}
                      max={30}
                      value={localSettings.defaultQuestionCount}
                      onChange={(e) => setSettingField('defaultQuestionCount', parseInt(e.target.value))}
                      className="w-full accent-indigo-600"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">Default Difficulty</label>
                    <select
                      value={localSettings.defaultDifficulty}
                      onChange={(e) => setSettingField('defaultDifficulty', e.target.value as Difficulty)}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {['easy', 'medium', 'hard', 'mixed'].map((d) => (
                        <option key={d} value={d} className="capitalize">{d.charAt(0).toUpperCase() + d.slice(1)}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">Default Question Type</label>
                    <select
                      value={localSettings.defaultQuestionType}
                      onChange={(e) => setSettingField('defaultQuestionType', e.target.value as AppSettings['defaultQuestionType'])}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {['MCQ', 'Short', 'Long', 'Mixed'].map((t) => <option key={t}>{t}</option>)}
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Generation settings tab */}
          {activeTab === 'generation' && (
            <div className="space-y-5">
              <div>
                <h4 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
                  AI Generation Defaults
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">Default Bloom's Level</label>
                    <select
                      value={localSettings.defaultBloomsLevel}
                      onChange={(e) => setSettingField('defaultBloomsLevel', e.target.value as BloomsLevel | 'Mixed')}
                      className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {['Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create', 'Mixed'].map((b) => (
                        <option key={b}>{b}</option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1.5">Default Marks per Question</label>
                    <div className="flex gap-2">
                      {([1, 2, 3, 5] as const).map((m) => (
                        <button
                          key={m}
                          type="button"
                          onClick={() => setSettingField('defaultMarks', m)}
                          className={`flex-1 py-2 text-sm rounded-lg border font-medium transition-colors ${
                            localSettings.defaultMarks === m
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
              </div>

              <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
                <div className="flex gap-3">
                  <Sliders className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-medium text-amber-800">Marks-Aware Generation</p>
                    <p className="text-xs text-amber-700 mt-1">
                      Questions are automatically generated with answer depth matching Karnataka State Board marking
                      scheme: 1 mark → direct answer, 2 marks → brief with supporting point, 3 marks → 3 distinct
                      points, 5 marks → detailed multi-part answer.
                    </p>
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
                <p className="text-sm text-slate-500 mb-4">
                  You will be logged out and your session will be cleared.
                </p>
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
                  Reset all settings and question banks to the original demo state.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    localStorage.clear();
                    window.location.reload();
                  }}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-lg hover:bg-amber-100 transition-colors"
                >
                  Reset Demo Data
                </button>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">System Info</p>
                <dl className="space-y-2">
                  {[
                    { label: 'Version', value: '1.0.0 (Demo)' },
                    { label: 'Board', value: 'Karnataka State Board' },
                    { label: 'Grades', value: '7 · 8 · 9' },
                    { label: 'Backend', value: 'Not connected (Frontend Demo)' },
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

          {/* Save button (not shown on account tab) */}
          {activeTab !== 'account' && (
            <div className="mt-6 pt-4 border-t border-slate-100 flex justify-end">
              <button
                type="submit"
                className="flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-lg transition-colors bg-indigo-600 text-white hover:bg-indigo-700"
              >
                {saved ? (
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
