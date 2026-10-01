// ============================================================
// Typed client for the FastAPI backend (docs/api-contract.md).
// Every endpoint returns errors as {"error": string, "detail": string}.
// ============================================================
import { UNAUTHORIZED_EVENT, clearSession, getToken } from './auth';
import type {
  BlueprintInput,
  BlueprintPlan,
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
  User,
} from '../types';

export const API_BASE: string = (import.meta.env.VITE_API_BASE_URL ?? '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  status: number;
  code: string;
  /** Seconds to wait before retrying, for a 429 (rate limited) response. */
  retryAfter?: number;
  constructor(status: number, code: string, detail: string, retryAfter?: number) {
    super(detail || code);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
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
  if (err instanceof TypeError) return 'Cannot reach the server. Please check your connection and try again.';
  return err instanceof Error ? err.message : 'Something went wrong.';
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs?: number,
  { auth = true }: { auth?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (init.body) headers['Content-Type'] = 'application/json';
  const token = auth ? getToken() : null;
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { ...headers, ...init.headers },
      signal: timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'TimeoutError') {
      throw new ApiError(0, 'timeout', 'The server took too long to respond. Please try again.');
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
    // A token we sent was rejected (expired / revoked): drop the session so the
    // app returns to the sign-in page instead of failing every request.
    if (res.status === 401 && token) {
      clearSession();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    const retryAfter = Number(res.headers.get('Retry-After'));
    throw new ApiError(
      res.status,
      b.error ?? 'error',
      detail,
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : undefined,
    );
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
  questions: {
    order_index: number;
    marks: number;
    marks_override: number | null;
    section?: string | null;
    question: QuestionWire;
  }[];
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
    section: item.section ?? undefined,
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
// Auth
// ------------------------------------------------------------
export interface SignUpInput {
  name: string;
  email: string;
  password: string;
  role: 'Teacher' | 'Student';
}

export interface AuthResult {
  token: string;
  user: User;
}

interface TokenWire {
  access_token: string;
  user: User;
}

export async function signUp(input: SignUpInput): Promise<AuthResult> {
  const r = await request<TokenWire>(
    '/auth/signup',
    { method: 'POST', body: JSON.stringify(input) },
    15000,
    { auth: false },
  );
  return { token: r.access_token, user: r.user };
}

export async function signIn(email: string, password: string): Promise<AuthResult> {
  const r = await request<TokenWire>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    15000,
    { auth: false },
  );
  return { token: r.access_token, user: r.user };
}

/** Ask for a password-reset email. The reply is the same whether or not the account exists. */
export async function requestPasswordReset(email: string): Promise<string> {
  const r = await request<{ message: string }>(
    '/auth/forgot-password',
    { method: 'POST', body: JSON.stringify({ email }) },
    15000,
    { auth: false },
  );
  return r.message;
}

/** Set a new password using the token from the emailed link. */
export async function resetPassword(token: string, password: string): Promise<string> {
  const r = await request<{ message: string }>(
    '/auth/reset-password',
    { method: 'POST', body: JSON.stringify({ token, password }) },
    15000,
    { auth: false },
  );
  return r.message;
}

/** The signed-in user; also how a stored token is validated on page load. */
export async function fetchMe(): Promise<User> {
  return request<User>('/auth/me', {}, 15000);
}

// ------------------------------------------------------------
// Syllabus
// ------------------------------------------------------------
export async function fetchChapters(subject: Subject, grade?: number): Promise<ChapterInfo[]> {
  const query = grade ? `?grade=${grade}` : '';
  const rows = await request<{ id: string; name: string; order_index: number; question_count: number }[]>(
    `/subjects/${encodeURIComponent(subject)}/chapters${query}`,
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
// Blueprint papers
// ------------------------------------------------------------
function blueprintBody(b: BlueprintInput): Record<string, unknown> {
  return {
    title: b.title.trim() || null,
    subject: b.subject,
    grade: b.grade,
    chapters: b.chapters.map((c) => ({ name: c.name, weightage: c.weightage })),
    sections: b.sections.map((s) => ({
      name: s.name,
      type: s.type,
      marks_per_question: s.marksPerQuestion,
      total_marks: s.totalMarks,
      difficulty: s.difficulty,
    })),
    refresh: b.refresh,
  };
}

interface BlueprintPlanWire {
  total_marks: number;
  total_questions: number;
  sections: {
    name: string;
    type: QuestionType;
    marks_per_question: number;
    questions: number;
    marks: number;
    allocations: { chapter: string; questions: number; marks: number }[];
  }[];
  chapters: {
    chapter: string;
    weightage: number;
    target_marks: number;
    planned_marks: number;
    planned_questions: number;
  }[];
}

/** How the blueprint's marks would be split across chapters. Calls no LLM. */
export async function previewBlueprint(b: BlueprintInput): Promise<BlueprintPlan> {
  const r = await request<BlueprintPlanWire>(
    '/papers/blueprint/preview',
    { method: 'POST', body: JSON.stringify(blueprintBody(b)) },
    15000,
  );
  return {
    totalMarks: r.total_marks,
    totalQuestions: r.total_questions,
    sections: r.sections.map((s) => ({
      name: s.name,
      type: s.type,
      marksPerQuestion: s.marks_per_question,
      questions: s.questions,
      marks: s.marks,
      allocations: s.allocations,
    })),
    chapters: r.chapters.map((c) => ({
      chapter: c.chapter,
      weightage: c.weightage,
      targetMarks: c.target_marks,
      plannedMarks: c.planned_marks,
      plannedQuestions: c.planned_questions,
    })),
  };
}

/**
 * Build and save a paper from a blueprint. Reuses stored questions and
 * generates the rest, so a large paper can take a while — hence the long timeout.
 */
export async function createBlueprintPaper(b: BlueprintInput): Promise<QuestionBank> {
  return toBank(
    await request<PaperWire>(
      '/papers/blueprint',
      { method: 'POST', body: JSON.stringify(blueprintBody(b)) },
      5 * 60 * 1000,
    ),
  );
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
