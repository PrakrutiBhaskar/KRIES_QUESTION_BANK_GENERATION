import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertTriangle, FileText, Loader2, Plus, Scale, Trash2, Wand2 } from 'lucide-react';
import { useApp } from '../hooks/useApp';
import { ChapterListSkeleton } from '../components/Skeleton';
import {
  buildBlueprintPaper,
  errorMessage,
  fetchChapters,
  fetchCombinations,
  previewBlueprint,
} from '../lib/api';
import type { BlueprintProgress } from '../lib/api';
import type {
  BlueprintInput,
  BlueprintPlan,
  BlueprintSection,
  ChapterInfo,
  Difficulty,
  Grade,
  Marks,
  MarksByType,
  QuestionType,
  Subject,
} from '../types';

const SUBJECTS: Subject[] = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];
const GRADES: Grade[] = [7, 8, 9];
const TYPE_LABEL: Record<QuestionType, string> = {
  MCQ: 'MCQ',
  Short: 'Short answer',
  Long: 'Long answer',
  Fill: 'Fill in the blank',
  Match: 'Match the following',
};
const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard', 'mixed'];
// Used only if GET /generation/combinations can't be reached.
const DEFAULT_MARKS_BY_TYPE: MarksByType = { MCQ: [1], Short: [1, 2, 3], Long: [5], Fill: [1], Match: [3, 5] };
// Limits enforced by the backend (schemas/requests.py); checked here so the
// user sees the problem next to the field instead of after a failed request.
const MAX_QUESTIONS = 100;
const MAX_CHAPTERS = 12;
const MAX_SECTIONS = 8;

interface SectionRow extends BlueprintSection {
  key: number;
}

const inputClass =
  'w-full px-2.5 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
const cardClass = 'bg-white rounded-xl border border-slate-200 p-5 shadow-sm';
const cardTitleClass = 'text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100';

/** Whole-number percentages that add up to exactly 100, earlier chapters taking the remainder. */
function splitEvenly(names: string[]): Record<string, number> {
  if (names.length === 0) return {};
  const base = Math.floor(100 / names.length);
  const extra = 100 - base * names.length;
  return Object.fromEntries(names.map((n, i) => [n, base + (i < extra ? 1 : 0)]));
}

function sectionQuestions(s: BlueprintSection): number | null {
  return s.totalMarks > 0 && s.totalMarks % s.marksPerQuestion === 0 ? s.totalMarks / s.marksPerQuestion : null;
}

export default function QuestionPapersPage() {
  const { upsertBank, showToast, settings } = useApp();
  const navigate = useNavigate();

  const [subject, setSubject] = useState<Subject>('Science');
  const [grade, setGrade] = useState<Grade>(8);
  const [title, setTitle] = useState('');
  const [fresh, setFresh] = useState(false);
  const [marksByType, setMarksByType] = useState<MarksByType>(DEFAULT_MARKS_BY_TYPE);

  // Chapters available for the subject + grade, and the picked ones with their weightage.
  const [chapters, setChapters] = useState<ChapterInfo[]>([]);
  const [chaptersLoading, setChaptersLoading] = useState(false);
  const [chaptersError, setChaptersError] = useState<string | null>(null);
  const [chaptersReload, setChaptersReload] = useState(0);
  const [weights, setWeights] = useState<Record<string, number>>({});

  const nextKey = useRef(4);
  const [sections, setSections] = useState<SectionRow[]>([
    { key: 1, name: 'Section A', type: 'MCQ', marksPerQuestion: 1, totalMarks: 10, difficulty: 'easy' },
    { key: 2, name: 'Section B', type: 'Short', marksPerQuestion: 2, totalMarks: 10, difficulty: 'medium' },
    { key: 3, name: 'Section C', type: 'Long', marksPerQuestion: 5, totalMarks: 10, difficulty: 'medium' },
  ]);

  const [plan, setPlan] = useState<BlueprintPlan | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  // Questions gathered so far while the paper is being built.
  const [progress, setProgress] = useState<BlueprintProgress>({ done: 0, total: 0 });
  const buildAbort = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchCombinations()
      .then(setMarksByType)
      .catch(() => setMarksByType(DEFAULT_MARKS_BY_TYPE));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setChaptersLoading(true);
    setChaptersError(null);
    setWeights({});
    fetchChapters(subject, grade)
      .then((rows) => {
        if (!cancelled) setChapters(rows);
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
  }, [subject, grade, chaptersReload]);

  // --- chapters ---------------------------------------------------------------

  // Picked chapters, in syllabus order (that's also the order they appear in the paper).
  const picked = useMemo(() => chapters.filter((c) => c.name in weights).map((c) => c.name), [chapters, weights]);
  const weightTotal = picked.reduce((sum, name) => sum + (weights[name] || 0), 0);

  const toggleChapter = (name: string) => {
    const next = new Set(picked);
    if (next.has(name)) next.delete(name);
    else if (next.size >= MAX_CHAPTERS) {
      showToast(`A paper can draw on at most ${MAX_CHAPTERS} chapters.`, 'warning');
      return;
    } else next.add(name);
    // Adding or removing a chapter re-splits evenly; fine-tune the numbers afterwards.
    setWeights(splitEvenly(chapters.map((c) => c.name).filter((n) => next.has(n))));
  };

  const selectAllChapters = () => setWeights(splitEvenly(chapters.slice(0, MAX_CHAPTERS).map((c) => c.name)));
  const clearChapters = () => setWeights({});
  const evenSplit = () => setWeights(splitEvenly(picked));

  // --- sections ---------------------------------------------------------------

  const updateSection = (key: number, patch: Partial<BlueprintSection>) =>
    setSections((rows) =>
      rows.map((r) => {
        if (r.key !== key) return r;
        const next = { ...r, ...patch };
        // Changing the type may leave the marks value invalid for it.
        if (patch.type && !marksByType[patch.type].includes(next.marksPerQuestion)) {
          const allowed = marksByType[patch.type];
          next.marksPerQuestion = (allowed.includes(2) ? 2 : allowed[0]) as Marks;
        }
        return next;
      }),
    );

  const addSection = () => {
    if (sections.length >= MAX_SECTIONS) return;
    const key = nextKey.current++;
    setSections((rows) => [
      ...rows,
      {
        key,
        name: `Section ${String.fromCharCode(65 + rows.length)}`,
        type: 'Short',
        marksPerQuestion: 2,
        totalMarks: 10,
        difficulty: settings.defaultDifficulty,
      },
    ]);
  };

  const removeSection = (key: number) => setSections((rows) => rows.filter((r) => r.key !== key));

  const totalMarks = sections.reduce((sum, s) => sum + (s.totalMarks || 0), 0);
  const totalQuestions = sections.reduce((sum, s) => sum + (sectionQuestions(s) ?? 0), 0);

  // --- validation (mirrors the backend so problems show next to the field) ----

  const problems = useMemo(() => {
    const out: string[] = [];
    if (picked.length === 0) out.push('Pick at least one chapter.');
    else if (Math.abs(weightTotal - 100) > 0.01) out.push(`Chapter weightage adds up to ${weightTotal}%, not 100%.`);
    if (picked.some((n) => !(weights[n] > 0))) out.push('Every chapter needs a weightage above 0.');
    if (sections.length === 0) out.push('Add at least one section.');
    const names = sections.map((s) => s.name.trim().toLowerCase());
    if (names.some((n) => !n)) out.push('Every section needs a name.');
    if (new Set(names).size !== names.length) out.push('Section names must be different from each other.');
    for (const s of sections) {
      if (sectionQuestions(s) === null) {
        out.push(`${s.name || 'A section'}: ${s.totalMarks || 0} marks isn't a whole number of ${s.marksPerQuestion}-mark questions.`);
      }
    }
    if (totalQuestions > MAX_QUESTIONS) out.push(`A paper can have at most ${MAX_QUESTIONS} questions (this has ${totalQuestions}).`);
    return out;
  }, [picked, weights, weightTotal, sections, totalQuestions]);

  const blueprint: BlueprintInput = useMemo(
    () => ({
      title,
      subject,
      grade,
      chapters: picked.map((name) => ({ name, weightage: weights[name] })),
      sections: sections.map(({ name, type, marksPerQuestion, totalMarks: marks, difficulty }) => ({
        name: name.trim(),
        type,
        marksPerQuestion,
        totalMarks: marks,
        difficulty,
      })),
      refresh: fresh,
    }),
    [title, subject, grade, picked, weights, sections, fresh],
  );

  // --- live preview of the split ------------------------------------------------

  const valid = problems.length === 0;
  const blueprintKey = JSON.stringify({ ...blueprint, title: '', refresh: false });
  useEffect(() => {
    if (!valid) {
      setPlan(null);
      setPlanError(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      previewBlueprint(blueprint)
        .then((p) => {
          if (cancelled) return;
          setPlan(p);
          setPlanError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setPlan(null);
          setPlanError(errorMessage(err));
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // The preview depends on the structure only, not on the title or refresh flag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blueprintKey, valid]);

  // --- generate ---------------------------------------------------------------

  const handleGenerate = async () => {
    if (!valid || generating) return;
    setGenerating(true);
    setProgress({ done: 0, total: plan?.totalQuestions ?? 0 });
    const abort = new AbortController();
    buildAbort.current = abort;
    try {
      const bank = await buildBlueprintPaper(blueprint, setProgress, abort.signal);
      upsertBank(bank);
      showToast(`Question paper created: ${bank.questionCount} questions, ${bank.totalMarks} marks.`, 'success');
      navigate(`/question-banks/${bank.id}`);
    } catch (err) {
      if (abort.signal.aborted) return;
      showToast(errorMessage(err), 'error');
      setGenerating(false);
    }
  };

  // Leaving the page stops polling; the server still finishes and saves the paper.
  useEffect(() => () => buildAbort.current?.abort(), []);

  const gaps = plan?.chapters.filter((c) => Math.abs(c.plannedMarks - c.targetMarks) > 1) ?? [];

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div>
        <h2 className="text-xl font-bold text-slate-900">Question Papers</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Describe the paper — marks per section and weightage per chapter — and the system picks the questions to fit,
          like a board exam paper.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* ---------------- Form ---------------- */}
        <div className="lg:col-span-3 space-y-5">
          <div className={cardClass}>
            <h3 className={cardTitleClass}>Paper details</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Title</label>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder={`${subject} Question Paper (Grade ${grade})`}
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Subject</label>
                <select value={subject} onChange={(e) => setSubject(e.target.value as Subject)} className={inputClass}>
                  {SUBJECTS.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Grade</label>
                <div className="flex gap-2">
                  {GRADES.map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGrade(g)}
                      className={`flex-1 py-2 text-sm rounded-lg border font-medium transition-colors ${
                        grade === g
                          ? 'bg-indigo-600 text-white border-indigo-600'
                          : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'
                      }`}
                    >
                      {g}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Chapters + weightage */}
          <div className={cardClass}>
            <div className="flex items-start justify-between gap-3 mb-4 pb-2 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Chapters &amp; weightage</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Pick the chapters this paper covers and what share of the marks each gets.
                </p>
              </div>
              <div className="flex gap-3 shrink-0 text-xs font-medium">
                <button type="button" onClick={selectAllChapters} disabled={chapters.length === 0} className="text-indigo-600 hover:text-indigo-800 disabled:opacity-40">
                  Select all
                </button>
                <button type="button" onClick={clearChapters} disabled={picked.length === 0} className="text-slate-500 hover:text-slate-800 disabled:opacity-40">
                  Clear
                </button>
              </div>
            </div>

            {chaptersLoading && <ChapterListSkeleton />}
            {!chaptersLoading && chaptersError && (
              <p className="text-xs text-red-600">
                {chaptersError}{' '}
                <button type="button" onClick={() => setChaptersReload((n) => n + 1)} className="font-medium underline">
                  Retry
                </button>
              </p>
            )}
            {!chaptersLoading && !chaptersError && chapters.length === 0 && (
              <p className="text-xs text-slate-500">
                No chapters are available for {subject}, Grade {grade}. Check that SYLLABUS_JSON_PATH points at a
                syllabus file and restart the backend.
              </p>
            )}

            <ul className="space-y-1.5">
              {chapters.map((c) => {
                const on = c.name in weights;
                return (
                  <li
                    key={c.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg border transition-colors ${
                      on ? 'border-indigo-200 bg-indigo-50/50' : 'border-slate-200'
                    }`}
                  >
                    <label className="flex items-center gap-2.5 flex-1 min-w-0 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() => toggleChapter(c.name)}
                        className="accent-indigo-600"
                      />
                      <span className="text-sm text-slate-800 truncate">{c.name}</span>
                    </label>
                    {on && (
                      <div className="flex items-center gap-1 shrink-0">
                        <input
                          type="number"
                          min={1}
                          max={100}
                          value={weights[c.name] ?? ''}
                          onChange={(e) => setWeights((w) => ({ ...w, [c.name]: parseFloat(e.target.value) || 0 }))}
                          aria-label={`Weightage for ${c.name}`}
                          className="w-16 px-2 py-1 text-sm text-right rounded-md border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        />
                        <span className="text-xs text-slate-500">%</span>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>

            {picked.length > 0 && (
              <div className="flex items-center justify-between mt-3 text-xs">
                <span className={Math.abs(weightTotal - 100) > 0.01 ? 'font-semibold text-red-600' : 'font-semibold text-emerald-600'}>
                  Total: {weightTotal}%
                </span>
                <button type="button" onClick={evenSplit} className="flex items-center gap-1 font-medium text-indigo-600 hover:text-indigo-800">
                  <Scale className="w-3.5 h-3.5" /> Split evenly
                </button>
              </div>
            )}
            {picked.length > 0 && (
              <p className="mt-1.5 text-xs text-slate-400">Adding or removing a chapter re-splits the weightage evenly.</p>
            )}
          </div>

          {/* Sections */}
          <div className={cardClass}>
            <div className="flex items-start justify-between gap-3 mb-4 pb-2 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-semibold text-slate-900">Sections</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Each section has a question type and is worth a set number of marks.
                </p>
              </div>
              <button
                type="button"
                onClick={addSection}
                disabled={sections.length >= MAX_SECTIONS}
                className="flex items-center gap-1 shrink-0 text-xs font-medium text-indigo-600 hover:text-indigo-800 disabled:opacity-40"
              >
                <Plus className="w-3.5 h-3.5" /> Add section
              </button>
            </div>

            <div className="space-y-3">
              {sections.map((s) => {
                const count = sectionQuestions(s);
                return (
                  <div key={s.key} className="rounded-lg border border-slate-200 p-3">
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2.5 items-end">
                      <div className="col-span-2 sm:col-span-2">
                        <label className="block text-xs font-medium text-slate-600 mb-1">Name</label>
                        <input
                          value={s.name}
                          onChange={(e) => updateSection(s.key, { name: e.target.value })}
                          className={inputClass}
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Type</label>
                        <select
                          value={s.type}
                          onChange={(e) => updateSection(s.key, { type: e.target.value as QuestionType })}
                          className={inputClass}
                        >
                          {(Object.keys(TYPE_LABEL) as QuestionType[]).map((t) => (
                            <option key={t} value={t}>
                              {TYPE_LABEL[t]}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Marks each</label>
                        <select
                          value={s.marksPerQuestion}
                          onChange={(e) => updateSection(s.key, { marksPerQuestion: parseInt(e.target.value) as Marks })}
                          className={inputClass}
                        >
                          {marksByType[s.type].map((m) => (
                            <option key={m} value={m}>
                              {m}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-slate-600 mb-1">Section marks</label>
                        <input
                          type="number"
                          min={1}
                          value={s.totalMarks || ''}
                          onChange={(e) => updateSection(s.key, { totalMarks: parseInt(e.target.value) || 0 })}
                          className={inputClass}
                        />
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-2 mt-2.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500">Difficulty</span>
                        <select
                          value={s.difficulty}
                          onChange={(e) => updateSection(s.key, { difficulty: e.target.value as Difficulty })}
                          className="px-2 py-1 text-xs capitalize rounded-md border border-slate-300 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                        >
                          {DIFFICULTIES.map((d) => (
                            <option key={d} value={d}>
                              {d}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="flex items-center gap-3">
                        {count !== null ? (
                          <span className="text-xs font-medium text-slate-600">
                            {count} question{count === 1 ? '' : 's'} × {s.marksPerQuestion} = {s.totalMarks} marks
                          </span>
                        ) : (
                          <span className="text-xs font-medium text-red-600">
                            Not a whole number of {s.marksPerQuestion}-mark questions
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => removeSection(s.key)}
                          className="p-1 text-slate-400 hover:text-red-600 transition-colors"
                          aria-label={`Remove ${s.name}`}
                          title="Remove section"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
              {sections.length === 0 && <p className="text-xs text-slate-500">Add a section to start the blueprint.</p>}
            </div>

            <label className="flex items-start gap-2 text-xs text-slate-700 cursor-pointer mt-4 pt-4 border-t border-slate-100">
              <input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} className="mt-0.5 accent-indigo-600" />
              <span>
                Always generate new questions
                <span className="block text-slate-400">
                  Off: reuse matching questions already stored, and only generate the shortfall. A repeat of the same
                  blueprint will then give you the same paper.
                </span>
              </span>
            </label>
          </div>
        </div>

        {/* ---------------- Summary ---------------- */}
        <div className="lg:col-span-2">
          <div className="lg:sticky lg:top-4 space-y-4">
            <div className={cardClass}>
              <h3 className={cardTitleClass}>Blueprint summary</h3>
              <div className="grid grid-cols-2 gap-3 mb-4">
                <div>
                  <p className="text-xs text-slate-500 font-medium">Total marks</p>
                  <p className="text-lg font-bold text-slate-900">{totalMarks}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Questions</p>
                  <p className="text-lg font-bold text-slate-900">{totalQuestions}</p>
                </div>
              </div>

              {problems.length > 0 && (
                <ul className="space-y-1.5 mb-4">
                  {problems.map((p) => (
                    <li key={p} className="flex items-start gap-2 text-xs text-amber-700">
                      <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                      {p}
                    </li>
                  ))}
                </ul>
              )}

              {planError && <p className="text-xs text-red-600 mb-4">{planError}</p>}

              {plan && (
                <div className="space-y-4">
                  <div>
                    <p className="text-xs font-semibold text-slate-700 mb-1.5">Marks per chapter</p>
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="text-slate-400 text-left">
                          <th className="font-medium pb-1">Chapter</th>
                          <th className="font-medium pb-1 text-right">Target</th>
                          <th className="font-medium pb-1 text-right">Planned</th>
                        </tr>
                      </thead>
                      <tbody>
                        {plan.chapters.map((c) => {
                          const off = Math.abs(c.plannedMarks - c.targetMarks) > 1;
                          return (
                            <tr key={c.chapter} className="border-t border-slate-100">
                              <td className="py-1.5 pr-2 text-slate-700">{c.chapter}</td>
                              <td className="py-1.5 text-right text-slate-500">{Number(c.targetMarks.toFixed(1))}</td>
                              <td className={`py-1.5 text-right font-semibold ${off ? 'text-amber-600' : 'text-slate-900'}`}>
                                {c.plannedMarks}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {gaps.length > 0 && (
                      <p className="mt-2 text-xs text-amber-700">
                        Questions are whole units, so {gaps.map((g) => g.chapter).join(', ')}{' '}
                        can't match the weightage exactly. More, smaller questions give a closer fit.
                      </p>
                    )}
                  </div>

                  <div>
                    <p className="text-xs font-semibold text-slate-700 mb-1.5">Questions per section</p>
                    <div className="space-y-2">
                      {plan.sections.map((s) => (
                        <div key={s.name} className="text-xs">
                          <p className="font-medium text-slate-800">
                            {s.name}{' '}
                            <span className="font-normal text-slate-400">
                              · {s.questions} × {s.marksPerQuestion} = {s.marks}
                            </span>
                          </p>
                          <p className="text-slate-500">
                            {s.allocations.map((a) => `${a.chapter} ${a.questions}`).join(' · ')}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {!plan && valid && !planError && (
                <p className="flex items-center gap-2 text-xs text-slate-500">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> Working out the split…
                </p>
              )}
            </div>

            <button
              type="button"
              onClick={() => void handleGenerate()}
              disabled={!valid || generating}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors shadow-sm"
            >
              {generating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Building paper… {progress.total > 0 ? `${progress.done}/${progress.total}` : ''}
                </>
              ) : (
                <>
                  <Wand2 className="w-4 h-4" />
                  Generate question paper
                </>
              )}
            </button>
            {generating && (
              <div role="status" aria-busy="true" className="space-y-2">
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <p className="font-semibold text-slate-900">Creating questions…</p>
                  <p className="font-semibold text-slate-900 tabular-nums whitespace-nowrap">
                    {progress.done} <span className="font-normal text-slate-500">of {progress.total || '…'} created</span>
                  </p>
                </div>
                <div
                  className="h-1.5 bg-slate-100 rounded-full overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={progress.total}
                  aria-valuenow={progress.done}
                  aria-label="Questions created"
                >
                  <div
                    className="h-full bg-indigo-500 rounded-full transition-all duration-500"
                    style={{ width: `${progress.total ? Math.min(100, Math.max(4, (progress.done / progress.total) * 100)) : 4}%` }}
                  />
                </div>
                <p className="flex items-start gap-2 text-xs text-slate-500">
                  <FileText className="w-3.5 h-3.5 mt-0.5 shrink-0" />
                  Stored questions are reused and the rest are written by the AI, so a large paper can take a minute or
                  two. Keep this page open.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
