import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import {
  ArrowLeft,
  BookOpen,
  Plus,
  Download,
  Trash2,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  Check,
  Database,
  FilePlus,
  Loader2,
  Pencil,
  Search,
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
  fetchPoolQuestions,
  generateQuestions,
  insertByMarks,
  renumber,
  setBankQuestions,
  updateQuestion,
  copyQuestion,
  createQuestion,
  ApiError,
} from '../lib/api';
import type { ExportFormat, QuestionEdit } from '../lib/api';

// ============================================================
// Question Row
// ============================================================
interface QuestionRowProps {
  question: Question;
  editing: boolean;
  onEdit: (question: Question) => void;
  onDelete: (id: string) => void;
}

function QuestionRow({ question, editing, onEdit, onDelete }: QuestionRowProps) {
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

        {/* Actions (edit mode only) */}
        {editing && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={() => onEdit(question)}
              className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
              aria-label="Edit question and answer"
              title="Edit question and answer"
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
        )}
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

/** What the answer key must look like for these marks (checked by the server when saving). */
function answerShapeHint(type: QuestionType, marks: number): string | null {
  if (type === 'MCQ' || type === 'Match') return null;
  if (type === 'Fill') return 'A word or a short phrase.';
  switch (marks) {
    case 1:
      return '1 mark: one word or one short line (up to 15 words), without an explanation.';
    case 2:
      return '2 marks: list more points than marks, ideally 5 short points (any 2 earn full marks). Number them 1. 2. 3.';
    case 3:
      return '3 marks: list more points than marks, ideally 6 distinct points or steps (any 3 earn full marks). Number them 1. 2. 3.';
    case 5:
      return '5 marks: list more points than marks, ideally 8 points or steps (any 5 earn full marks) and at least 60 words. Number them.';
    default:
      return null;
  }
}

// ============================================================
// Edit Question Modal — change the wording, options, answer and explanation
// ============================================================
interface EditQuestionModalProps {
  question: Question;
  onSave: (id: string, changes: QuestionEdit) => Promise<void>;
  onClose: () => void;
}

function EditQuestionModal({ question, onSave, onClose }: EditQuestionModalProps) {
  const isMcq = question.type === 'MCQ';
  const hasOptions = !!question.options && question.options.length > 0;

  const [text, setText] = useState(question.text);
  const [options, setOptions] = useState<string[]>(question.options ?? []);
  // For an MCQ the key is picked from the options, so it stays valid when an option is reworded.
  const [correct, setCorrect] = useState(() =>
    isMcq ? (question.options ?? []).findIndex((o) => o.trim() === question.answer.trim()) : -1,
  );
  const [answer, setAnswer] = useState(question.answer);
  const [explanation, setExplanation] = useState(question.explanation);
  const [difficulty, setDifficulty] = useState<QuestionDifficulty>(question.difficulty);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finalAnswer = isMcq ? (options[correct] ?? '') : answer;

  const handleSave = async () => {
    const problem =
      !text.trim() ? 'The question text cannot be empty.'
      : isMcq && options.some((o) => !o.trim()) ? 'Every option needs text.'
      : isMcq && correct < 0 ? 'Choose which option is the correct answer.'
      : !finalAnswer.trim() ? 'The answer cannot be empty.'
      : null;
    if (problem) {
      setError(problem);
      return;
    }

    // Send only what changed.
    const changes: QuestionEdit = {};
    if (text.trim() !== question.text) changes.text = text.trim();
    if (hasOptions && JSON.stringify(options.map((o) => o.trim())) !== JSON.stringify(question.options)) {
      changes.options = options.map((o) => o.trim());
    }
    if (finalAnswer.trim() !== question.answer) changes.answer = finalAnswer.trim();
    if (explanation.trim() !== question.explanation) changes.explanation = explanation.trim();
    if (difficulty !== question.difficulty) changes.difficulty = difficulty;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await onSave(question.id, changes);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const fieldClass =
    'w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Edit question">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100 shrink-0">
          <h3 className="text-base font-semibold text-slate-900">Edit question {question.questionNumber}</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            If you generated this question, the change applies everywhere it is used. Otherwise it is saved as your
            own copy in this paper. Either way the answer key is marked as not checked.
          </p>
        </div>

        <div className="px-6 py-4 space-y-4 overflow-y-auto flex-1">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Question</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={question.type === 'Match' ? 6 : 3}
              className={fieldClass}
            />
            {question.type === 'Match' && (
              <p className="mt-1 text-xs text-slate-400">Keep the numbered lines (1. 2. 3.) so the table still shows.</p>
            )}
          </div>

          {hasOptions && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                {isMcq ? 'Options' : 'Column B options'}
              </label>
              <div className="space-y-2">
                {options.map((opt, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-500 w-4">{String.fromCharCode(65 + i)}.</span>
                    <input
                      value={opt}
                      onChange={(e) => setOptions((prev) => prev.map((o, j) => (j === i ? e.target.value : o)))}
                      className={fieldClass}
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {isMcq && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Correct answer</label>
              <select
                value={correct}
                onChange={(e) => setCorrect(parseInt(e.target.value))}
                className={fieldClass}
              >
                {correct < 0 && <option value={-1}>Choose the correct option…</option>}
                {options.map((opt, i) => (
                  <option key={i} value={i}>
                    {String.fromCharCode(65 + i)}. {opt}
                  </option>
                ))}
              </select>
            </div>
          )}

          {!isMcq && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Answer</label>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={question.type === 'Long' ? 6 : 3}
                className={fieldClass}
              />
              {answerShapeHint(question.type, question.baseMarks ?? question.marks) && (
                <p className="mt-1 text-xs text-slate-500">
                  {answerShapeHint(question.type, question.baseMarks ?? question.marks)}
                </p>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">Explanation</label>
              <textarea
                value={explanation}
                onChange={(e) => setExplanation(e.target.value)}
                rows={2}
                className={fieldClass}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Difficulty</label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as QuestionDifficulty)}
                className={fieldClass}
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
          </div>

        </div>

        {error && (
          <p role="alert" className="px-6 py-2 text-sm text-red-700 bg-red-50 border-t border-red-100 shrink-0">
            {error}
          </p>
        )}

        <div className="px-6 py-4 border-t border-slate-100 shrink-0 flex justify-end gap-3">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors">Cancel</button>
          <button
            onClick={() => void handleSave()}
            disabled={busy}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Write Question Modal — add a question, answer and explanation of your own
// ============================================================
// Match the Following is left out: it needs numbered pairs and a letter key, which is
// easier to get right by generating one and then editing it.
const WRITABLE_TYPES: { value: QuestionType; label: string }[] = [
  { value: 'MCQ', label: 'MCQ' },
  { value: 'Short', label: 'Short answer' },
  { value: 'Long', label: 'Long answer' },
  { value: 'Fill', label: 'Fill in the blank' },
];

interface WriteQuestionModalProps {
  bank: QuestionBank;
  marksByType: MarksByType;
  onAdd: (q: Question) => Promise<void>;
  onClose: () => void;
}

function WriteQuestionModal({ bank, marksByType, onAdd, onClose }: WriteQuestionModalProps) {
  const [grade, setGrade] = useState<number>(bank.questions.length > 0 ? bank.grade : 8);
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(true);
  const [chapter, setChapter] = useState(bank.chapter);
  const [type, setType] = useState<QuestionType>('Short');
  const [marks, setMarks] = useState<number>(2);
  const [difficulty, setDifficulty] = useState<QuestionDifficulty>('medium');
  const [text, setText] = useState('');
  const [options, setOptions] = useState<string[]>(['', '', '', '']);
  const [correct, setCorrect] = useState(-1);
  const [answer, setAnswer] = useState('');
  const [explanation, setExplanation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isMcq = type === 'MCQ';

  useEffect(() => {
    let cancelled = false;
    setChaptersLoading(true);
    fetchChapters(bank.subject, grade)
      .then((rows) => {
        if (cancelled) return;
        setChapters(rows);
        setChapter((c) => (rows.some((r) => r.name === c) ? c : rows[0]?.name ?? ''));
      })
      .catch(() => { if (!cancelled) setChapters([]); })
      .finally(() => { if (!cancelled) setChaptersLoading(false); });
    return () => { cancelled = true; };
  }, [bank.subject, grade]);

  const handleType = (t: QuestionType) => {
    setType(t);
    const allowed = marksByType[t] ?? [1];
    if (!allowed.includes(marks as Marks)) setMarks(allowed.includes(2) ? 2 : allowed[0]);
  };

  const handleSave = async () => {
    const finalAnswer = isMcq ? (options[correct] ?? '') : answer;
    const problem =
      !chapter ? 'Choose a chapter.'
      : !text.trim() ? 'Write the question.'
      : isMcq && options.some((o) => !o.trim()) ? 'Fill in all four options.'
      : isMcq && correct < 0 ? 'Choose the correct option.'
      : !finalAnswer.trim() ? 'Write the answer.'
      : isMcq && !explanation.trim() ? 'An MCQ needs a one-line explanation.'
      : null;
    if (problem) {
      setError(problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const q = await createQuestion({
        subject: bank.subject,
        chapter,
        type,
        grade,
        text: text.trim(),
        options: isMcq ? options.map((o) => o.trim()) : undefined,
        answer: finalAnswer.trim(),
        explanation: explanation.trim(),
        marks,
        difficulty,
      });
      await onAdd(q);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const fieldClass =
    'w-full px-3 py-2 text-sm rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
  const smallClass =
    'w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Write your own question">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100 shrink-0">
          <h3 className="text-base font-semibold text-slate-900">Write your own question</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Add a {bank.subject} question with its answer and explanation. It is saved as not checked, and placed in
            the section for its marks.
          </p>
        </div>

        <div className="px-6 py-4 space-y-4 overflow-y-auto flex-1">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Grade</label>
              <select value={grade} onChange={(e) => setGrade(parseInt(e.target.value))} className={smallClass}>
                {[7, 8, 9].map((g) => <option key={g} value={g}>Grade {g}</option>)}
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">Chapter</label>
              <select
                value={chapter}
                onChange={(e) => setChapter(e.target.value)}
                disabled={chaptersLoading || chapters.length === 0}
                className={`${smallClass} disabled:bg-slate-50 disabled:text-slate-400`}
              >
                {chaptersLoading && <option value="">Loading chapters…</option>}
                {!chaptersLoading && chapters.length === 0 && <option value="">No chapters available</option>}
                {chapters.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Difficulty</label>
              <select value={difficulty} onChange={(e) => setDifficulty(e.target.value as QuestionDifficulty)} className={smallClass}>
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Type</label>
              <select value={type} onChange={(e) => handleType(e.target.value as QuestionType)} className={smallClass}>
                {WRITABLE_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Marks</label>
              <select value={marks} onChange={(e) => setMarks(parseInt(e.target.value))} className={smallClass}>
                {(marksByType[type] ?? [1]).map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Question</label>
            <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} className={fieldClass} />
            {type === 'Fill' && (
              <p className="mt-1 text-xs text-slate-400">Use one run of underscores for the blank, for example: The powerhouse of the cell is the _____.</p>
            )}
          </div>

          {isMcq && (
            <>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Options</label>
                <div className="space-y-2">
                  {options.map((opt, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-500 w-4">{String.fromCharCode(65 + i)}.</span>
                      <input
                        value={opt}
                        onChange={(e) => setOptions((prev) => prev.map((o, j) => (j === i ? e.target.value : o)))}
                        className={fieldClass}
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Correct answer</label>
                <select value={correct} onChange={(e) => setCorrect(parseInt(e.target.value))} className={fieldClass}>
                  <option value={-1}>Choose the correct option…</option>
                  {options.map((opt, i) => (
                    <option key={i} value={i}>{String.fromCharCode(65 + i)}. {opt}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          {!isMcq && (
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Answer</label>
              <textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={type === 'Long' ? 6 : 3} className={fieldClass} />
              {answerShapeHint(type, marks) && (
                <p className="mt-1 text-xs text-slate-500">{answerShapeHint(type, marks)}</p>
              )}
            </div>
          )}

          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">
              Explanation{isMcq ? ' (one line)' : ' (optional)'}
            </label>
            <textarea value={explanation} onChange={(e) => setExplanation(e.target.value)} rows={2} className={fieldClass} />
          </div>

        </div>

        {error && (
          <p role="alert" className="px-6 py-2 text-sm text-red-700 bg-red-50 border-t border-red-100 shrink-0">
            {error}
          </p>
        )}

        <div className="px-6 py-4 border-t border-slate-100 shrink-0 flex justify-end gap-3">
          <button onClick={onClose} disabled={busy} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors">Cancel</button>
          <button
            onClick={() => void handleSave()}
            disabled={busy || chaptersLoading}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
          >
            {busy && <Loader2 className="w-4 h-4 animate-spin" />}
            {busy ? 'Saving…' : 'Add question'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Pool Picker Modal — add questions that are already stored (no AI call)
// ============================================================
const POOL_PAGE_SIZE = 10;

interface PoolPickerModalProps {
  bank: QuestionBank;
  onAdd: (questions: Question[]) => Promise<void>;
  onClose: () => void;
}

function PoolPickerModal({ bank, onAdd, onClose }: PoolPickerModalProps) {
  const { showToast } = useApp();
  // An empty bank has no grade of its own, so start with every grade.
  const [grade, setGrade] = useState<number | ''>(bank.questions.length > 0 ? bank.grade : '');
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chapter, setChapter] = useState('');
  const [type, setType] = useState<QuestionType | ''>('');
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const [rows, setRows] = useState<Question[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  // Ticked questions are kept across pages and filter changes.
  const [picked, setPicked] = useState<Map<string, Question>>(new Map());
  const [busy, setBusy] = useState(false);

  const inBank = useMemo(() => new Set(bank.questions.map((q) => q.id)), [bank.questions]);

  useEffect(() => {
    let cancelled = false;
    setChapter('');
    fetchChapters(bank.subject, grade === '' ? undefined : grade)
      .then((c) => { if (!cancelled) setChapters(c); })
      .catch(() => { if (!cancelled) setChapters([]); });
    return () => { cancelled = true; };
  }, [bank.subject, grade]);

  // Wait for a pause in typing before searching.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(searchInput);
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    fetchPoolQuestions({
      subject: bank.subject,
      grade: grade === '' ? undefined : grade,
      chapter: chapter || undefined,
      type: type || undefined,
      search,
      page,
      pageSize: POOL_PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return;
        setRows(res.questions);
        setTotal(res.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setRows([]);
        setTotal(0);
        setLoadError(errorMessage(err));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [bank.subject, grade, chapter, type, search, page, reload]);

  const toggle = (q: Question) =>
    setPicked((prev) => {
      const next = new Map(prev);
      if (next.has(q.id)) next.delete(q.id);
      else next.set(q.id, q);
      return next;
    });

  const handleAdd = async () => {
    if (picked.size === 0) return;
    setBusy(true);
    try {
      await onAdd([...picked.values()]);
      onClose();
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.max(1, Math.ceil(total / POOL_PAGE_SIZE));
  const selectClass =
    'w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Add from stored questions">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={busy ? undefined : onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-2xl flex flex-col max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100 shrink-0">
          <h3 className="text-base font-semibold text-slate-900">Add from stored questions</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Pick existing {bank.subject} questions to add to this bank. Nothing new is generated.
          </p>
        </div>

        {/* Filters */}
        <div className="px-6 pt-4 space-y-3 shrink-0">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search question text, answer or topic"
              className="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <select
              value={grade}
              onChange={(e) => { setGrade(e.target.value === '' ? '' : parseInt(e.target.value)); setPage(1); }}
              className={selectClass}
              aria-label="Grade"
            >
              <option value="">Any grade</option>
              {[7, 8, 9].map((g) => <option key={g} value={g}>Grade {g}</option>)}
            </select>
            <select
              value={chapter}
              onChange={(e) => { setChapter(e.target.value); setPage(1); }}
              className={selectClass}
              aria-label="Chapter"
            >
              <option value="">All chapters</option>
              {chapters.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
            <select
              value={type}
              onChange={(e) => { setType(e.target.value as QuestionType | ''); setPage(1); }}
              className={selectClass}
              aria-label="Question type"
            >
              <option value="">All types</option>
              <option value="MCQ">MCQ</option>
              <option value="Short">Short</option>
              <option value="Long">Long</option>
              <option value="Fill">Fill in the blank</option>
              <option value="Match">Match the following</option>
            </select>
          </div>
        </div>

        {/* Results */}
        <div className="px-6 py-4 overflow-y-auto flex-1 min-h-[12rem]">
          {loading && (
            <p className="flex items-center gap-2 text-xs text-slate-500">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading questions…
            </p>
          )}
          {!loading && loadError && (
            <p className="text-xs text-red-600">
              {loadError}{' '}
              <button type="button" onClick={() => setReload((n) => n + 1)} className="font-medium underline">Retry</button>
            </p>
          )}
          {!loading && !loadError && rows.length === 0 && (
            <p className="text-xs text-slate-500">No stored questions match these filters.</p>
          )}
          {!loading && !loadError && rows.length > 0 && (
            <ul className="space-y-2">
              {rows.map((q) => {
                const already = inBank.has(q.id);
                const on = picked.has(q.id);
                return (
                  <li key={q.id}>
                    <label
                      className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                        already
                          ? 'border-slate-100 bg-slate-50 opacity-60 cursor-not-allowed'
                          : on
                            ? 'border-indigo-300 bg-indigo-50/50 cursor-pointer'
                            : 'border-slate-200 hover:border-indigo-200 cursor-pointer'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={on || already}
                        disabled={already}
                        onChange={() => toggle(q)}
                        className="mt-0.5 accent-indigo-600"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap gap-1.5 mb-1.5">
                          <TypeBadge type={q.type} />
                          <DifficultyBadge difficulty={q.difficulty} />
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
                            {q.marks} mark{q.marks > 1 ? 's' : ''}
                          </span>
                          {already && <span className="text-xs font-medium text-slate-500">Already in this bank</span>}
                        </div>
                        <p className="text-xs text-slate-800 leading-snug whitespace-pre-line line-clamp-3">{q.text}</p>
                        <p className="text-xs text-slate-400 mt-1">Grade {q.grade} · {q.chapter}</p>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Paging + actions */}
        <div className="px-6 py-3 border-t border-slate-100 shrink-0 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <button
              type="button"
              onClick={() => setPage((n) => Math.max(1, n - 1))}
              disabled={page <= 1 || loading}
              className="px-2 py-1 rounded-md border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
            >
              Prev
            </button>
            <span>Page {page} of {pages} · {total} found</span>
            <button
              type="button"
              onClick={() => setPage((n) => Math.min(pages, n + 1))}
              disabled={page >= pages || loading}
              className="px-2 py-1 rounded-md border border-slate-300 disabled:opacity-40 hover:bg-slate-50"
            >
              Next
            </button>
          </div>
          <div className="flex gap-2">
            <button onClick={onClose} disabled={busy} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors">Cancel</button>
            <button
              onClick={() => void handleAdd()}
              disabled={busy || picked.size === 0}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
            >
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Add selected{picked.size > 0 ? ` (${picked.size})` : ''}
            </button>
          </div>
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
  const { upsertBank, showToast, user } = useApp();
  const canWrite = user?.role !== 'Student';
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [bank, setBank] = useState<QuestionBank | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [marksByType, setMarksByType] = useState<MarksByType>({ MCQ: [1], Short: [1, 2, 3], Long: [5], Fill: [1], Match: [3, 5] });

  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);
  const [pickingFromPool, setPickingFromPool] = useState(false);
  const [writingQuestion, setWritingQuestion] = useState(false);
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  // Edit mode (add / remove questions). The bank list links here with ?edit=1.
  const [editing, setEditing] = useState(searchParams.get('edit') === '1');
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
    const placed = insertByMarks(bank.questions, [q]);
    commit(await setBankQuestions(bank.id, renumber(placed)));
    const where = placed.find((x) => x.id === q.id)?.section;
    showToast(
      where ? `Question added to ${where}.` : `Question added with the ${q.marks}-mark questions.`,
      'success',
    );
  };

  const handleAddFromPool = async (picked: Question[]) => {
    const fresh = picked.filter((q) => !bank.questions.some((x) => x.id === q.id));
    if (fresh.length === 0) {
      showToast('Those questions are already in this bank.', 'warning');
      return;
    }
    commit(await setBankQuestions(bank.id, renumber(insertByMarks(bank.questions, fresh))));
    showToast(`${fresh.length} question${fresh.length > 1 ? 's' : ''} added.`, 'success');
  };

  const handleSaveQuestion = async (id: string, changes: QuestionEdit) => {
    let updated: Question;
    let copied = false;
    try {
      updated = await updateQuestion(id, changes);
    } catch (err) {
      // Only the person who generated a question may change it. For anyone else the
      // edit goes to their own copy, which then replaces the original in this paper.
      if (!(err instanceof ApiError) || err.status !== 403) throw err;
      const copy = await copyQuestion(id);
      updated = await updateQuestion(copy.id, changes);
      copied = true;
    }
    const questions = bank.questions.map((q) =>
      q.id === id
        ? {
            ...updated,
            // The paper's own numbering, marks and section are not part of the question edit.
            questionNumber: q.questionNumber,
            marks: q.marks,
            baseMarks: q.baseMarks,
            section: q.section,
          }
        : q,
    );
    if (copied) {
      // Save the swap so the paper now points at the edited copy.
      commit(await setBankQuestions(bank.id, questions));
      showToast(
        'Saved as your own copy in this paper. The original question is unchanged for everyone else.',
        'success',
      );
      return;
    }
    const difficulties = new Set(questions.map((q) => q.difficulty));
    commit({
      ...bank,
      questions,
      difficulty: difficulties.size === 1 ? [...difficulties][0] : 'mixed',
    });
    showToast('Question updated. Its answer key is now marked as not checked.', 'success');
  };

  const toggleEditing = () => {
    const next = !editing;
    setEditing(next);
    setSearchParams(next ? { edit: '1' } : {}, { replace: true });
  };

  const handleExport = async (includeAnswerKey: boolean, format: ExportFormat) => {
    setExporting(true);
    try {
      const res = await exportBank(bank.id, { includeAnswerKey, format });
      window.open(res.downloadUrl, '_blank', 'noopener');
      setExportOpen(false);
      const label = format === 'docx' ? 'Word file' : 'PDF';
      showToast(`${label} exported ${includeAnswerKey ? 'with' : 'without'} answer key.`, 'success');
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
              onClick={toggleEditing}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                editing
                  ? 'text-white bg-indigo-600 hover:bg-indigo-700'
                  : 'text-indigo-700 bg-indigo-50 hover:bg-indigo-100'
              }`}
            >
              {editing ? <Check className="w-4 h-4" /> : <Pencil className="w-4 h-4" />}
              {editing ? 'Done' : 'Edit'}
            </button>
            <button
              onClick={() => setExportOpen(true)}
              disabled={exporting || bank.questions.length === 0}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 disabled:opacity-60 transition-colors"
            >
              {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              Export
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
          {editing && (
            <div className="flex flex-wrap justify-end gap-2">
              <button
                onClick={() => setPickingFromPool(true)}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
              >
                <Database className="w-4 h-4" />
                Add from stored
              </button>
              {canWrite && (
                <button
                  onClick={() => setWritingQuestion(true)}
                  className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
                >
                  <FilePlus className="w-4 h-4" />
                  Write your own
                </button>
              )}
              <button
                onClick={() => setAddingQuestion(true)}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Generate Question
              </button>
            </div>
          )}
        </div>

        {editing && (
          <p className="mb-4 px-3 py-2 text-xs text-indigo-800 bg-indigo-50 border border-indigo-100 rounded-lg">
            Editing: use the pencil to change a question or its answer, the bin to remove it, or add more with the
            buttons above (write your own, add from stored, or generate). Each change is saved straight away. Click Done when you are finished.
          </p>
        )}

        {bank.questions.length === 0 ? (
          <EmptyState
            icon={<BookOpen className="w-7 h-7" />}
            title="No questions yet"
            description={editing ? 'Write a question, add stored ones, or generate a new one.' : 'Click Edit to add questions to this bank.'}
            action={
              editing ? (
                <div className="flex flex-wrap justify-center gap-2">
                  <button
                    onClick={() => setPickingFromPool(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-700 text-sm font-semibold rounded-lg hover:bg-indigo-100 transition-colors"
                  >
                    <Database className="w-4 h-4" />
                    Add from stored
                  </button>
                  {canWrite && (
                    <button
                      onClick={() => setWritingQuestion(true)}
                      className="flex items-center gap-2 px-4 py-2 bg-indigo-50 text-indigo-700 text-sm font-semibold rounded-lg hover:bg-indigo-100 transition-colors"
                    >
                      <FilePlus className="w-4 h-4" />
                      Write your own
                    </button>
                  )}
                  <button
                    onClick={() => setAddingQuestion(true)}
                    className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    Generate Question
                  </button>
                </div>
              ) : (
                <button
                  onClick={toggleEditing}
                  className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  <Pencil className="w-4 h-4" />
                  Edit
                </button>
              )
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
                  editing={editing}
                  onEdit={setEditingQuestion}
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

      {writingQuestion && (
        <WriteQuestionModal
          bank={bank}
          marksByType={marksByType}
          onAdd={handleAddQuestion}
          onClose={() => setWritingQuestion(false)}
        />
      )}

      {editingQuestion && (
        <EditQuestionModal
          question={editingQuestion}
          onSave={handleSaveQuestion}
          onClose={() => setEditingQuestion(null)}
        />
      )}

      {pickingFromPool && (
        <PoolPickerModal
          bank={bank}
          onAdd={handleAddFromPool}
          onClose={() => setPickingFromPool(false)}
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
        onConfirm={(includeAnswerKey, format) => void handleExport(includeAnswerKey, format)}
        onCancel={() => setExportOpen(false)}
      />
    </div>
  );
}
