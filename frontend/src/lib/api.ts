// ============================================================
// Typed client for the FastAPI backend (docs/api-contract.md).
// Every endpoint returns errors as {"error": string, "detail": string}.
// ============================================================
import type {
  ChapterInfo,
  Difficulty,
  Grade,
  Marks,
  MarksByType,
  Question,
  QuestionBank,
  QuestionDifficulty,
  QuestionType,
  Subject,
} from '../types';

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, detail: string) {
    super(detail || code);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

/** A message that is safe to show in a toast. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 502) return `The AI service failed: ${err.message}`;
    if (err.status >= 500) {
      // A 5xx that isn't the AI service is a backend bug or a database problem.
      return `The server hit an internal error (${err.message}). Check the backend terminal for the traceback.`;
    }
    return err.message;
  }
  if (err instanceof TypeError) return 'Cannot reach the server. Is the backend running?';
  return err instanceof Error ? err.message : 'Something went wrong.';
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs?: number): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body) headers['Content-Type'] = 'application/json';

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...headers, ...init.headers },
      signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      throw new ApiError(0, 'timeout', 'The server took too long to respond. Is the backend running?');
    }
    throw err;
  }

  if (res.status === 204) return undefined as T;

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }

  if (!res.ok) {
    const b = (body ?? {}) as { error?: string; detail?: unknown };
    const detail = typeof b.detail === 'string' ? b.detail : res.statusText;
    throw new ApiError(res.status, b.error ?? 'error', detail);
  }
  return body as T;
}

// ------------------------------------------------------------
// Wire types (snake_case, as the backend sends them)
// ------------------------------------------------------------
interface QuestionWire {
  id: string;
  subject: Subject;
  chapter: string;
  type: QuestionType;
  grade: number;
  text: string;
  options: string[] | null;
  answer: string;
  explanation: string;
  marks: number;
  difficulty: QuestionDifficulty;
  topic: string;
  tags: string[];
}

interface PaperWire {
  id: string;
  title: string;
  subject: Subject;
  total_marks: number;
  created_at: string;
  questions: { order_index: number; marks: number; marks_override: number | null; question: QuestionWire }[];
}

interface GenerateWire {
  questions: QuestionWire[];
  cached: number;
  generated: number;
  report: Record<string, unknown> | null;
}

function toQuestion(q: QuestionWire, index: number): Question {
  return {
    id: q.id,
    questionNumber: index + 1,
    subject: q.subject,
    chapter: q.chapter,
    grade: q.grade as Grade,
    text: q.text,
    type: q.type,
    difficulty: q.difficulty,
    marks: q.marks as Marks,
    topic: q.topic,
    options: q.options ?? undefined,
    answer: q.answer,
    explanation: q.explanation,
    tags: q.tags,
  };
}

export function renumber(questions: Question[]): Question[] {
  return questions.map((q, i) => ({ ...q, questionNumber: i + 1 }));
}

function toBank(p: PaperWire): QuestionBank {
  const ordered = [...p.questions].sort((a, b) => a.order_index - b.order_index);
  // Show the marks the paper actually uses (marks_override wins).
  const questions = ordered.map((item, i) => ({
    ...toQuestion(item.question, i),
    marks: item.marks as Marks,
    baseMarks: item.question.marks as Marks,
  }));

  const chapters = new Set(questions.map((q) => q.chapter));
  const difficulties = new Set(questions.map((q) => q.difficulty));

  return {
    id: p.id,
    name: p.title,
    subject: p.subject,
    chapter: chapters.size === 1 ? [...chapters][0] : chapters.size === 0 ? '—' : 'Multiple chapters',
    grade: (questions[0]?.grade ?? 8) as Grade,
    questionCount: questions.length,
    difficulty: difficulties.size === 1 ? [...difficulties][0] : 'mixed',
    createdAt: p.created_at,
    totalMarks: p.total_marks,
    questions,
  };
}

// ------------------------------------------------------------
// Syllabus
// ------------------------------------------------------------
export async function fetchChapters(subject: Subject): Promise<ChapterInfo[]> {
  const rows = await request<{ id: string; name: string; order_index: number; question_count: number }[]>(
    `/subjects/${encodeURIComponent(subject)}/chapters`,
    {},
    15000,
  );
  return rows.map((r) => ({
    id: r.id,
    name: r.name,
    orderIndex: r.order_index,
    questionCount: r.question_count,
  }));
}

/** Which marks values each question type supports (enforced by POST /generate). */
export async function fetchCombinations(): Promise<MarksByType> {
  const rows = await request<{ type: QuestionType; marks: number[] }[]>('/generation/combinations');
  const out: MarksByType = { MCQ: [], Short: [], Long: [] };
  for (const r of rows) out[r.type] = r.marks as Marks[];
  return out;
}

// ------------------------------------------------------------
// Generation
// ------------------------------------------------------------
export interface GenerateParams {
  subject: Subject;
  chapter: string;
  type: QuestionType;
  grade: Grade;
  marks: Marks;
  difficulty: QuestionDifficulty;
  count: number;
  topic?: string;
  refresh?: boolean;
}

export interface GenerateResult {
  questions: Question[];
  cached: number;
  generated: number;
}

export async function generateQuestions(p: GenerateParams): Promise<GenerateResult> {
  const body: Record<string, unknown> = {
    subject: p.subject,
    chapter: p.chapter,
    type: p.type,
    grade: p.grade,
    marks: p.marks,
    difficulty: p.difficulty,
    count: p.count,
    refresh: p.refresh ?? false,
  };
  if (p.topic?.trim()) body.topic = p.topic.trim();

  const res = await request<GenerateWire>('/generate', { method: 'POST', body: JSON.stringify(body) });
  return {
    questions: res.questions.map(toQuestion),
    cached: res.cached,
    generated: res.generated,
  };
}

// ------------------------------------------------------------
// Questions
// ------------------------------------------------------------
export interface QuestionEdit {
  text?: string;
  answer?: string;
  explanation?: string;
  options?: string[];
  marks?: number;
  difficulty?: QuestionDifficulty;
  topic?: string;
  tags?: string[];
}

export async function updateQuestion(id: string, changes: QuestionEdit): Promise<Question> {
  const q = await request<QuestionWire>(`/questions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
  return toQuestion(q, 0);
}

export async function discardQuestion(id: string): Promise<void> {
  await request<void>(`/questions/${id}`, { method: 'DELETE' });
}

// ------------------------------------------------------------
// Papers (= question banks in the UI)
// ------------------------------------------------------------
export async function fetchBanks(): Promise<QuestionBank[]> {
  const rows = await request<PaperWire[]>('/papers?limit=200');
  return rows.map(toBank);
}

export async function fetchBank(id: string): Promise<QuestionBank> {
  return toBank(await request<PaperWire>(`/papers/${id}`));
}

export async function createBank(
  title: string,
  subject: Subject,
  questionIds: string[],
): Promise<QuestionBank> {
  return toBank(
    await request<PaperWire>('/papers', {
      method: 'POST',
      body: JSON.stringify({ title, subject, question_ids: questionIds }),
    }),
  );
}

/** Replace the bank's whole question list (order = array order). */
export async function setBankQuestions(id: string, questions: Question[]): Promise<QuestionBank> {
  return toBank(
    await request<PaperWire>(`/papers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        questions: questions.map((q, i) => ({
          question_id: q.id,
          order_index: i,
          // Only send an override when it differs from the question's own marks.
          marks_override: q.baseMarks !== undefined && q.marks !== q.baseMarks ? q.marks : null,
        })),
      }),
    }),
  );
}

export async function renameBank(id: string, title: string): Promise<QuestionBank> {
  return toBank(
    await request<PaperWire>(`/papers/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  );
}

export async function deleteBank(id: string): Promise<void> {
  await request<void>(`/papers/${id}`, { method: 'DELETE' });
}

// ------------------------------------------------------------
// Export
// ------------------------------------------------------------
export interface ExportResult {
  downloadUrl: string;
  filename: string;
  sizeBytes: number;
}

export async function exportBank(id: string): Promise<ExportResult> {
  const r = await request<{ download_url: string; filename: string; size_bytes: number }>(
    `/export/${id}`,
    { method: 'POST' },
  );
  return { downloadUrl: r.download_url, filename: r.filename, sizeBytes: r.size_bytes };
}

// ------------------------------------------------------------
// Helpers shared by the generation UI
// ------------------------------------------------------------

/** Turn the form's "Mixed" choices into concrete (type, marks, difficulty, count) batches. */
export function planBatches(
  form: {
    questionCount: number;
    questionType: QuestionType | 'Mixed';
    difficulty: Difficulty;
    marksPerQuestion: Marks;
  },
  marksByType: MarksByType,
): { type: QuestionType; marks: Marks; difficulty: QuestionDifficulty; count: number }[] {
  const types: QuestionType[] =
    form.questionType === 'Mixed' ? ['MCQ', 'Short', 'Long'] : [form.questionType];
  const difficulties: QuestionDifficulty[] =
    form.difficulty === 'mixed' ? ['easy', 'medium', 'hard'] : [form.difficulty];

  const marksFor = (t: QuestionType): Marks => {
    const allowed = marksByType[t];
    if (form.questionType !== 'Mixed' && allowed.includes(form.marksPerQuestion)) {
      return form.marksPerQuestion;
    }
    // Mixed: use each type's natural marks value.
    if (t === 'MCQ') return (allowed[0] ?? 1) as Marks;
    if (t === 'Long') return (allowed[allowed.length - 1] ?? 5) as Marks;
    return (allowed.includes(2) ? 2 : allowed[0] ?? 2) as Marks;
  };

  // Spread `count` questions across the (type x difficulty) cells, round-robin.
  const cells = types.flatMap((type) => difficulties.map((difficulty) => ({ type, difficulty })));
  const counts = new Array(cells.length).fill(0);
  for (let i = 0; i < form.questionCount; i++) counts[i % cells.length]++;

  return cells
    .map((c, i) => ({ ...c, marks: marksFor(c.type), count: counts[i] }))
    .filter((b) => b.count > 0);
}
