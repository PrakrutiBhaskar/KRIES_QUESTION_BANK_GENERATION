import { useState } from 'react';
import { Menu, Bell } from 'lucide-react';
import { useLocation } from 'react-router-dom';

const PAGE_TITLES: Record<string, { title: string; description: string }> = {
  '/dashboard': { title: 'Dashboard', description: 'Overview of your question bank activity' },
  '/generate': { title: 'Generate', description: 'Create new question banks using AI' },
  '/question-banks': { title: 'Question Banks', description: 'Browse and manage your question banks' },
  '/settings': { title: 'Settings', description: 'Configure your preferences' },
};

interface HeaderProps {
  onMenuClick: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();
  const [showNotifications, setShowNotifications] = useState(false);

  const basePath = '/' + location.pathname.split('/')[1];
  const page = PAGE_TITLES[basePath] ?? { title: 'KRIES', description: 'Question Bank System' };

  return (
    <header className="bg-white border-b border-slate-200 px-4 sm:px-6 py-3 flex items-center gap-4">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
        aria-label="Open navigation menu"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-base font-semibold text-slate-900 truncate">{page.title}</h1>
        <p className="text-xs text-slate-500 hidden sm:block truncate">{page.description}</p>
      </div>

      {/* Notifications */}
      <div className="relative">
        <button
          onClick={() => setShowNotifications((p) => !p)}
          className="relative p-2 rounded-lg text-slate-500 hover:bg-slate-100 transition-colors"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
        </button>
        {showNotifications && (
          <>
            <div
              className="fixed inset-0 z-40"
              onClick={() => setShowNotifications(false)}
            />
            <div className="absolute right-0 top-11 z-50 bg-white rounded-xl border border-slate-200 shadow-xl w-72 p-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide px-2 mb-2">Notifications</p>
              {[
                { text: 'Science question bank generated successfully', time: '2 min ago' },
                { text: '5 questions from Math bank updated', time: '1 hr ago' },
                { text: 'Question bank "Gravitation" archived', time: '2 days ago' },
              ].map((n, i) => (
                <div key={i} className="flex gap-3 px-2 py-2 rounded-lg hover:bg-slate-50 cursor-pointer">
                  <div className="w-2 h-2 bg-indigo-500 rounded-full mt-1.5 shrink-0" />
                  <div>
                    <p className="text-xs text-slate-700">{n.text}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{n.time}</p>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </header>
  );
}
