import { Fragment, useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wand2,
  Loader2,
  ChevronDown,
  CheckCircle2,
  Trash2,
  Plus,
  RefreshCw,
  GripVertical,
  ChevronUp,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { QuestionCardsSkeleton } from '../components/Skeleton';
import {
  createBank,
  discardQuestion,
  errorMessage,
  fetchChapters,
  fetchCombinations,
  generateQuestions,
  planBatches,
  effectiveMarksList,
  ALL_QUESTION_TYPES,
  renumber,
  sortByMarks,
  verifyAnswers,
} from '../lib/api';
import type {
  Subject,
  Grade,
  QuestionType,
  Difficulty,
  Marks,
  MarksByType,
  GenerateFormData,
  Question,
  ChapterInfo,
} from '../types';
import {
  DifficultyBadge,
  TypeBadge,
  ConfirmModal,
  VerificationBadge,
  VerificationNote,
  VerificationWarning,
  isKeyOption,
  MatchTable,
  parseMatch,
  TYPE_LABELS,
} from '../components/ui';
import { FigureImage } from '../components/FigureImage';

const SUBJECTS: Subject[] = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];
const GRADES: Grade[] = [7, 8, 9];
const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard', 'mixed'];
// Fallback used only if GET /generation/combinations can't be reached.
const DEFAULT_MARKS_BY_TYPE: MarksByType = { MCQ: [1], Short: [1, 2, 3], Long: [3, 5], Fill: [1], Match: [3, 5] };

// ============================================================
// Question Card
// ============================================================
interface QuestionCardProps {
  question: Question;
  onDelete: (id: string) => void;
  onRegenerate: (id: string) => void;
  busy?: boolean;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  isFirst: boolean;
  isLast: boolean;
}

function QuestionCard({ question, onDelete, onRegenerate, busy, onMoveUp, onMoveDown, isFirst, isLast }: QuestionCardProps) {
  const [expanded, setExpanded] = useState(false);
  const match = parseMatch(question);

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3">
        {/* Drag handle / order */}
        <div className="flex flex-col items-center gap-1 pt-0.5 shrink-0">
          <GripVertical className="w-4 h-4 text-slate-300" />
          <span className="text-xs font-bold text-slate-400 w-5 text-center">{question.questionNumber}</span>
        </div>

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
          <p className="text-sm font-medium text-slate-900 mb-1 leading-snug whitespace-pre-line">{match ? match.stem : question.text}</p>
          {question.figure && <FigureImage figure={question.figure} className="my-2" />}
          <VerificationWarning question={question} />

          {/* MCQ options, or Column B of a Match question (no single option is "the answer") */}
          {match && <MatchTable rows={match.rows} />}
          {!match && question.options && question.options.length > 0 && (
            <ol className="list-none space-y-1 my-2">
              {question.options.map((opt, i) => (
                <li key={i} className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${isKeyOption(question, opt) ? 'bg-emerald-50 border-emerald-200 text-emerald-800 font-medium' : 'bg-slate-50 border-slate-100 text-slate-600'}`}>
                  <span className="font-semibold shrink-0">{String.fromCharCode(65 + i)}.</span>
                  {opt}
                  {isKeyOption(question, opt) && <CheckCircle2 className="w-3.5 h-3.5 ml-auto shrink-0 text-emerald-500" />}
                </li>
              ))}
            </ol>
          )}

          {/* Answer / Explanation toggle */}
          <button
            onClick={() => setExpanded((p) => !p)}
            className="flex items-center gap-1 text-xs text-indigo-600 hover:text-indigo-800 mt-1 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? 'Hide answer' : 'Show answer & explanation'}
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
              <VerificationNote question={question} />
            </div>
          )}

          {/* Topic tag */}
          {question.topic && <p className="text-xs text-slate-400 mt-2">Topic: {question.topic}</p>}
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1 shrink-0">
          <button
            onClick={() => onMoveUp(question.id)}
            disabled={isFirst}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30 transition-colors"
            aria-label="Move up"
            title="Move up"
          >
            <ChevronUp className="w-4 h-4" />
          </button>
          <button
            onClick={() => onMoveDown(question.id)}
            disabled={isLast}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 disabled:opacity-30 transition-colors"
            aria-label="Move down"
            title="Move down"
          >
            <ChevronDown className="w-4 h-4" />
          </button>
          <button
            onClick={() => onRegenerate(question.id)}
            disabled={busy}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-amber-50 hover:text-amber-600 disabled:opacity-50 transition-colors"
            aria-label="Regenerate question"
            title="Regenerate"
          >
            <RefreshCw className={`w-4 h-4 ${busy ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => onDelete(question.id)}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
            aria-label="Delete question"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Generate Page
// ============================================================
export default function GeneratePage() {
  const { upsertBank, showToast, settings } = useApp();
  const navigate = useNavigate();

  const [form, setForm] = useState<GenerateFormData>({
    subject: 'Science',
    chapter: '',
    grade: 8,
    questionCount: Math.min(settings.defaultQuestionCount, 25),
    questionTypes:
      settings.defaultQuestionType === 'Mixed' ? [...ALL_QUESTION_TYPES] : [settings.defaultQuestionType],
    difficulty: settings.defaultDifficulty,
    marksChoice: {},
  });

  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [chaptersError, setChaptersError] = useState<string | null>(null);
  const [chaptersReload, setChaptersReload] = useState(0);
  const [marksByType, setMarksByType] = useState<MarksByType>(DEFAULT_MARKS_BY_TYPE);
  const [loading, setLoading] = useState(false);
  // Questions created so far in the current run (updates as each batch finishes).
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [busyId, setBusyId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [generated, setGenerated] = useState<Question[]>([]);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [verifying, setVerifying] = useState(false);

  // Which (type, marks) pairs the backend accepts.
  useEffect(() => {
    fetchCombinations()
      .then(setMarksByType)
      .catch(() => setMarksByType(DEFAULT_MARKS_BY_TYPE));
  }, []);

  // Chapters come from the backend syllabus, so names always match what POST /generate accepts.
  useEffect(() => {
    let cancelled = false;
    setChaptersLoading(true);
    setChaptersError(null);
    fetchChapters(form.subject, form.grade)
      .then((rows) => {
        if (cancelled) return;
        setChapters(rows);
        setForm((p) => ({ ...p, chapter: rows.some((r) => r.name === p.chapter) ? p.chapter : rows[0]?.name ?? '' }));
      })
      .catch((err) => {
        if (cancelled) return;
        setChapters([]);
        setChaptersError(errorMessage(err));
      })
      .finally(() => {
        if (!cancelled) setChaptersLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.subject, form.grade, chaptersReload]);

  const setField = <K extends keyof GenerateFormData>(key: K, val: GenerateFormData[K]) =>
    setForm((p) => ({ ...p, [key]: val }));

  const handleSubjectChange = (subject: Subject) => {
    setForm((p) => ({ ...p, subject, chapter: '' }));
    setGenerated([]);
    setSaved(false);
  };

  /** Add or drop a type; at least one always stays selected. */
  const toggleType = (t: QuestionType) =>
    setForm((p) => {
      const has = p.questionTypes.includes(t);
      if (has && p.questionTypes.length === 1) return p;
      return { ...p, questionTypes: has ? p.questionTypes.filter((x) => x !== t) : [...p.questionTypes, t] };
    });

  const allTypesSelected = ALL_QUESTION_TYPES.every((t) => form.questionTypes.includes(t));
  const selectedTypes = ALL_QUESTION_TYPES.filter((t) => form.questionTypes.includes(t));
  /** A saved default marks value only applies when a single type is chosen. */
  const preferredMarks = selectedTypes.length === 1 ? settings.defaultMarks : undefined;
  const marksFor = (t: QuestionType): Marks[] =>
    effectiveMarksList(t, marksByType[t], form.marksChoice[t], preferredMarks);
  /** Select or deselect one marks value for a type; at least one always stays selected. */
  const toggleMarksFor = (t: QuestionType, m: Marks) =>
    setForm((p) => {
      const current = effectiveMarksList(t, marksByType[t], p.marksChoice[t], preferredMarks);
      const has = current.includes(m);
      if (has && current.length === 1) return p;
      const next = has ? current.filter((x) => x !== m) : [...current, m];
      return { ...p, marksChoice: { ...p.marksChoice, [t]: marksByType[t].filter((x) => next.includes(x)) } };
    });

  /** Generate `count` more questions using the current form settings. */
  const generateBatches = async (count: number, refresh: boolean) => {
    const batches = planBatches({ ...form, questionCount: count }, marksByType, settings.defaultMarks);
    const out: Question[] = [];
    setProgress({ done: 0, total: count });
    // The generator can hand back a question it already stored (same text, same
    // id). A paper can't contain one question twice, so keep the first of each.
    const seen = new Set<string>();
    try {
      // Sequential: each call hits the LLM and stores into the shared question pool.
      for (const b of batches) {
        const res = await generateQuestions({
          subject: form.subject,
          chapter: form.chapter,
          grade: form.grade,
          type: b.type,
          marks: b.marks,
          difficulty: b.difficulty,
          count: b.count,
          refresh,
          mixFigures: true,
        });
        for (const q of res.questions) {
          if (seen.has(q.id)) continue;
          seen.add(q.id);
          out.push(q);
        }
        setProgress((p) => ({ ...p, done: out.length }));
      }
    } catch (err) {
      if (out.length === 0) throw err;
      showToast(`Only ${out.length} of ${count} questions were generated: ${errorMessage(err)}`, 'warning');
    }
    return out;
  };

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.chapter) { showToast('Please select a chapter.', 'error'); return; }

    setLoading(true);
    setSaved(false);
    try {
      const questions = await generateBatches(form.questionCount, false);
      setGenerated(renumber(sortByMarks(questions)));
      if (questions.length < form.questionCount) {
        showToast(
          `Generated ${questions.length} unique questions (asked for ${form.questionCount}). ` +
            'Some repeated an existing question.',
          'warning',
        );
      } else {
        showToast(`Generated ${questions.length} questions.`, 'success');
      }
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    setDeleteId(null);
    try {
      await discardQuestion(id);
      setGenerated((prev) => renumber(prev.filter((q) => q.id !== id)));
      showToast('Question deleted.', 'info');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    }
  };

  const handleRegenerate = async (id: string) => {
    const old = generated.find((q) => q.id === id);
    if (!old) return;
    setBusyId(id);
    try {
      // Same type / marks / difficulty as the question being replaced.
      const res = await generateQuestions({
        subject: old.subject,
        chapter: old.chapter,
        grade: old.grade,
        type: old.type,
        marks: old.marks,
        difficulty: old.difficulty,
        count: 1,
        refresh: true,
        // A figure question is replaced by another about the same figure.
        figureIds: old.figure ? [old.figure.id] : undefined,
      });
      const [fresh] = res.questions;
      if (!fresh) throw new Error('No question was returned.');
      if (fresh.id === old.id || generated.some((q) => q.id === fresh.id)) {
        // Discarding `old` here would delete the very question just returned.
        showToast('The generator returned a question that is already in your list. Try again.', 'warning');
        return;
      }
      await discardQuestion(old.id).catch(() => undefined);
      setGenerated((prev) => prev.map((q) => (q.id === id ? { ...fresh, questionNumber: old.questionNumber } : q)));
      showToast('Question regenerated.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setBusyId(null);
    }
  };

  const handleAddQuestion = async () => {
    setLoading(true);
    try {
      const have = new Set(generated.map((q) => q.id));
      const added = (await generateBatches(1, true)).filter((q) => !have.has(q.id));
      if (added.length === 0) {
        showToast('The generator returned a question that is already in your list. Try again.', 'warning');
        return;
      }
      setGenerated((prev) => renumber(sortByMarks([...prev, ...added])));
      showToast('New question added.', 'success');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleMoveUp = (id: string) => {
    setGenerated((prev) => {
      const idx = prev.findIndex((q) => q.id === id);
      if (idx <= 0) return prev;
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return renumber(next);
    });
  };

  const handleMoveDown = (id: string) => {
    setGenerated((prev) => {
      const idx = prev.findIndex((q) => q.id === id);
      if (idx < 0 || idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return renumber(next);
    });
  };

  /** The "Verify answers" button: check the answer keys of the questions on screen. */
  const handleVerify = async () => {
    const pending = generated.filter((q) => q.verificationStatus !== 'verified');
    if (pending.length === 0 || verifying) return;
    setVerifying(true);
    try {
      const res = await verifyAnswers(pending.map((q) => q.id));
      const checked = new Map(res.questions.map((q) => [q.id, q]));
      // Only the check result changes; each card keeps its position, number and marks.
      setGenerated((prev) =>
        prev.map((q) => {
          const c = checked.get(q.id);
          return c ? { ...q, verificationStatus: c.verificationStatus, verificationNote: c.verificationNote } : q;
        }),
      );
      if (res.flagged > 0) {
        showToast(
          `${res.flagged} answer${res.flagged > 1 ? 's look' : ' looks'} wrong. Review ${res.flagged > 1 ? 'them' : 'it'} before saving.`,
          'warning',
        );
      } else if (res.unverified > 0) {
        showToast(`${res.verified} verified, ${res.unverified} could not be checked.`, 'info');
      } else {
        showToast(`All ${res.verified} answers verified.`, 'success');
      }
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setVerifying(false);
    }
  };

  const handleSaveBank = async () => {
    if (generated.length === 0 || saving) return;
    setSaving(true);
    try {
      const bank = await createBank(`${form.subject} – ${form.chapter} (Grade ${form.grade})`, form.subject, [...new Set(generated.map((q) => q.id))]);
      upsertBank(bank);
      setSaved(true);
      showToast('Question bank saved!', 'success');
      navigate('/question-banks');
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const totalMarks = generated.reduce((s, q) => s + q.marks, 0);
  const flaggedCount = generated.filter((q) => q.verificationStatus === 'flagged').length;
  const allVerified = generated.length > 0 && generated.every((q) => q.verificationStatus === 'verified');

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-900">Generate Question Bank</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Configure your question bank and let AI generate syllabus-aligned questions.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form */}
        <form onSubmit={handleGenerate} className="lg:col-span-2 space-y-5">
          {/* Basic Information */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
              Basic Information
            </h3>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Subject *</label>
                <select
                  value={form.subject}
                  onChange={(e) => handleSubjectChange(e.target.value as Subject)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {SUBJECTS.map((s) => <option key={s}>{s}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Chapter *</label>
                {/* Always a dropdown: POST /generate only accepts chapter names from the
                    backend syllabus, so free text just produces "unknown chapter" errors. */}
                <select
                  value={form.chapter}
                  onChange={(e) => setField('chapter', e.target.value)}
                  disabled={chaptersLoading || chapters.length === 0}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50 disabled:text-slate-400"
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
                    <button
                      type="button"
                      onClick={() => setChaptersReload((n) => n + 1)}
                      className="font-medium underline"
                    >
                      Retry
                    </button>
                  </p>
                )}
                {!chaptersLoading && !chaptersError && chapters.length === 0 && (
                  <p className="mt-1.5 text-xs text-slate-500">
                    The backend has no chapters for {form.subject}. Check that SYLLABUS_JSON_PATH points at a
                    syllabus file and restart the backend.
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Grade *</label>
                <div className="flex gap-2">
                  {GRADES.map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setField('grade', g)}
                      className={`flex-1 py-1.5 text-sm rounded-lg border font-medium transition-colors ${form.grade === g ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                    >
                      Grade {g}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Question Configuration */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
              Question Configuration
            </h3>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  Number of Questions: <span className="font-bold text-indigo-600">{form.questionCount}</span>
                </label>
                <input
                  type="range"
                  min={1}
                  max={25}
                  value={form.questionCount}
                  onChange={(e) => setField('questionCount', parseInt(e.target.value))}
                  className="w-full accent-indigo-600"
                />
                <div className="flex justify-between text-xs text-slate-400">
                  <span>1</span><span>25</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  Question Types <span className="font-normal text-slate-400">(pick one or more)</span>
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {ALL_QUESTION_TYPES.map((t) => {
                    const on = form.questionTypes.includes(t);
                    return (
                      <button
                        key={t}
                        type="button"
                        aria-pressed={on}
                        onClick={() => toggleType(t)}
                        className={`py-1.5 text-xs rounded-lg border font-medium transition-colors ${on ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                      >
                        {TYPE_LABELS[t] ?? t}
                      </button>
                    );
                  })}
                  <button
                    type="button"
                    aria-pressed={allTypesSelected}
                    onClick={() => setField('questionTypes', [...ALL_QUESTION_TYPES])}
                    className={`py-1.5 text-xs rounded-lg border font-medium transition-colors ${allTypesSelected ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                  >
                    All types
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Difficulty</label>
                <div className="grid grid-cols-2 gap-2">
                  {DIFFICULTIES.map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => setField('difficulty', d)}
                      className={`py-1.5 text-xs rounded-lg border font-medium capitalize transition-colors ${form.difficulty === d ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Marks & generation options */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
              Marks &amp; Options
            </h3>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Marks per Question <span className="font-normal text-slate-400">(pick one or more)</span></label>
                <div className="space-y-2">
                  {selectedTypes.map((t) => (
                    <div key={t} className="flex items-center gap-2">
                      {selectedTypes.length > 1 && (
                        <span className="w-14 shrink-0 text-xs text-slate-500">{TYPE_LABELS[t] ?? t}</span>
                      )}
                      <div className="flex flex-1 gap-2">
                        {marksByType[t].map((m) => (
                          <button
                            key={m}
                            type="button"
                            aria-pressed={marksFor(t).includes(m)}
                            onClick={() => toggleMarksFor(t, m)}
                            className={`flex-1 py-1.5 text-sm rounded-lg border font-medium transition-colors ${marksFor(t).includes(m) ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                {selectedTypes.length > 1 && (
                  <p className="mt-1.5 text-xs text-slate-400">
                    Questions are spread evenly across the chosen types and marks.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Generate button */}
          <button
            type="submit"
            disabled={loading || chaptersLoading || !form.chapter.trim()}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors shadow-sm"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating… {progress.done}/{progress.total}
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4" />
                Generate Question Bank
              </>
            )}
          </button>
          {!loading && !chaptersLoading && !form.chapter.trim() && (
            <p className="text-xs text-center text-amber-600">
              Choose a chapter to enable generation.
            </p>
          )}
        </form>

        {/* Generated questions panel */}
        <div className="lg:col-span-3 space-y-4">
          {loading && (
            <div role="status" aria-busy="true" className="space-y-4">
              <div className="bg-white rounded-xl border border-slate-200 px-5 py-3 shadow-sm">
                <div className="flex items-center gap-3">
                  <Loader2 className="w-4 h-4 text-indigo-600 animate-spin shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-slate-900">Generating questions…</p>
                    <p className="text-xs text-slate-500 truncate">{form.chapter}</p>
                  </div>
                  <p className="text-sm font-semibold text-slate-900 tabular-nums whitespace-nowrap">
                    {progress.done} <span className="font-normal text-slate-500">of {progress.total} created</span>
                  </p>
                </div>
                <div
                  className="mt-3 h-1.5 bg-slate-100 rounded-full overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={progress.total}
                  aria-valuenow={progress.done}
                  aria-label="Questions created"
                >
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${progress.total ? Math.min(100, Math.max(4, (progress.done / progress.total) * 100)) : 0}%` }}
                  />
                </div>
              </div>
              <QuestionCardsSkeleton count={Math.min(Math.max(progress.total - progress.done, 1), 4)} />
            </div>
          )}

          {!loading && generated.length === 0 && (
            <div className="bg-white rounded-xl border border-dashed border-slate-300 p-12 flex flex-col items-center gap-3 text-center">
              <Wand2 className="w-10 h-10 text-slate-300" />
              <p className="text-sm font-medium text-slate-500">No questions yet</p>
              <p className="text-xs text-slate-400">
                Fill in the form and click "Generate Question Bank" to create questions.
              </p>
            </div>
          )}

          {!loading && generated.length > 0 && (
            <>
              {/* Summary bar */}
              <div className="bg-white rounded-xl border border-slate-200 px-5 py-3 shadow-sm flex flex-wrap items-center gap-4">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-900">
                    {generated.length} questions · {totalMarks} total marks
                  </p>
                  <p className="text-xs text-slate-500">{form.chapter} — Grade {form.grade}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => void handleVerify()}
                    disabled={verifying || allVerified}
                    title="Check each answer key (calculation rules, then an independent AI pass)"
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-lg hover:bg-emerald-100 disabled:opacity-60 transition-colors"
                  >
                    {verifying ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                    {verifying ? 'Verifying…' : allVerified ? 'Answers verified' : 'Verify answers'}
                  </button>
                  <button
                    onClick={handleAddQuestion}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Question
                  </button>
                  <button
                    onClick={handleSaveBank}
                    disabled={saved || saving}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {saved ? 'Saved!' : saving ? 'Saving…' : 'Save Bank'}
                  </button>
                </div>
              </div>

              {flaggedCount > 0 && (
                <div
                  role="alert"
                  className="mb-3 flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900"
                >
                  <TriangleAlert className="w-4 h-4 shrink-0" />
                  <p>
                    {flaggedCount} question{flaggedCount > 1 ? 's have' : ' has'} an answer the check thinks is
                    wrong. Regenerate or delete {flaggedCount > 1 ? 'them' : 'it'} before saving.
                  </p>
                </div>
              )}

              {/* Question cards */}
              <div className="space-y-3">
                {generated.map((q, i) => (
                  <Fragment key={q.id}>
                  {(i === 0 || generated[i - 1].marks !== q.marks) && (
                    <h3 className="pt-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Section — {q.marks}-mark question{q.marks > 1 ? 's' : ''} ({generated.filter((x) => x.marks === q.marks).length})
                    </h3>
                  )}
                  <QuestionCard
                    question={q}
                    onDelete={(id) => setDeleteId(id)}
                    onRegenerate={handleRegenerate}
                    busy={busyId === q.id}
                    onMoveUp={handleMoveUp}
                    onMoveDown={handleMoveDown}
                    isFirst={i === 0}
                    isLast={i === generated.length - 1}
                  />
                  </Fragment>
                ))}
              </div>

              {/* Save again at bottom */}
              <button
                onClick={handleSaveBank}
                disabled={saved || saving}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                <CheckCircle2 className="w-4 h-4" />
                {saved ? 'Saved to Question Banks' : saving ? 'Saving…' : 'Save Question Bank'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Delete confirm */}
      <ConfirmModal
        open={deleteId !== null}
        title="Delete Question"
        message="Are you sure you want to delete this question? This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={() => deleteId && void handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
