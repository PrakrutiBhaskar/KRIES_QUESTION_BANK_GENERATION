import { useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
  AreaChart,
  Area,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
} from 'recharts';
import { ANALYTICS_DATA } from '../data/analytics';
import { StatCard } from '../components/ui';
import { BookOpen, FileQuestion, GraduationCap, Wand2 } from 'lucide-react';

const SUBJECT_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#8b5cf6', '#f43f5e'];
const DIFF_COLORS = ['#10b981', '#f59e0b', '#f43f5e'];
const TYPE_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4'];
const BLOOMS_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e', '#8b5cf6', '#ec4899'];

const DATE_RANGES = ['Last 7 days', 'Last 30 days', 'Last 3 months', 'All time'] as const;
type DateRange = (typeof DATE_RANGES)[number];

export default function AnalyticsPage() {
  const [dateRange, setDateRange] = useState<DateRange>('Last 3 months');

  const stats = [
    {
      label: 'Total Questions',
      value: ANALYTICS_DATA.totalQuestions,
      icon: <FileQuestion className="w-5 h-5" />,
      trend: '23 added this week',
      trendUp: true,
      color: 'bg-indigo-50 text-indigo-600',
    },
    {
      label: 'Question Banks',
      value: ANALYTICS_DATA.totalQuestionBanks,
      icon: <BookOpen className="w-5 h-5" />,
      trend: '2 new this week',
      trendUp: true,
      color: 'bg-emerald-50 text-emerald-600',
    },
    {
      label: 'Subjects Covered',
      value: ANALYTICS_DATA.totalSubjects,
      icon: <GraduationCap className="w-5 h-5" />,
      color: 'bg-amber-50 text-amber-600',
    },
    {
      label: 'AI Generations',
      value: ANALYTICS_DATA.recentGenerations,
      icon: <Wand2 className="w-5 h-5" />,
      trend: 'in last 7 days',
      trendUp: true,
      color: 'bg-violet-50 text-violet-600',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header + date range */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <h2 className="text-xl font-bold text-slate-900">Analytics</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            Insights into your question bank generation activity.
          </p>
        </div>
        <div className="flex items-center gap-1 bg-white border border-slate-200 rounded-lg p-1 shadow-sm">
          {DATE_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setDateRange(r)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                dateRange === r
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-600 hover:bg-slate-50'
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {stats.map((s) => <StatCard key={s.label} {...s} />)}
      </div>

      {/* Questions over time */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions Generated Over Time</h3>
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={ANALYTICS_DATA.questionsOverTime} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="colorArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#6366f1" stopOpacity={0.25} />
                <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#6366f1"
              strokeWidth={2.5}
              fill="url(#colorArea)"
              name="Questions"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* 2-column row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* By subject — bar chart */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions by Subject</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={ANALYTICS_DATA.bySubject}
              layout="vertical"
              margin={{ top: 0, right: 20, left: 10, bottom: 0 }}
            >
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis
                type="category"
                dataKey="subject"
                tick={{ fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={85}
              />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Questions">
                {ANALYTICS_DATA.bySubject.map((_, i) => (
                  <Cell key={i} fill={SUBJECT_COLORS[i % SUBJECT_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* By difficulty — pie */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Difficulty Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie
                data={ANALYTICS_DATA.byDifficulty}
                dataKey="count"
                nameKey="difficulty"
                cx="50%"
                cy="50%"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={4}
              >
                {ANALYTICS_DATA.byDifficulty.map((_, i) => (
                  <Cell key={i} fill={DIFF_COLORS[i]} />
                ))}
              </Pie>
              <Legend
                formatter={(value) => <span className="text-xs text-slate-600 capitalize">{value}</span>}
              />
              <Tooltip
                formatter={(value, name) => [value, String(name).charAt(0).toUpperCase() + String(name).slice(1)]}
                contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 3-column row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* By type */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Question Types</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie
                data={ANALYTICS_DATA.byType}
                dataKey="count"
                nameKey="type"
                cx="50%"
                cy="50%"
                outerRadius={70}
                paddingAngle={3}
              >
                {ANALYTICS_DATA.byType.map((_, i) => (
                  <Cell key={i} fill={TYPE_COLORS[i]} />
                ))}
              </Pie>
              <Legend formatter={(value) => <span className="text-xs text-slate-600">{value}</span>} />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* By grade */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions by Grade</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={ANALYTICS_DATA.byGrade} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="grade" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Questions" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Bloom's radar */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Bloom's Taxonomy</h3>
          <ResponsiveContainer width="100%" height={200}>
            <RadarChart data={ANALYTICS_DATA.byBlooms} cx="50%" cy="50%" outerRadius={70}>
              <PolarGrid stroke="#f1f5f9" />
              <PolarAngleAxis dataKey="level" tick={{ fontSize: 10 }} />
              <PolarRadiusAxis tick={{ fontSize: 9 }} />
              <Radar name="Questions" dataKey="count" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
              <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Bloom's bar breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <h3 className="text-sm font-semibold text-slate-900 mb-4">Bloom's Taxonomy Distribution</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={ANALYTICS_DATA.byBlooms} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="level" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={{ borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 }} />
            <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Questions">
              {ANALYTICS_DATA.byBlooms.map((_, i) => (
                <Cell key={i} fill={BLOOMS_COLORS[i % BLOOMS_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
