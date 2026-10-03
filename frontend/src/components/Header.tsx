import { Menu } from 'lucide-react';
import { useLocation } from 'react-router-dom';

const PAGE_TITLES: Record<string, { title: string; description: string }> = {
  '/dashboard': { title: 'Dashboard', description: 'Overview of your question bank activity' },
  '/generate': { title: 'Generate', description: 'Create new question banks using AI' },
  '/question-papers': { title: 'Question Papers', description: 'Build a board-style paper from a blueprint' },
  '/question-banks': { title: 'Question Banks', description: 'Browse and manage your question banks' },
  '/figure-library': { title: 'Figure Library', description: 'Diagrams teachers can build questions and answer keys from' },
  '/settings': { title: 'Settings', description: 'Configure your preferences' },
};

interface HeaderProps {
  onMenuClick: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const location = useLocation();

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
    </header>
  );
}
