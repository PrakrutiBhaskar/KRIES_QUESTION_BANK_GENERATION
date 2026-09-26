import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wand2,
  Loader2,
  ChevronDown,
  CheckCircle2,
  Pencil,
  Trash2,
  Plus,
  RefreshCw,
  GripVertical,
  ChevronUp,
} from 'lucide-react';
import { SYLLABUS } from '../data/syllabus';
import { generateMockQuestions } from '../lib/generator';
import { generateId } from '../lib/utils';
import { useApp } from '../hooks/useApp';
import type {
  Subject,
  Grade,
  QuestionType,
  Difficulty,
  BloomsLevel,
  Marks,
  GenerateFormData,
  Question,
  QuestionBank,
} from '../types';
import { DifficultyBadge, TypeBadge, BloomsBadge, ConfirmModal } from '../components/ui';

const SUBJECTS: Subject[] = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];
const GRADES: Grade[] = [7, 8, 9];
const TYPES: Array<QuestionType | 'Mixed'> = ['MCQ', 'Short', 'Long', 'Mixed'];
const DIFFICULTIES: Difficulty[] = ['easy', 'medium', 'hard', 'mixed'];
const BLOOMS: Array<BloomsLevel | 'Mixed'> = [
  'Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create', 'Mixed',
];
const MARKS_OPTIONS: Marks[] = [1, 2, 3, 5];

// ============================================================
// Question Card (editable)
// ============================================================
interface QuestionCardProps {
  question: Question;
  onEdit: (q: Question) => void;
  onDelete: (id: string) => void;
  onRegenerate: (id: string) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  isFirst: boolean;
  isLast: boolean;
}

function QuestionCard({ question, onEdit, onDelete, onRegenerate, onMoveUp, onMoveDown, isFirst, isLast }: QuestionCardProps) {
  const [expanded, setExpanded] = useState(false);

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
            <BloomsBadge level={question.bloomsLevel} />
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
              {question.marks} mark{question.marks > 1 ? 's' : ''}
            </span>
          </div>

          {/* Question text */}
          <p className="text-sm font-medium text-slate-900 mb-1 leading-snug">{question.text}</p>

          {/* MCQ options */}
          {question.options && question.options.length > 0 && (
            <ol className="list-none space-y-1 my-2">
              {question.options.map((opt, i) => (
                <li key={i} className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-lg border ${opt === question.answer ? 'bg-emerald-50 border-emerald-200 text-emerald-800 font-medium' : 'bg-slate-50 border-slate-100 text-slate-600'}`}>
                  <span className="font-semibold shrink-0">{String.fromCharCode(65 + i)}.</span>
                  {opt}
                  {opt === question.answer && <CheckCircle2 className="w-3.5 h-3.5 ml-auto shrink-0 text-emerald-500" />}
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
            </div>
          )}

          {/* Topic tag */}
          <p className="text-xs text-slate-400 mt-2">Topic: {question.topic}</p>
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
            onClick={() => onEdit(question)}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-indigo-50 hover:text-indigo-600 transition-colors"
            aria-label="Edit question"
            title="Edit"
          >
            <Pencil className="w-4 h-4" />
          </button>
          <button
            onClick={() => onRegenerate(question.id)}
            className="p-1.5 rounded-lg text-slate-400 hover:bg-amber-50 hover:text-amber-600 transition-colors"
            aria-label="Regenerate question"
            title="Regenerate"
          >
            <RefreshCw className="w-4 h-4" />
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
// Edit Question Modal
// ============================================================
interface EditQuestionModalProps {
  question: Question | null;
  onSave: (q: Question) => void;
  onClose: () => void;
}

function EditQuestionModal({ question, onSave, onClose }: EditQuestionModalProps) {
  const [text, setText] = useState(question?.text ?? '');
  const [answer, setAnswer] = useState(question?.answer ?? '');
  const [explanation, setExplanation] = useState(question?.explanation ?? '');

  if (!question) return null;

  const handleSave = () => {
    onSave({ ...question, text, answer, explanation });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-semibold text-slate-900">Edit Question {question.questionNumber}</h3>
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
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Answer</label>
            <textarea
              rows={4}
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
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors">
            Cancel
          </button>
          <button onClick={handleSave} className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
            Save Changes
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
  const { addQuestionBank, showToast, settings } = useApp();
  const navigate = useNavigate();

  const [form, setForm] = useState<GenerateFormData>({
    name: '',
    subject: 'Science',
    chapter: SYLLABUS.find((s) => s.name === 'Science')?.chapters[0] ?? '',
    description: '',
    grade: 8,
    questionCount: settings.defaultQuestionCount,
    questionType: settings.defaultQuestionType as QuestionType | 'Mixed',
    difficulty: settings.defaultDifficulty,
    bloomsLevel: settings.defaultBloomsLevel as BloomsLevel | 'Mixed',
    marksPerQuestion: settings.defaultMarks,
    learningOutcome: '',
  });

  const [loading, setLoading] = useState(false);
  const [generated, setGenerated] = useState<Question[]>([]);
  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const chapters = SYLLABUS.find((s) => s.name === form.subject)?.chapters ?? [];

  const setField = <K extends keyof GenerateFormData>(key: K, val: GenerateFormData[K]) =>
    setForm((p) => ({ ...p, [key]: val }));

  const handleSubjectChange = (subject: Subject) => {
    const chaps = SYLLABUS.find((s) => s.name === subject)?.chapters ?? [];
    setForm((p) => ({ ...p, subject, chapter: chaps[0] ?? '' }));
    setGenerated([]);
    setSaved(false);
  };

  const handleGenerate = async (e: FormEvent) => {
    e.preventDefault();
    if (!form.chapter) { showToast('Please select a chapter.', 'error'); return; }
    if (!form.name.trim()) { showToast('Please enter a question bank name.', 'error'); return; }

    setLoading(true);
    setSaved(false);
    // Simulate AI generation delay
    await new Promise((r) => setTimeout(r, 1500));
    const questions = generateMockQuestions(form);
    setGenerated(questions);
    setLoading(false);
    showToast(`Successfully generated ${questions.length} questions!`, 'success');
  };

  const handleEdit = (updated: Question) => {
    setGenerated((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
    showToast('Question updated.', 'success');
  };

  const handleDelete = (id: string) => {
    setGenerated((prev) => {
      const next = prev.filter((q) => q.id !== id);
      return next.map((q, i) => ({ ...q, questionNumber: i + 1 }));
    });
    setDeleteId(null);
    showToast('Question deleted.', 'info');
  };

  const handleRegenerate = (id: string) => {
    const old = generated.find((q) => q.id === id);
    if (!old) return;
    const [newQ] = generateMockQuestions({ ...form, questionCount: 1 });
    const updated = {
      ...newQ,
      id: old.id,
      questionNumber: old.questionNumber,
      type: old.type,
      difficulty: old.difficulty,
      marks: old.marks,
    };
    setGenerated((prev) => prev.map((q) => (q.id === id ? updated : q)));
    showToast('Question regenerated.', 'success');
  };

  const handleAddQuestion = () => {
    const [newQ] = generateMockQuestions({ ...form, questionCount: 1 });
    newQ.questionNumber = generated.length + 1;
    setGenerated((prev) => [...prev, newQ]);
    showToast('New question added.', 'success');
  };

  const handleMoveUp = (id: string) => {
    setGenerated((prev) => {
      const idx = prev.findIndex((q) => q.id === id);
      if (idx <= 0) return prev;
      const next = [...prev];
      [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
      return next.map((q, i) => ({ ...q, questionNumber: i + 1 }));
    });
  };

  const handleMoveDown = (id: string) => {
    setGenerated((prev) => {
      const idx = prev.findIndex((q) => q.id === id);
      if (idx >= prev.length - 1) return prev;
      const next = [...prev];
      [next[idx], next[idx + 1]] = [next[idx + 1], next[idx]];
      return next.map((q, i) => ({ ...q, questionNumber: i + 1 }));
    });
  };

  const handleSaveBank = () => {
    if (generated.length === 0) return;
    const bank: QuestionBank = {
      id: generateId(),
      name: form.name,
      subject: form.subject,
      chapter: form.chapter,
      description: form.description,
      grade: form.grade,
      questionCount: generated.length,
      difficulty: form.difficulty,
      status: 'draft',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      totalMarks: generated.reduce((s, q) => s + q.marks, 0),
      questions: generated,
    };
    addQuestionBank(bank);
    setSaved(true);
    showToast('Question bank saved!', 'success');
    navigate('/question-banks');
  };

  const totalMarks = generated.reduce((s, q) => s + q.marks, 0);

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
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Bank Name *</label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => setField('name', e.target.value)}
                  placeholder="e.g. Photosynthesis Practice Set"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

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
                <select
                  value={form.chapter}
                  onChange={(e) => setField('chapter', e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {chapters.map((c) => <option key={c}>{c}</option>)}
                </select>
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

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Description</label>
                <textarea
                  rows={2}
                  value={form.description}
                  onChange={(e) => setField('description', e.target.value)}
                  placeholder="Optional description..."
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                />
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
                  min={3}
                  max={30}
                  value={form.questionCount}
                  onChange={(e) => setField('questionCount', parseInt(e.target.value))}
                  className="w-full accent-indigo-600"
                />
                <div className="flex justify-between text-xs text-slate-400">
                  <span>3</span><span>30</span>
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Question Type</label>
                <div className="grid grid-cols-2 gap-2">
                  {TYPES.map((t) => (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setField('questionType', t)}
                      className={`py-1.5 text-xs rounded-lg border font-medium transition-colors ${form.questionType === t ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                    >
                      {t === 'Short' ? 'Short Answer' : t === 'Long' ? 'Long Answer' : t}
                    </button>
                  ))}
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

          {/* Academic Configuration */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-900 mb-4 pb-2 border-b border-slate-100">
              Academic Configuration
            </h3>
            <div className="space-y-3.5">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Bloom's Taxonomy Level</label>
                <select
                  value={form.bloomsLevel}
                  onChange={(e) => setField('bloomsLevel', e.target.value as BloomsLevel | 'Mixed')}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {BLOOMS.map((b) => <option key={b}>{b}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Marks per Question</label>
                <div className="flex gap-2">
                  {MARKS_OPTIONS.map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setField('marksPerQuestion', m)}
                      className={`flex-1 py-1.5 text-sm rounded-lg border font-medium transition-colors ${form.marksPerQuestion === m ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-white text-slate-700 border-slate-300 hover:border-indigo-300'}`}
                    >
                      {m}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">Learning Outcome</label>
                <input
                  type="text"
                  value={form.learningOutcome}
                  onChange={(e) => setField('learningOutcome', e.target.value)}
                  placeholder="e.g. Students will understand photosynthesis"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
          </div>

          {/* Generate button */}
          <button
            type="submit"
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors shadow-sm"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Generating questions…
              </>
            ) : (
              <>
                <Wand2 className="w-4 h-4" />
                Generate Question Bank
              </>
            )}
          </button>
        </form>

        {/* Generated questions panel */}
        <div className="lg:col-span-3 space-y-4">
          {loading && (
            <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm flex flex-col items-center gap-4">
              <div className="w-12 h-12 bg-indigo-50 rounded-full flex items-center justify-center">
                <Loader2 className="w-6 h-6 text-indigo-600 animate-spin" />
              </div>
              <div className="text-center">
                <p className="text-sm font-semibold text-slate-900">Generating questions…</p>
                <p className="text-xs text-slate-500 mt-0.5">
                  AI is crafting {form.questionCount} {form.difficulty} {form.questionType} questions for{' '}
                  <span className="font-medium">{form.chapter}</span>.
                </p>
              </div>
              <div className="w-48 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-indigo-500 rounded-full animate-pulse" style={{ width: '70%' }} />
              </div>
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
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleAddQuestion}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    Add Question
                  </button>
                  <button
                    onClick={handleSaveBank}
                    disabled={saved}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    {saved ? 'Saved!' : 'Save Bank'}
                  </button>
                </div>
              </div>

              {/* Question cards */}
              <div className="space-y-3">
                {generated.map((q, i) => (
                  <QuestionCard
                    key={q.id}
                    question={q}
                    onEdit={setEditingQuestion}
                    onDelete={(id) => setDeleteId(id)}
                    onRegenerate={handleRegenerate}
                    onMoveUp={handleMoveUp}
                    onMoveDown={handleMoveDown}
                    isFirst={i === 0}
                    isLast={i === generated.length - 1}
                  />
                ))}
              </div>

              {/* Save again at bottom */}
              <button
                onClick={handleSaveBank}
                disabled={saved}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-60 text-white text-sm font-semibold rounded-xl transition-colors"
              >
                <CheckCircle2 className="w-4 h-4" />
                {saved ? 'Saved to Question Banks' : 'Save Question Bank'}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Edit modal */}
      {editingQuestion && (
        <EditQuestionModal
          question={editingQuestion}
          onSave={handleEdit}
          onClose={() => setEditingQuestion(null)}
        />
      )}

      {/* Delete confirm */}
      <ConfirmModal
        open={deleteId !== null}
        title="Delete Question"
        message="Are you sure you want to delete this question? This cannot be undone."
        confirmLabel="Delete"
        danger
        onConfirm={() => deleteId && handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
