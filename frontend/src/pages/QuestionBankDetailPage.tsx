import { useState } from 'react';
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
} from 'lucide-react';
import { useApp } from '../hooks/useApp';
import type { Question } from '../types';
import {
  DifficultyBadge,
  TypeBadge,
  BloomsBadge,
  StatusBadge,
  EmptyState,
  ConfirmModal,
} from '../components/ui';
import { formatDate, generateId } from '../lib/utils';

// ============================================================
// Edit Question Modal (inline)
// ============================================================
interface EditModalProps {
  question: Question | null;
  onSave: (q: Question) => void;
  onClose: () => void;
}

function EditModal({ question, onSave, onClose }: EditModalProps) {
  const [text, setText] = useState(question?.text ?? '');
  const [answer, setAnswer] = useState(question?.answer ?? '');
  const [explanation, setExplanation] = useState(question?.explanation ?? '');

  if (!question) return null;

  const handleSave = () => {
    onSave({ ...question, text, answer, explanation });
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
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors"
          >
            Save Changes
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
            <BloomsBadge level={question.bloomsLevel} />
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

          <p className="text-xs text-slate-400 mt-2">Topic: {question.topic}</p>
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
            aria-label="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Add Question Modal
// ============================================================
interface AddQuestionModalProps {
  open: boolean;
  onAdd: (q: Question) => void;
  onClose: () => void;
  nextNumber: number;
}

function AddQuestionModal({ open, onAdd, onClose, nextNumber }: AddQuestionModalProps) {
  const [text, setText] = useState('');
  const [answer, setAnswer] = useState('');
  const [explanation, setExplanation] = useState('');
  const [type, setType] = useState<Question['type']>('Short');
  const [difficulty, setDifficulty] = useState<Question['difficulty']>('medium');
  const [marks, setMarks] = useState<Question['marks']>(2);

  if (!open) return null;

  const handleAdd = () => {
    if (!text.trim() || !answer.trim()) return;
    onAdd({
      id: generateId(),
      questionNumber: nextNumber,
      text,
      answer,
      explanation,
      type,
      difficulty,
      marks,
      topic: 'General',
      bloomsLevel: 'Understand',
      tags: [],
    });
    setText('');
    setAnswer('');
    setExplanation('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-xl overflow-y-auto max-h-[90vh]">
        <div className="px-6 py-4 border-b border-slate-100">
          <h3 className="text-base font-semibold text-slate-900">Add Question {nextNumber}</h3>
        </div>
        <div className="px-6 py-4 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Type</label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value as Question['type'])}
                className="w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="MCQ">MCQ</option>
                <option value="Short">Short</option>
                <option value="Long">Long</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Difficulty</label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value as Question['difficulty'])}
                className="w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option value="easy">Easy</option>
                <option value="medium">Medium</option>
                <option value="hard">Hard</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">Marks</label>
              <select
                value={marks}
                onChange={(e) => setMarks(parseInt(e.target.value) as Question['marks'])}
                className="w-full px-2.5 py-2 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {[1, 2, 3, 5].map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Question Text *</label>
            <textarea
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Enter the question..."
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Answer *</label>
            <textarea
              rows={4}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Enter the model answer..."
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1.5">Explanation (optional)</label>
            <textarea
              rows={2}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              placeholder="Enter an explanation..."
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
            />
          </div>
        </div>
        <div className="px-6 py-4 border-t border-slate-100 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors">Cancel</button>
          <button onClick={handleAdd} disabled={!text.trim() || !answer.trim()} className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">Add Question</button>
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
  const { getQuestionBank, updateQuestionBank, showToast } = useApp();
  const navigate = useNavigate();

  const bank = getQuestionBank(id ?? '');

  const [editingQuestion, setEditingQuestion] = useState<Question | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [addingQuestion, setAddingQuestion] = useState(false);

  if (!bank) {
    return (
      <div className="flex flex-col items-center justify-center py-24 gap-4">
        <BookOpen className="w-12 h-12 text-slate-300" />
        <p className="text-slate-500 font-medium">Question bank not found.</p>
        <Link to="/question-banks" className="text-indigo-600 text-sm hover:underline">
          Back to Question Banks
        </Link>
      </div>
    );
  }

  const handleSaveEdit = (updated: Question) => {
    const newBank = {
      ...bank,
      questions: bank.questions.map((q) => (q.id === updated.id ? updated : q)),
      updatedAt: new Date().toISOString(),
    };
    updateQuestionBank(newBank);
    setEditingQuestion(null);
    showToast('Question updated.', 'success');
  };

  const handleDelete = (qId: string) => {
    const newQuestions = bank.questions
      .filter((q) => q.id !== qId)
      .map((q, i) => ({ ...q, questionNumber: i + 1 }));
    updateQuestionBank({
      ...bank,
      questions: newQuestions,
      questionCount: newQuestions.length,
      totalMarks: newQuestions.reduce((s, q) => s + q.marks, 0),
      updatedAt: new Date().toISOString(),
    });
    setDeleteId(null);
    showToast('Question deleted.', 'info');
  };

  const handleAddQuestion = (q: Question) => {
    const newQuestions = [...bank.questions, q];
    updateQuestionBank({
      ...bank,
      questions: newQuestions,
      questionCount: newQuestions.length,
      totalMarks: newQuestions.reduce((s, qq) => s + qq.marks, 0),
      updatedAt: new Date().toISOString(),
    });
    setAddingQuestion(false);
    showToast('Question added.', 'success');
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
              <StatusBadge status={bank.status} />
              <DifficultyBadge difficulty={bank.difficulty} />
              <span className="text-xs text-slate-400">Grade {bank.grade}</span>
            </div>
            <h2 className="text-xl font-bold text-slate-900 leading-tight">{bank.name}</h2>
            <p className="text-sm text-slate-500 mt-1">{bank.subject} — {bank.chapter}</p>
            {bank.description && (
              <p className="text-sm text-slate-600 mt-2 leading-relaxed">{bank.description}</p>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => showToast(`Exporting "${bank.name}" as PDF… (demo only)`, 'info')}
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
            >
              <Download className="w-4 h-4" />
              Export
            </button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-5 border-t border-slate-100">
          {[
            { label: 'Questions', value: bank.questionCount },
            { label: 'Total Marks', value: bank.totalMarks },
            { label: 'Created', value: formatDate(bank.createdAt) },
            { label: 'Updated', value: formatDate(bank.updatedAt) },
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
            Add Question
          </button>
        </div>

        {bank.questions.length === 0 ? (
          <EmptyState
            icon={<BookOpen className="w-7 h-7" />}
            title="No questions yet"
            description="Add questions to this bank manually or go back and generate more."
            action={
              <button
                onClick={() => setAddingQuestion(true)}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                Add Question
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

      <AddQuestionModal
        open={addingQuestion}
        onAdd={handleAddQuestion}
        onClose={() => setAddingQuestion(false)}
        nextNumber={bank.questions.length + 1}
      />

      <ConfirmModal
        open={deleteId !== null}
        title="Delete Question"
        message="Are you sure you want to delete this question?"
        confirmLabel="Delete"
        danger
        onConfirm={() => deleteId && handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  );
}
