import { useEffect, useState } from 'react';
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
} from 'recharts';
import { StatCard } from '../components/ui';
import { BookOpen, FileQuestion, GraduationCap, Loader2 } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { errorMessage, fetchAllQuestions } from '../lib/api';
import { buildAnalytics } from '../lib/analytics';
import type { AnalyticsData } from '../types';

const SUBJECT_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#8b5cf6', '#f43f5e'];
const DIFF_COLORS = ['#10b981', '#f59e0b', '#f43f5e'];
const TYPE_COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#14b8a6', '#f59e0b'];
const MARKS_COLORS = ['#6366f1', '#10b981', '#f59e0b', '#f43f5e'];
const TOOLTIP_STYLE = { borderRadius: 8, border: '1px solid #e2e8f0', fontSize: 12 };

export default function AnalyticsPage() {
  const { questionBanks } = useApp();
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchAllQuestions()
      .then(({ questions, total }) => {
        if (!cancelled) setData(buildAnalytics(questions, total, questionBanks.length));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err));
      });
    return () => {
      cancelled = true;
    };
  }, [questionBanks.length]);

  if (error) return <p className="py-24 text-center text-sm text-slate-500">{error}</p>;
  if (!data) {
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading analytics…
      </div>
    );
  }

  const stats = [
    { label: 'Total Questions', value: data.totalQuestions, icon: <FileQuestion className="w-5 h-5" />, color: 'bg-indigo-50 text-indigo-600' },
    { label: 'Question Banks', value: data.totalQuestionBanks, icon: <BookOpen className="w-5 h-5" />, color: 'bg-emerald-50 text-emerald-600' },
    { label: 'Subjects Covered', value: data.subjectsCovered, icon: <GraduationCap className="w-5 h-5" />, color: 'bg-amber-50 text-amber-600' },
  ];

  const card = 'bg-white rounded-xl border border-slate-200 p-5 shadow-sm';

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Analytics</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          A breakdown of every stored question.
          {data.truncated && ' (Showing the most recent questions only.)'}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {stats.map((s) => <StatCard key={s.label} {...s} />)}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className={card}>
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions by Subject</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={data.bySubject} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#f1f5f9" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="subject" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} width={85} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[0, 4, 4, 0]} name="Questions">
                {data.bySubject.map((_, i) => <Cell key={i} fill={SUBJECT_COLORS[i % SUBJECT_COLORS.length]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className={card}>
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Difficulty Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={data.byDifficulty} dataKey="count" nameKey="difficulty" cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={4}>
                {data.byDifficulty.map((_, i) => <Cell key={i} fill={DIFF_COLORS[i]} />)}
              </Pie>
              <Legend formatter={(value) => <span className="text-xs text-slate-600 capitalize">{value}</span>} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className={card}>
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Question Types</h3>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={data.byType} dataKey="count" nameKey="type" cx="50%" cy="50%" outerRadius={70} paddingAngle={3}>
                {data.byType.map((_, i) => <Cell key={i} fill={TYPE_COLORS[i]} />)}
              </Pie>
              <Legend formatter={(value) => <span className="text-xs text-slate-600">{value}</span>} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className={card}>
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions by Grade</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.byGrade} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="grade" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} name="Questions" />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className={card}>
          <h3 className="text-sm font-semibold text-slate-900 mb-4">Questions by Marks</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={data.byMarks} margin={{ top: 0, right: 0, left: -25, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="marks" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <YAxis allowDecimals={false} tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]} name="Questions">
                {data.byMarks.map((_, i) => <Cell key={i} fill={MARKS_COLORS[i]} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
