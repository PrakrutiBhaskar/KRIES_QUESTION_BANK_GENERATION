import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Plus,
  Download,
  Pencil,
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
} from '../components/ui';
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
  updateQuestion,
} from '../lib/api';

// ============================================================
// Edit Question Modal (inline)
// ============================================================
interface EditModalProps {
  question: Question | null;
  onSave: (q: Question) => Promise<void>;
  onClose: () => void;
}

function EditModal({ question, onSave, onClose }: EditModalProps) {
  const [text, setText] = useState(question?.text ?? '');
  const [answer, setAnswer] = useState(question?.answer ?? '');
  const [explanation, setExplanation] = useState(question?.explanation ?? '');
  const [saving, setSaving] = useState(false);

  if (!question) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave({ ...question, text, answer, explanation });
    } catch {
      // Parent already showed the server's message; keep the modal open.
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-xl overflow-y-auto max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-900">
            Edit Question {question.questionNumber}
          </h3>
          <div className="flex gap-1.5">
            <TypeBadge type={question.type} />
            <DifficultyBadge difficulty={question.difficulty} />
          </div>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Question Text</label>
            <textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Answer / Model Answer</label>
            <textarea
              rows={5}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Explanation</label>
            <textarea
              rows={2}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !text.trim() || !answer.trim()}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {saving ? 'Saving…' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Question Row
// ============================================================
interface QuestionRowProps {
  question: Question;
  onEdit: (q: Question) => void;
  onDelete: (id: string) => void;
}

function QuestionRow({ question, onEdit, onDelete }: QuestionRowProps) {
  const [expanded, setExpanded] = useState(false);

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
          </div>

          {/* Question text */}
          <p className="text-sm font-medium text-slate-900 leading-snug">{question.text}</p>

          {/* MCQ options */}
          {question.options && question.options.length > 0 && (
            <ol className="list-none space-y-1 mt-2">
              {question.options.map((opt, i) => (
                <li
                  key={i}
                  className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${
                    opt === question.answer
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800 font-medium'
                      : 'bg-slate-50 border-slate-100 text-slate-600'
                  }`}
                >
                  <span className="font-semibold">{String.fromCharCode(65 + i)}.</span>
                  {opt}
                  {opt === question.answer && (
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
              </div>
              {question.explanation && (
                <div className="bg-blue-50 border border-blue-100 rounded-lg p-3">
                  <p className="text-xs font-semibold text-blue-700 mb-1">Explanation</p>
                  <p className="text-xs text-blue-800">{question.explanation}</p>
                </div>
              )}
            </div>
          )}

          {question.topic && <p className="text-xs text-slate-400 mt-2">Topic: {question.topic}</p>}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onEdit(question)}
            className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
            aria-label="Edit"
          >
            <Pencil className="w-4 h-4" />
          </button>
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
    fetchChapters(bank.subject)
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
  }, [bank.subject, chaptersReload]);

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
  const [marksByType, setMarksByType] = useState<MarksByType>({ MCQ: [1], Short: [1, 2, 3], Long: [5] });

  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [exporting, setExporting] = useState(false);

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
    return (
      <div className="flex items-center justify-center gap-2 py-24 text-sm text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading question bank…
      </div>
    );
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

  const handleSaveEdit = async (updated: Question) => {
    try {
      const saved = await updateQuestion(updated.id, {
        text: updated.text,
        answer: updated.answer,
        explanation: updated.explanation,
      });
      commit({
        ...bank,
        questions: bank.questions.map((q) =>
          q.id === updated.id ? { ...q, ...saved, questionNumber: q.questionNumber, marks: q.marks, baseMarks: q.baseMarks } : q,
        ),
      });
      setEditingQuestion(null);
      showToast('Question updated.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
      throw err;
    }
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
    commit(await setBankQuestions(bank.id, renumber([...bank.questions, q])));
    showToast('Question added.', 'success');
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await exportBank(bank.id);
      window.open(res.downloadUrl, '_blank', 'noopener');
      showToast('PDF exported.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setExporting(false);
    }
  };

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
              onClick={() => void handleExport()}
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
            {bank.questions.map((q) => (
              <QuestionRow
                key={q.id}
                question={q}
                onEdit={setEditingQuestion}
                onDelete={(qId) => setDeleteId(qId)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Modals */}
      {editingQuestion && (
        <EditModal
          question={editingQuestion}
          onSave={handleSaveEdit}
          onClose={() => setEditingQuestion(null)}
        />
      )}

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
    </div>
  );
}
