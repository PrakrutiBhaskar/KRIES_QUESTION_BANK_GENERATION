import { useState, useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Search,
  Filter,
  LayoutGrid,
  LayoutList,
  Plus,
  Eye,
  Copy,
  Trash2,
  Download,
  BookOpen,
} from 'lucide-react';
import { useApp } from '../hooks/useApp';
import type { Subject, Difficulty, QuestionBankStatus } from '../types';
import { DifficultyBadge, StatusBadge, SubjectDot, EmptyState, ConfirmModal } from '../components/ui';
import { formatDate, generateId } from '../lib/utils';

const SUBJECTS: Array<Subject | 'All'> = ['All', 'Math', 'Science', 'Social Science', 'English', 'Kannada'];
const DIFFICULTIES: Array<Difficulty | 'All'> = ['All', 'easy', 'medium', 'hard', 'mixed'];
const STATUSES: Array<QuestionBankStatus | 'All'> = ['All', 'published', 'draft', 'archived'];

export default function QuestionBanksPage() {
  const { questionBanks, deleteQuestionBank, addQuestionBank, showToast } = useApp();
  const navigate = useNavigate();

  const [search, setSearch] = useState('');
  const [subjectFilter, setSubjectFilter] = useState<Subject | 'All'>('All');
  const [difficultyFilter, setDifficultyFilter] = useState<Difficulty | 'All'>('All');
  const [statusFilter, setStatusFilter] = useState<QuestionBankStatus | 'All'>('All');
  const [view, setView] = useState<'grid' | 'list'>('grid');
  const [sortBy, setSortBy] = useState<'newest' | 'oldest' | 'name' | 'questions'>('newest');
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);

  const filtered = useMemo(() => {
    let banks = [...questionBanks];

    if (search) {
      const q = search.toLowerCase();
      banks = banks.filter(
        (b) =>
          b.name.toLowerCase().includes(q) ||
          b.subject.toLowerCase().includes(q) ||
          b.chapter.toLowerCase().includes(q),
      );
    }
    if (subjectFilter !== 'All') banks = banks.filter((b) => b.subject === subjectFilter);
    if (difficultyFilter !== 'All') banks = banks.filter((b) => b.difficulty === difficultyFilter);
    if (statusFilter !== 'All') banks = banks.filter((b) => b.status === statusFilter);

    banks.sort((a, b) => {
      if (sortBy === 'newest') return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
      if (sortBy === 'oldest') return new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
      if (sortBy === 'name') return a.name.localeCompare(b.name);
      if (sortBy === 'questions') return b.questionCount - a.questionCount;
      return 0;
    });

    return banks;
  }, [questionBanks, search, subjectFilter, difficultyFilter, statusFilter, sortBy]);

  const handleDelete = (id: string) => {
    deleteQuestionBank(id);
    setDeleteId(null);
    showToast('Question bank deleted.', 'info');
  };

  const handleDuplicate = (id: string) => {
    const bank = questionBanks.find((b) => b.id === id);
    if (!bank) return;
    addQuestionBank({
      ...bank,
      id: generateId(),
      name: `${bank.name} (Copy)`,
      status: 'draft',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    });
    showToast('Question bank duplicated.', 'success');
  };

  const handleExport = (name: string) => {
    showToast(`Exporting "${name}" as PDF… (demo only)`, 'info');
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex-1">
          <h2 className="text-xl font-bold text-slate-900">Question Banks</h2>
          <p className="text-sm text-slate-500 mt-0.5">
            {questionBanks.length} question bank{questionBanks.length !== 1 ? 's' : ''} total
          </p>
        </div>
        <Link
          to="/generate"
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold rounded-lg transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4" />
          New Bank
        </Link>
      </div>

      {/* Search + filter bar */}
      <div className="bg-white rounded-xl border border-slate-200 p-3 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 flex-1">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              type="search"
              placeholder="Search by name, subject, or chapter…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none w-full"
            />
          </div>

          {/* Sort */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="px-3 py-2 text-sm border border-slate-200 rounded-lg bg-white text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
            <option value="name">A–Z</option>
            <option value="questions">Most Questions</option>
          </select>

          {/* Filter toggle */}
          <button
            onClick={() => setShowFilters((p) => !p)}
            className={`flex items-center gap-2 px-3 py-2 text-sm border rounded-lg transition-colors ${showFilters ? 'bg-indigo-50 border-indigo-200 text-indigo-700' : 'border-slate-200 text-slate-700 hover:bg-slate-50'}`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {(subjectFilter !== 'All' || difficultyFilter !== 'All' || statusFilter !== 'All') && (
              <span className="w-2 h-2 bg-indigo-500 rounded-full" />
            )}
          </button>

          {/* View toggle */}
          <div className="flex border border-slate-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setView('grid')}
              className={`p-2 transition-colors ${view === 'grid' ? 'bg-indigo-50 text-indigo-600' : 'text-slate-400 hover:bg-slate-50'}`}
              aria-label="Grid view"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView('list')}
              className={`p-2 transition-colors ${view === 'list' ? 'bg-indigo-50 text-indigo-600' : 'text-slate-400 hover:bg-slate-50'}`}
              aria-label="List view"
            >
              <LayoutList className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Filters */}
        {showFilters && (
          <div className="flex flex-wrap gap-3 pt-2 border-t border-slate-100">
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Subject</label>
              <div className="flex flex-wrap gap-1.5">
                {SUBJECTS.map((s) => (
                  <button
                    key={s}
                    onClick={() => setSubjectFilter(s as Subject | 'All')}
                    className={`px-2.5 py-1 text-xs rounded-full border font-medium transition-colors ${subjectFilter === s ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Difficulty</label>
              <div className="flex flex-wrap gap-1.5">
                {DIFFICULTIES.map((d) => (
                  <button
                    key={d}
                    onClick={() => setDifficultyFilter(d as Difficulty | 'All')}
                    className={`px-2.5 py-1 text-xs rounded-full border font-medium capitalize transition-colors ${difficultyFilter === d ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}
                  >
                    {d}
                  </button>
                ))}
              </div>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-500 mb-1 block">Status</label>
              <div className="flex flex-wrap gap-1.5">
                {STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s as QuestionBankStatus | 'All')}
                    className={`px-2.5 py-1 text-xs rounded-full border font-medium capitalize transition-colors ${statusFilter === s ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-600 border-slate-200 hover:border-indigo-300'}`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <EmptyState
          icon={<BookOpen className="w-7 h-7" />}
          title="No question banks found"
          description={search ? 'Try adjusting your search or filters.' : 'Create your first question bank to get started.'}
          action={
            <Link
              to="/generate"
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
            >
              <Plus className="w-4 h-4" />
              Generate New Bank
            </Link>
          }
        />
      ) : view === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((bank) => (
            <div key={bank.id} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col gap-3">
              {/* Title + status */}
              <div className="flex items-start gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 mb-1">
                    <SubjectDot subject={bank.subject} />
                    <span className="text-xs text-slate-500 font-medium">{bank.subject}</span>
                  </div>
                  <h3 className="text-sm font-semibold text-slate-900 leading-snug line-clamp-2">{bank.name}</h3>
                </div>
                <StatusBadge status={bank.status} />
              </div>

              <p className="text-xs text-slate-500 line-clamp-1">{bank.chapter}</p>

              {/* Meta */}
              <div className="flex flex-wrap gap-1.5">
                <DifficultyBadge difficulty={bank.difficulty} />
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  Grade {bank.grade}
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  {bank.questionCount} Qs
                </span>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  {bank.totalMarks} marks
                </span>
              </div>

              <p className="text-xs text-slate-400">Created {formatDate(bank.createdAt)}</p>

              {/* Actions */}
              <div className="flex items-center gap-1.5 pt-1 border-t border-slate-100">
                <button
                  onClick={() => navigate(`/question-banks/${bank.id}`)}
                  className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
                >
                  <Eye className="w-3.5 h-3.5" />
                  View
                </button>
                <button
                  onClick={() => handleDuplicate(bank.id)}
                  className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
                  aria-label="Duplicate"
                  title="Duplicate"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => handleExport(bank.name)}
                  className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors"
                  aria-label="Export PDF"
                  title="Export PDF"
                >
                  <Download className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={() => setDeleteId(bank.id)}
                  className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors ml-auto"
                  aria-label="Delete"
                  title="Delete"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* List view */
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto scrollbar-thin">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-100">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-slate-500">Name</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Subject</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Grade</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Questions</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Difficulty</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Status</th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-slate-500">Created</th>
                  <th className="px-4 py-3 text-xs font-semibold text-slate-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filtered.map((bank) => (
                  <tr key={bank.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-5 py-3">
                      <p className="font-medium text-slate-900 line-clamp-1 max-w-[200px]">{bank.name}</p>
                      <p className="text-xs text-slate-400 truncate max-w-[200px]">{bank.chapter}</p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <SubjectDot subject={bank.subject} />
                        <span className="text-slate-600 whitespace-nowrap">{bank.subject}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">Grade {bank.grade}</td>
                    <td className="px-4 py-3 text-slate-600">{bank.questionCount}</td>
                    <td className="px-4 py-3"><DifficultyBadge difficulty={bank.difficulty} /></td>
                    <td className="px-4 py-3"><StatusBadge status={bank.status} /></td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap text-xs">{formatDate(bank.createdAt)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button onClick={() => navigate(`/question-banks/${bank.id}`)} className="p-1.5 text-indigo-500 hover:bg-indigo-50 rounded transition-colors" title="View"><Eye className="w-4 h-4" /></button>
                        <button onClick={() => handleDuplicate(bank.id)} className="p-1.5 text-slate-400 hover:bg-slate-100 rounded transition-colors" title="Duplicate"><Copy className="w-4 h-4" /></button>
                        <button onClick={() => handleExport(bank.name)} className="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded transition-colors" title="Export"><Download className="w-4 h-4" /></button>
                        <button onClick={() => setDeleteId(bank.id)} className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors" title="Delete"><Trash2 className="w-4 h-4" /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmModal
        open={deleteId !== null}
        title="Delete Question Bank"
        message="Are you sure you want to delete this question bank? All associated questions will be removed."
        confirmLabel="Delete"
        danger
        onConfirm={() => deleteId && handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
