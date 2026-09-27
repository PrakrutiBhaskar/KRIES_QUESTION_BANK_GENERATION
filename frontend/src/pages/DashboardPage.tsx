import { Link } from 'react-router-dom';
import {
  Wand2,
} from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { DifficultyBadge, StatusBadge, SubjectDot } from '../components/ui';

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function DashboardPage() {
  const { user, questionBanks } = useApp();
  const recentBanks = [...questionBanks].slice(0, 5);

  return (
    <div className="space-y-6">
      {/* Welcome */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">
            {getGreeting()}, {user?.name?.split(' ')[0] ?? 'Teacher'} 👋
          </h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Here's what's happening with your question banks.
          </p>
        </div>
        <Link
          to="/generate"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          <Wand2 className="w-4 h-4" />
          Generate New
        </Link>
      </div>

      {/* Recent question banks */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <h3 className="text-sm font-semibold text-slate-900">Recent Question Banks</h3>
          <Link to="/question-banks" className="text-xs text-indigo-600 hover:underline font-medium">
            View all
          </Link>
        </div>
        <div className="overflow-x-auto scrollbar-thin">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50">
                <th className="text-left px-5 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap">Name</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap">Subject</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap">Questions</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap">Difficulty</th>
                <th className="text-left px-4 py-2.5 text-xs font-semibold text-slate-500 whitespace-nowrap">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recentBanks.map((bank) => (
                <tr key={bank.id} className="hover:bg-slate-50 transition-colors">
                  <td className="px-5 py-3">
                    <Link
                      to={`/question-banks/${bank.id}`}
                      className="font-medium text-slate-900 hover:text-indigo-600 transition-colors line-clamp-1"
                    >
                      {bank.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1.5">
                      <SubjectDot subject={bank.subject} />
                      <span className="text-slate-600 whitespace-nowrap">{bank.subject}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{bank.questionCount}</td>
                  <td className="px-4 py-3">
                    <DifficultyBadge difficulty={bank.difficulty} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={bank.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
