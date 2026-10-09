// ============================================================
// Typed client for the FastAPI backend (docs/api-contract.md).
// Every endpoint returns errors as {"error": string, "detail": string}.
// ============================================================
import { UNAUTHORIZED_EVENT, clearSession, getToken } from './auth';
import type {
  BlueprintInput,
  Figure,
  LibraryFigure,
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
  AppSettings,
  VerificationStatus,
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
  // A FormData body (file upload) needs the browser to set its own multipart
  // Content-Type, boundary included, so only JSON bodies get one here.
  if (init.body && !(init.body instanceof FormData)) headers['Content-Type'] = 'application/json';
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
interface FigureWire {
  id: string;
  caption: string;
  mime: string;
  width: number;
  height: number;
  size_bytes: number;
  // Only present on figure-library endpoints, and only filled in for administrators and teachers.
  subject?: Subject | null;
  chapter?: string | null;
  topic?: string;
  labels?: string[];
}

function toLibraryFigure(f: FigureWire): LibraryFigure {
  return {
    ...toFigure(f)!,
    subject: f.subject ?? undefined,
    chapter: f.chapter ?? undefined,
    topic: f.topic ?? '',
    labels: f.labels ?? [],
  };
}

function toFigure(f: FigureWire | null | undefined): Figure | undefined {
  if (!f) return undefined;
  return {
    id: f.id,
    caption: f.caption,
    mime: f.mime,
    width: f.width,
    height: f.height,
    sizeBytes: f.size_bytes,
  };
}

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
  verification_status?: VerificationStatus;
  verification_note?: string | null;
  /** Present only when a figure is attached. */
  figure?: FigureWire | null;
  answer_figure?: FigureWire | null;
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
    verificationStatus: q.verification_status ?? 'unverified',
    verificationNote: q.verification_note ?? undefined,
    figure: toFigure(q.figure),
    answerFigure: toFigure(q.answer_figure),
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
  /** The user's saved preferences (defaults for an account that never saved any). */
  settings: AppSettings;
}

interface PreferencesWire {
  theme: AppSettings['theme'];
  notifications: boolean;
  default_question_count: number;
  default_difficulty: AppSettings['defaultDifficulty'];
  default_question_type: AppSettings['defaultQuestionType'];
  default_marks: AppSettings['defaultMarks'];
}

interface UserWire extends User {
  preferences: PreferencesWire;
}

interface TokenWire {
  access_token: string;
  user: UserWire;
}

function settingsFromWire(p: PreferencesWire): AppSettings {
  return {
    theme: p.theme,
    notifications: p.notifications,
    defaultQuestionCount: p.default_question_count,
    defaultDifficulty: p.default_difficulty,
    defaultQuestionType: p.default_question_type,
    defaultMarks: p.default_marks,
  };
}

function settingsToWire(s: Partial<AppSettings>): Partial<PreferencesWire> {
  const out: Partial<PreferencesWire> = {};
  if (s.theme !== undefined) out.theme = s.theme;
  if (s.notifications !== undefined) out.notifications = s.notifications;
  if (s.defaultQuestionCount !== undefined) out.default_question_count = s.defaultQuestionCount;
  if (s.defaultDifficulty !== undefined) out.default_difficulty = s.defaultDifficulty;
  if (s.defaultQuestionType !== undefined) out.default_question_type = s.defaultQuestionType;
  if (s.defaultMarks !== undefined) out.default_marks = s.defaultMarks;
  return out;
}

/** Split the server's user object into the account (cached for the session) and the preferences. */
function splitUser(w: UserWire): { user: User; settings: AppSettings } {
  const { preferences, ...user } = w;
  return { user, settings: settingsFromWire(preferences) };
}

export async function signUp(input: SignUpInput): Promise<AuthResult> {
  const r = await request<TokenWire>(
    '/auth/signup',
    { method: 'POST', body: JSON.stringify(input) },
    15000,
    { auth: false },
  );
  return { token: r.access_token, ...splitUser(r.user) };
}

export async function signIn(email: string, password: string): Promise<AuthResult> {
  const r = await request<TokenWire>(
    '/auth/login',
    { method: 'POST', body: JSON.stringify({ email, password }) },
    15000,
    { auth: false },
  );
  return { token: r.access_token, ...splitUser(r.user) };
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
export async function fetchMe(): Promise<{ user: User; settings: AppSettings }> {
  return splitUser(await request<UserWire>('/auth/me', {}, 15000));
}

export interface ProfileChanges {
  name?: string;
  role?: 'Teacher' | 'Student';
  settings?: Partial<AppSettings>;
}

/** Save profile and/or preference changes to the database. The email can't be changed. */
export async function updateProfile(
  changes: ProfileChanges,
): Promise<{ user: User; settings: AppSettings }> {
  const body: Record<string, unknown> = {};
  if (changes.name !== undefined) body.name = changes.name;
  if (changes.role !== undefined) body.role = changes.role;
  if (changes.settings !== undefined) body.preferences = settingsToWire(changes.settings);
  return splitUser(
    await request<UserWire>('/auth/me', { method: 'PATCH', body: JSON.stringify(body) }, 15000),
  );
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
  const out: MarksByType = { MCQ: [], Short: [], Long: [], Fill: [], Match: [] };
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
  /** Write the questions about figures from your library (matched on subject + chapter). */
  useFigures?: boolean;
  /** Or name exact figures; implies useFigures. */
  figureIds?: string[];
  /** Let the server randomly make some of the questions diagram-based (theory when the chapter has no figures). */
  mixFigures?: boolean;
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
  if (p.figureIds?.length) body.figure_ids = p.figureIds;
  else if (p.useFigures) body.use_figures = true;
  else if (p.mixFigures) body.mix_figures = true;

  const res = await request<GenerateWire>('/generate', { method: 'POST', body: JSON.stringify(body) });
  return {
    questions: res.questions.map(toQuestion),
    cached: res.cached,
    generated: res.generated,
  };
}

// ------------------------------------------------------------
// Answer verification (the "Verify answers" button)
// ------------------------------------------------------------
interface VerifyWire {
  questions: QuestionWire[];
  verified: number;
  unverified: number;
  flagged: number;
}

export interface VerifyResult {
  questions: Question[];
  verified: number;
  unverified: number;
  flagged: number;
}

// POST /questions/verify accepts at most this many ids per call.
const VERIFY_BATCH = 50;

/** Check the answer keys of stored questions. Generation never does this; it only happens on request. */
export async function verifyAnswers(ids: string[]): Promise<VerifyResult> {
  const out: VerifyResult = { questions: [], verified: 0, unverified: 0, flagged: 0 };
  for (let i = 0; i < ids.length; i += VERIFY_BATCH) {
    const res = await request<VerifyWire>('/questions/verify', {
      method: 'POST',
      body: JSON.stringify({ question_ids: ids.slice(i, i + VERIFY_BATCH) }),
    });
    out.questions.push(...res.questions.map(toQuestion));
    out.verified += res.verified;
    out.unverified += res.unverified;
    out.flagged += res.flagged;
  }
  return out;
}

// ------------------------------------------------------------
// Questions
// ------------------------------------------------------------
export interface QuestionEdit {
  text?: string;
  // No `answer`: the answer key is read-only (it is checked by "Verify answers").
  explanation?: string;
  options?: string[];
  marks?: number;
  difficulty?: QuestionDifficulty;
  topic?: string;
  tags?: string[];
  /** Attach a figure from the library, or null to detach. Sent as-is (snake_case). */
  figure_id?: string | null;
  answer_figure_id?: string | null;
}

export async function updateQuestion(id: string, changes: QuestionEdit): Promise<Question> {
  const q = await request<QuestionWire>(`/questions/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
  return toQuestion(q, 0);
}

// ------------------------------------------------------------
// Figures (diagrams attached to questions / answer keys)
// ------------------------------------------------------------
/** The shared figure library, newest first; optionally only figures tagged with a subject / chapter. */
export async function fetchFigureLibrary(
  filter: { subject?: Subject; chapter?: string } = {},
): Promise<LibraryFigure[]> {
  const q = new URLSearchParams({ page_size: '100' });
  if (filter.subject) q.set('subject', filter.subject);
  if (filter.chapter) q.set('chapter', filter.chapter);
  const page = await request<{ results: FigureWire[] }>(`/figures?${q}`);
  return page.results.map(toLibraryFigure);
}

/** What an administrator fills in when adding or editing a figure. */
export interface FigureInput {
  caption: string;
  subject: Subject | '';
  chapter: string;
  topic: string;
  /** One labelled part per entry, e.g. "A: nucleus". */
  labels: string[];
}

/** Add a diagram to the library (administrators only; anyone else gets a 403). */
export async function uploadFigure(file: File, meta: FigureInput): Promise<LibraryFigure> {
  const body = new FormData();
  body.append('file', file);
  body.append('caption', meta.caption);
  body.append('subject', meta.subject);
  body.append('chapter', meta.chapter);
  body.append('topic', meta.topic);
  body.append('labels', meta.labels.join('\n'));
  // Uploads can be several MB, so allow longer than the default timeout.
  return toLibraryFigure(await request<FigureWire>('/figures', { method: 'POST', body }, 60000));
}

/** Change a figure's caption / tags / labelled parts (administrators only). */
export async function updateFigure(id: string, meta: FigureInput): Promise<LibraryFigure> {
  return toLibraryFigure(
    await request<FigureWire>(`/figures/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        caption: meta.caption,
        subject: meta.subject || null,
        chapter: meta.chapter,
        topic: meta.topic,
        labels: meta.labels,
      }),
    }),
  );
}

/** Remove a figure nothing uses (administrators only; 409 while a question still prints it). */
export async function deleteFigure(id: string): Promise<void> {
  await request<void>(`/figures/${id}`, { method: 'DELETE' });
  figureUrlCache.delete(id);
}

// An <img src> cannot send the Authorization header, so the bytes are fetched
// with it and shown through an object URL. A figure's bytes never change, so
// each one is fetched once per session.
const figureUrlCache = new Map<string, Promise<string>>();

export function fetchFigureUrl(id: string): Promise<string> {
  let cached = figureUrlCache.get(id);
  if (!cached) {
    cached = (async () => {
      const token = getToken();
      const res = await fetch(`${API_BASE}/figures/${id}/file`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new ApiError(res.status, 'figure_unavailable', 'Could not load the figure.');
      return URL.createObjectURL(await res.blob());
    })();
    figureUrlCache.set(id, cached);
    // Don't cache a failure: let the next render try again.
    cached.catch(() => figureUrlCache.delete(id));
  }
  return cached;
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

interface BlueprintJobWire {
  id: string;
  status: 'running' | 'done' | 'error';
  done: number;
  total: number;
  paper: PaperWire | null;
  error: string | null;
  detail: string | null;
  error_status: number | null;
}

/** How far a paper build has got: questions gathered out of the number needed. */
export interface BlueprintProgress {
  done: number;
  total: number;
}

const JOB_POLL_MS = 1500;
const JOB_GIVE_UP_MS = 15 * 60 * 1000;
const JOB_MAX_POLL_FAILURES = 5;

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * Build and save a paper from a blueprint, reporting progress as it goes.
 *
 * Starts the build as a background job on the server and polls it, so the page
 * can show "N of M questions created" instead of a spinner. Same result and same
 * all-or-nothing behaviour as createBlueprintPaper. If `signal` aborts (the
 * page was closed) polling stops; the server finishes the paper regardless and
 * it shows up in Question Banks.
 */
export async function buildBlueprintPaper(
  b: BlueprintInput,
  onProgress: (p: BlueprintProgress) => void,
  signal?: AbortSignal,
): Promise<QuestionBank> {
  let job = await request<BlueprintJobWire>(
    '/papers/blueprint/jobs',
    { method: 'POST', body: JSON.stringify(blueprintBody(b)) },
    30000,
  );
  onProgress({ done: job.done, total: job.total });

  const startedAt = Date.now();
  let failures = 0;
  while (job.status === 'running') {
    await sleep(JOB_POLL_MS);
    if (signal?.aborted) throw new ApiError(0, 'cancelled', 'Cancelled.');
    if (Date.now() - startedAt > JOB_GIVE_UP_MS) {
      throw new ApiError(0, 'timeout', 'Building the paper is taking too long. Check Question Banks in a few minutes.');
    }
    try {
      job = await request<BlueprintJobWire>(`/papers/blueprint/jobs/${job.id}`, {}, 15000);
      failures = 0;
    } catch (err) {
      // A dropped request or a timeout is not the build failing; try again a few times.
      const transient = err instanceof TypeError || (err instanceof ApiError && err.code === 'timeout');
      if (!transient || ++failures >= JOB_MAX_POLL_FAILURES) throw err;
      continue;
    }
    onProgress({ done: job.done, total: job.total });
  }

  if (job.status === 'error') {
    throw new ApiError(job.error_status ?? 500, job.error ?? 'error', job.detail ?? 'Building the paper failed.');
  }
  return toBank(job.paper as PaperWire);
}

// ------------------------------------------------------------
// Export
// ------------------------------------------------------------
export interface ExportResult {
  downloadUrl: string;
  filename: string;
  sizeBytes: number;
}

export interface ExportOptions {
  /** Append the Answer Key pages. Defaults to true, matching the server. */
  includeAnswerKey?: boolean;
}

export async function exportBank(id: string, opts: ExportOptions = {}): Promise<ExportResult> {
  const r = await request<{ download_url: string; filename: string; size_bytes: number }>(
    `/export/${id}`,
    {
      method: 'POST',
      body: JSON.stringify({ include_answer_key: opts.includeAnswerKey ?? true }),
    },
  );
  return { downloadUrl: r.download_url, filename: r.filename, sizeBytes: r.size_bytes };
}

// ------------------------------------------------------------
// Helpers shared by the generation UI
// ------------------------------------------------------------

export const ALL_QUESTION_TYPES: QuestionType[] = ['MCQ', 'Short', 'Long', 'Fill', 'Match'];

/**
 * The marks a type will be generated with: the user's choice if the type allows
 * it, else `preferred` (a saved default; only passed for a single-type request),
 * else the type's natural value (MCQ/Fill the lowest, Long the highest, others 2).
 */
export function effectiveMarks(
  type: QuestionType,
  allowed: Marks[],
  chosen?: Marks,
  preferred?: Marks,
): Marks {
  if (chosen !== undefined && allowed.includes(chosen)) return chosen;
  if (preferred !== undefined && allowed.includes(preferred)) return preferred;
  if (type === 'MCQ' || type === 'Fill') return (allowed[0] ?? 1) as Marks;
  if (type === 'Long') return (allowed[allowed.length - 1] ?? 5) as Marks;
  return (allowed.includes(2) ? 2 : allowed[0] ?? 2) as Marks;
}

/**
 * Every marks value a type will be generated with: the user's picks that the
 * type allows (kept in the type's own order), else the single `effectiveMarks`
 * fallback. Never empty.
 */
export function effectiveMarksList(
  type: QuestionType,
  allowed: Marks[],
  chosen?: Marks[],
  preferred?: Marks,
): Marks[] {
  const picked = allowed.filter((m) => chosen?.includes(m));
  return picked.length > 0 ? picked : [effectiveMarks(type, allowed, undefined, preferred)];
}

/**
 * Turn the form into concrete (type, marks, difficulty, count) batches: `count`
 * questions spread round-robin over every (type x difficulty) cell, varying the
 * type fastest so even a small count touches every chosen type. Within a cell the
 * questions rotate through that type's chosen marks values, so picking several
 * marks for a type gives a mix of them.
 */
export function planBatches(
  form: {
    questionCount: number;
    questionTypes: QuestionType[];
    difficulty: Difficulty;
    marksChoice: Partial<Record<QuestionType, Marks[]>>;
  },
  marksByType: MarksByType,
  preferredMarks?: Marks,
): { type: QuestionType; marks: Marks; difficulty: QuestionDifficulty; count: number }[] {
  const types = ALL_QUESTION_TYPES.filter((t) => form.questionTypes.includes(t));
  const difficulties: QuestionDifficulty[] =
    form.difficulty === 'mixed' ? ['easy', 'medium', 'hard'] : [form.difficulty];
  const preferred = types.length === 1 ? preferredMarks : undefined;

  const cells = difficulties.flatMap((difficulty) =>
    types.map((type) => ({
      type,
      difficulty,
      marksList: effectiveMarksList(type, marksByType[type], form.marksChoice[type], preferred),
    })),
  );
  // tally[cell][marks] = questions of that marks value in that cell
  const tally: Map<Marks, number>[] = cells.map(() => new Map());
  const used = new Array(cells.length).fill(0);
  for (let i = 0; i < form.questionCount; i++) {
    const ci = i % cells.length;
    const m = cells[ci].marksList[used[ci]++ % cells[ci].marksList.length];
    tally[ci].set(m, (tally[ci].get(m) ?? 0) + 1);
  }

  const diffOrder: QuestionDifficulty[] = ['easy', 'medium', 'hard'];
  const batches = cells.flatMap((c, ci) =>
    c.marksList
      .filter((m) => tally[ci].has(m))
      .map((m) => ({ type: c.type, marks: m, difficulty: c.difficulty, count: tally[ci].get(m) as number })),
  );
  // Section-wise: all 1-mark questions first, then 2-mark, 3-mark, 5-mark; within a
  // section by type, then easy -> hard.
  return batches.sort(
    (a, b) =>
      a.marks - b.marks ||
      ALL_QUESTION_TYPES.indexOf(a.type) - ALL_QUESTION_TYPES.indexOf(b.type) ||
      diffOrder.indexOf(a.difficulty) - diffOrder.indexOf(b.difficulty),
  );
}

/** Stable sort of questions into marks sections (1, 2, 3, 5), keeping their order within a section. */
export function sortByMarks<T extends { marks: number }>(questions: T[]): T[] {
  return questions
    .map((q, i) => ({ q, i }))
    .sort((a, b) => a.q.marks - b.q.marks || a.i - b.i)
    .map((x) => x.q);
}
