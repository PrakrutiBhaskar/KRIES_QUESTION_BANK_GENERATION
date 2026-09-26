import { Link } from 'react-router-dom';
import {
  BookOpen,
  Wand2,
  BarChart3,
  TrendingUp,
  Clock,
  CheckCircle2,
  PlusCircle,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { useApp } from '../hooks/useApp';
import { ANALYTICS_DATA, RECENT_ACTIVITY } from '../data/analytics';
import { StatCard, DifficultyBadge, StatusBadge, SubjectDot } from '../components/ui';
import { formatDistanceToNow } from '../lib/utils';


const ACTIVITY_ICONS: Record<string, React.ReactNode> = {
  generate: <Wand2 className="w-3.5 h-3.5" />,
  edit: <CheckCircle2 className="w-3.5 h-3.5" />,
  delete: <Clock className="w-3.5 h-3.5" />,
  export: <BarChart3 className="w-3.5 h-3.5" />,
  create: <PlusCircle className="w-3.5 h-3.5" />,
};

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

export default function DashboardPage() {
  const { user, questionBanks } = useApp();
  const recentBanks = [...questionBanks].slice(0, 5);

  const stats = [
    {
      label: 'Question Banks',
      value: questionBanks.length,
      icon: <BookOpen className="w-5 h-5" />,
      trend: '2 added this week',
      trendUp: true,
      color: 'bg-indigo-50 text-indigo-600',
    },
    {
      label: 'Total Questions',
      value: questionBanks.reduce((s, b) => s + b.questionCount, 0),
      icon: <CheckCircle2 className="w-5 h-5" />,
      trend: '14 generated today',
      trendUp: true,
      color: 'bg-emerald-50 text-emerald-600',
    },
    {
      label: 'Subjects Covered',
      value: new Set(questionBanks.map((b) => b.subject)).size,
      icon: <TrendingUp className="w-5 h-5" />,
      color: 'bg-amber-50 text-amber-600',
    },
    {
      label: 'Recent Generations',
      value: ANALYTICS_DATA.recentGenerations,
      icon: <Wand2 className="w-5 h-5" />,
      trend: 'in the last 7 days',
      trendUp: true,
      color: 'bg-violet-50 text-violet-600',
    },
  ];

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

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats.map((s) => (
          <StatCard key={s.label} {...s} />
        ))}
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Area chart */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions Generated Over Time</h3>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={ANALYTICS_DATA.questionsOverTime} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
              <defs>
                <linearGradient id="colorQ" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#6366f1" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
              />
              <Area type="monotone" dataKey="count" stroke="#6366f1" strokeWidth={2} fill="url(#colorQ)" name="Questions" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Pie chart — by difficulty */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Difficulty Distribution</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={ANALYTICS_DATA.byDifficulty}
                dataKey="count"
                nameKey="difficulty"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={75}
                paddingAngle={3}
              >
                {ANALYTICS_DATA.byDifficulty.map((_, i) => (
                  <Cell key={i} fill={['#10b981', '#f59e0b', '#f43f5e'][i]} />
                ))}
              </Pie>
              <Legend
                formatter={(value) => <span className="text-xs text-slate-600">{value}</span>}
              />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bottom row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Recent question banks */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
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

        {/* Recent activity */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100">
            <h3 className="text-sm font-semibold text-slate-900">Recent Activity</h3>
          </div>
          <div className="divide-y divide-slate-100">
            {RECENT_ACTIVITY.slice(0, 6).map((act) => (
              <div key={act.id} className="flex items-start gap-3 px-5 py-3">
                <div className="w-6 h-6 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 mt-0.5">
                  {ACTIVITY_ICONS[act.type]}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-slate-700 leading-snug">{act.description}</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {formatDistanceToNow(act.timestamp)}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {[
          {
            to: '/generate',
            icon: <Wand2 className="w-5 h-5" />,
            title: 'Generate Question Bank',
            desc: 'Create questions for any subject and chapter.',
            color: 'indigo',
          },
          {
            to: '/question-banks',
            icon: <BookOpen className="w-5 h-5" />,
            title: 'Browse Question Banks',
            desc: 'Search, filter, and manage your existing banks.',
            color: 'emerald',
          },
          {
            to: '/analytics',
            icon: <BarChart3 className="w-5 h-5" />,
            title: 'View Analytics',
            desc: 'Understand your question bank usage and trends.',
            color: 'violet',
          },
        ].map(({ to, icon, title, desc, color }) => (
          <Link
            key={to}
            to={to}
            className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:shadow-md hover:border-slate-300 transition-all group"
          >
            <div className={`w-10 h-10 rounded-lg bg-${color}-50 text-${color}-600 flex items-center justify-center mb-3 group-hover:scale-105 transition-transform`}>
              {icon}
            </div>
            <h4 className="text-sm font-semibold text-slate-900 mb-1">{title}</h4>
            <p className="text-xs text-slate-500">{desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
