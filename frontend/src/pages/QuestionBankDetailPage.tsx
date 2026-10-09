import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Plus,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Loader2,
} from 'lucide-react';
import { useApp } from '../hooks/useApp';
import type { ChapterInfo, Marks, MarksByType, Question, QuestionBank, QuestionDifficulty, QuestionType } from '../types';
import {
  DifficultyBadge,
  TypeBadge,
  EmptyState,
  ConfirmModal,
  ExportModal,
  VerificationBadge,
  VerificationNote,
  VerificationWarning,
  isKeyOption,
  MatchTable,
  parseMatch,
} from '../components/ui';
import { BankDetailSkeleton } from '../components/Skeleton';
import { FigureImage } from '../components/FigureImage';
import { formatDate } from '../lib/utils';
import {
  errorMessage,
  exportBank,
  fetchBank,
  fetchChapters,
  fetchCombinations,
  generateQuestions,
  renumber,
  setBankQuestions,
} from '../lib/api';

// ============================================================
// Question Row
// ============================================================
interface QuestionRowProps {
  question: Question;
  onDelete: (id: string) => void;
}

function QuestionRow({ question, onDelete }: QuestionRowProps) {
  const [expanded, setExpanded] = useState(false);
  const match = parseMatch(question);

  return (
    <div className="border border-slate-200 rounded-xl bg-white overflow-hidden">
      <div className="flex items-start gap-4 p-4">
        {/* Number */}
        <span className="w-7 h-7 rounded-full bg-indigo-50 text-indigo-700 text-xs font-bold flex items-center justify-center shrink-0 mt-0.5">
          {question.questionNumber}
        </span>

        <div className="flex-1 min-w-0">
          {/* Badges */}
          <div className="flex flex-wrap gap-1.5 mb-2">
            <TypeBadge type={question.type} />
            <DifficultyBadge difficulty={question.difficulty} />
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
              {question.marks} mark{question.marks > 1 ? 's' : ''}
            </span>
            <VerificationBadge question={question} />
          </div>

          {/* Question text */}
          <p className="text-sm font-medium text-slate-900 leading-snug whitespace-pre-line">{match ? match.stem : question.text}</p>
          <VerificationWarning question={question} />

          {/* Diagram printed with the question */}
          {question.figure && <FigureImage figure={question.figure} className="mt-2" />}

          {/* MCQ options */}
          {match && <MatchTable rows={match.rows} />}
          {!match && question.options && question.options.length > 0 && (
            <ol className="list-none space-y-1 mt-2">
              {question.options.map((opt, i) => (
                <li
                  key={i}
                  className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${
                    isKeyOption(question, opt)
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800 font-medium'
                      : 'bg-slate-50 border-slate-100 text-slate-600'
                  }`}
                >
                  <span className="font-semibold">{String.fromCharCode(65 + i)}.</span>
                  {opt}
                  {isKeyOption(question, opt) && (
                    <CheckCircle2 className="w-3.5 h-3.5 ml-auto shrink-0 text-emerald-500" />
                  )}
                </li>
              ))}
            </ol>
          )}

          {/* Expand button */}
          <button
            onClick={() => setExpanded((p) => !p)}
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 mt-2 transition-colors"
          >
            {expanded ? (
              <><ChevronUp className="w-3.5 h-3.5" /> Hide answer</>
            ) : (
              <><ChevronDown className="w-3.5 h-3.5" /> Show answer & explanation</>
            )}
          </button>

          {expanded && (
            <div className="mt-2 space-y-2">
              <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-3">
                <p className="text-xs font-semibold text-emerald-700 mb-1">Answer</p>
                <p className="text-xs text-emerald-800 whitespace-pre-wrap">{question.answer}</p>
                {/* Diagram printed in the answer key: the answer figure, else the question's own */}
                {(question.answerFigure ?? question.figure) && (
                  <FigureImage figure={(question.answerFigure ?? question.figure)!} className="mt-2" />
                )}
              </div>
              {question.explanation && (
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-700 mb-1">Explanation</p>
                  <p className="text-xs text-blue-800">{question.explanation}</p>
                </div>
              )}
              <VerificationNote question={question} />
            </div>
          )}

          {question.topic && <p className="text-xs text-slate-400 mt-2">Topic: {question.topic}</p>}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onDelete(question.id)}
            className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
            aria-label="Remove from bank"
            title="Remove from bank"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Add Question Modal — generates one more question with the AI and adds it
// ============================================================
interface AddQuestionModalProps {
  bank: QuestionBank;
  marksByType: MarksByType;
  onAdd: (q: Question) => Promise<void>;
  onClose: () => void;
}

function AddQuestionModal({ bank, marksByType, onAdd, onClose }: AddQuestionModalProps) {
  const { showToast } = useApp();
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(true);
  const [chaptersError, setChaptersError] = useState<string | null>(null);
  const [chaptersReload, setChaptersReload] = useState(0);
  const [chapter, setChapter] = useState(bank.chapter);
  const [type, setType] = useState<QuestionType>('Short');
  const [marks, setMarks] = useState<Marks>(2);
  const [difficulty, setDifficulty] = useState<QuestionDifficulty>('medium');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setChaptersLoading(true);
    setChaptersError(null);
    fetchChapters(bank.subject, bank.grade)
      .then((rows) => {
        if (cancelled) return;
        setChapters(rows);
        setChapter((c) => (rows.some((r) => r.name === c) ? c : rows[0]?.name ?? ''));
      })
      .catch((err) => {
        if (cancelled) return;
        setChapters([]);
        setChapter('');
        setChaptersError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setChaptersLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [bank.subject, bank.grade, chaptersReload]);

  const handleType = (t: QuestionType) => {
    setType(t);
    const allowed = marksByType[t];
    if (!allowed.includes(marks)) setMarks((allowed.includes(2) ? 2 : allowed[0]) as Marks);
  };

  const handleAdd = async () => {
    if (!chapter) return;
    setBusy(true);
    try {
      const res = await generateQuestions({
        subject: bank.subject,
        chapter,
        grade: bank.grade,
        type,
        marks,
        difficulty,
        count: 1,
        // Force a new question rather than one that may already be in this bank.
        refresh: true,
      });
      const [q] = res.questions;
      if (!q) throw new Error('No question was returned.');
      await onAdd(q);
      onClose();
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const selectClass =
    'w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-y-auto max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-semibold text-slate-900">Generate &amp; Add a Question</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            The AI writes one new {bank.subject} question for Grade {bank.grade} and adds it to this bank.
          </p>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Chapter</label>
            <select
              value={chapter}
              onChange={(e) => setChapter(e.target.value)}
              disabled={chaptersLoading || chapters.length === 0}
              className={`${selectClass} disabled:bg-slate-50 disabled:text-slate-400`}
            >
              {chaptersLoading && <option value="">Loading chapters…</option>}
              {!chaptersLoading && chapters.length === 0 && (
                <option value="">{chaptersError ? 'Could not load chapters' : 'No chapters available'}</option>
              )}
              {chapters.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
            {!chaptersLoading && chaptersError && (
              <p className="mt-1.5 text-xs text-red-600">
                {chaptersError}{' '}
                <button type="button" onClick={() => setChaptersReload((n) => n + 1)} className="font-medium underline">
                  Retry
                </button>
              </p>
            )}
          </div>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Type</label>
              <select value={type} onChange={(e) => handleType(e.target.value as QuestionType)} className={selectClass}>
                <option value="MCQ">MCQ</option>
                <option value="Short">Short</option>
                <option value="Long">Long</option>
                <option value="Fill">Fill in the blank</option>
                <option value="Match">Match the following</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Marks</label>
              <select value={marks} onChange={(e) => setMarks(parseInt(e.target.value) as Marks)} className={selectClass}>
                {marksByType[type].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Difficulty</label>
              <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as QuestionDifficulty)} className={selectClass}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
          </div>
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors">Cancel</button>
          <button onClick={handleAdd} disabled={busy || chaptersLoading || !chapter} className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors">
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {busy ? 'Generating…' : 'Generate & Add'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Question Bank Detail Page
// ============================================================
export default function QuestionBankDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { upsertBank, showToast } = useApp();
  const navigate = useNavigate();

  const [bank, setBank] = useState<QuestionBank | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [marksByType, setMarksByType] = useState<MarksByType>({ MCQ: [1], Short: [1, 2, 3], Long: [5], Fill: [1], Match: [3, 5] });

  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetchBank(id ?? '')
      .then((b) => { if (!cancelled) setBank(b); })
      .catch((err) => { if (!cancelled) setLoadError(errorMessage(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => {
    fetchCombinations().then(setMarksByType).catch(() => undefined);
  }, []);

  if (loading) {
    return <BankDetailSkeleton />;
  }

  if (!bank) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <BookOpen className="w-12 h-12 text-slate-300" />
        <p className="text-slate-500 font-medium">{loadError ?? 'Question bank not found.'}</p>
        <Link to="/question-banks" className="text-indigo-600 text-sm hover:underline">
          Back to Question Banks
        </Link>
      </div>
    );
  }

  const commit = (next: QuestionBank) => {
    setBank(next);
    upsertBank(next);
  };

  const handleRemove = async (qId: string) => {
    setDeleteId(null);
    try {
      // Removing from the bank replaces the paper's list; the question stays in the pool.
      commit(await setBankQuestions(bank.id, bank.questions.filter((q) => q.id !== qId)));
      showToast('Question removed from bank.', 'info');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    }
  };

  const handleAddQuestion = async (q: Question) => {
    // A paper can't hold the same question twice (the generator may return one it already stored).
    if (bank.questions.some((x) => x.id === q.id)) {
      showToast('That question is already in this bank. Try again for a different one.', 'warning');
      return;
    }
    commit(await setBankQuestions(bank.id, renumber([...bank.questions, q])));
    showToast('Question added.', 'success');
  };

  const handleExport = async (includeAnswerKey: boolean) => {
    setExporting(true);
    try {
      const res = await exportBank(bank.id, { includeAnswerKey });
      window.open(res.downloadUrl, '_blank', 'noopener');
      setExportOpen(false);
      showToast(includeAnswerKey ? 'PDF exported with answer key.' : 'PDF exported without answer key.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setExporting(false);
    }
  };

  // Marks per section, for the section headings (empty for papers built by hand).
  const sectionMarks = new Map<string, number>();
  for (const q of bank.questions) {
    if (q.section) sectionMarks.set(q.section, (sectionMarks.get(q.section) ?? 0) + q.marks);
  }

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      {/* Back */}
      <button
        onClick={() => navigate('/question-banks')}
        className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-900 transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Question Banks
      </button>

      {/* Header card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <DifficultyBadge difficulty={bank.difficulty} />
              <span className="text-xs text-slate-400">Grade {bank.grade}</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 leading-tight">{bank.name}</h2>
            <p className="text-sm text-slate-500 mt-1">{bank.subject} — {bank.chapter}</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setExportOpen(true)}
              disabled={exporting || bank.questions.length === 0}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors"
            >
              {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              Export PDF
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mt-5 pt-5 border-t border-slate-100">
          {[
            { label: 'Questions', value: bank.questionCount },
            { label: 'Total Marks', value: bank.totalMarks },
            { label: 'Created', value: formatDate(bank.createdAt) },
          ].map(({ label, value }) => (
            <div key={label}>
              <p className="text-xs text-slate-500 font-medium">{label}</p>
              <p className="text-sm font-semibold text-slate-900 mt-0.5">{value}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Questions */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-slate-900">
            Questions ({bank.questions.length})
          </h3>
          <button
            onClick={() => setAddingQuestion(true)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Generate Question
          </button>
        </div>

        {bank.questions.length === 0 ? (
          <EmptyState
            icon={<BookOpen className="w-7 h-7" />}
            title="No questions yet"
            description="Generate a question to add to this bank."
            action={
              <button
                onClick={() => setAddingQuestion(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Generate Question
              </button>
            }
          />
        ) : (
          <div className="space-y-3">
            {bank.questions.map((q, i) => (
              <div key={q.id} className="space-y-3">
                {/* Blueprint papers keep their sections; show a heading where one starts. */}
                {q.section && q.section !== bank.questions[i - 1]?.section && (
                  <div className="flex items-baseline justify-between gap-3 pt-2 border-b border-slate-200 pb-1.5">
                    <h4 className="text-sm font-bold text-slate-900">{q.section}</h4>
                    <span className="text-xs font-medium text-slate-500">
                      {sectionMarks.get(q.section)} marks
                    </span>
                  </div>
                )}
                <QuestionRow
                  question={q}
                  onDelete={(qId) => setDeleteId(qId)}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {addingQuestion && (
        <AddQuestionModal
          bank={bank}
          marksByType={marksByType}
          onAdd={handleAddQuestion}
          onClose={() => setAddingQuestion(false)}
        />
      )}

      <ConfirmModal
        open={deleteId !== null}
        title="Remove Question"
        message="Remove this question from the bank? It stays in the question pool and can be reused."
        confirmLabel="Remove"
        danger
        onConfirm={() => deleteId && void handleRemove(deleteId)}
        onCancel={() => setDeleteId(null)}
      />

      <ExportModal
        open={exportOpen}
        name={bank.name}
        exporting={exporting}
        onConfirm={(includeAnswerKey) => void handleExport(includeAnswerKey)}
        onCancel={() => setExportOpen(false)}
      />
    </div>
  );
}
