import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  Wand2,
  BookOpen,
  Settings,
  LogOut,
  GraduationCap,
  X,
} from 'lucide-react';
import { useApp } from '../hooks/useApp';

interface SidebarProps {
  mobile?: boolean;
  onClose?: () => void;
}

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/generate', icon: Wand2, label: 'Generate' },
  { to: '/question-banks', icon: BookOpen, label: 'Question Banks' },
];

export default function Sidebar({ mobile = false, onClose }: SidebarProps) {
  const { user, logout } = useApp();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <aside
      className={`
        flex flex-col h-full bg-slate-900 text-white
        ${mobile ? 'w-64' : 'w-64'}
      `}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-6 py-5 border-b border-slate-700/50">
        <div className="w-8 h-8 bg-indigo-500 rounded-lg flex items-center justify-center shrink-0">
          <GraduationCap className="w-5 h-5 text-white" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-bold tracking-wide text-white truncate">KRIES</p>
          <p className="text-xs text-slate-400 truncate leading-tight">Question Bank System</p>
        </div>
        {mobile && (
          <button
            onClick={onClose}
            className="ml-auto text-slate-400 hover:text-white transition-colors"
            aria-label="Close sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-widest mb-2 mt-2">
          Navigation
        </p>
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onClose}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User + logout */}
      <div className="px-3 py-4 border-t border-slate-700/50 space-y-1">
        {user && (
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg mb-1">
            <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center shrink-0 text-sm font-bold text-white">
              {user.name.charAt(0)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white truncate">{user.name}</p>
              <p className="text-xs text-slate-400 truncate">{user.role}</p>
            </div>
          </div>
        )}
        <NavLink
          to="/settings"
          onClick={onClose}
          className={({ isActive }) =>
            `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
              isActive
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-400 hover:bg-slate-800 hover:text-white'
            }`
          }
        >
          <Settings className="w-4 h-4 shrink-0" />
          Settings
        </NavLink>
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-800 hover:text-red-400 transition-all duration-150"
        >
          <LogOut className="w-4 h-4 shrink-0" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
