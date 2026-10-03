// ============================================================
// Core domain types for KRIES Question Bank Generation System
// These mirror the backend's shared Question contract
// (docs/api-contract.md) plus a few UI-only view models.
// ============================================================

export type Subject = 'Math' | 'Science' | 'Social Science' | 'English' | 'Kannada';
export type Grade = 7 | 8 | 9;
export type QuestionType = 'MCQ' | 'Short' | 'Long';
export type Difficulty = 'easy' | 'medium' | 'hard' | 'mixed';
export type QuestionDifficulty = Exclude<Difficulty, 'mixed'>;
export type Marks = 1 | 2 | 3 | 5;

// ============================================================
// Question (UI view of the backend's QuestionOut)
// ============================================================
/** A diagram attached to a question. The image itself is fetched with the user's token. */
export interface Figure {
  id: string;
  caption: string;
  mime: string;
  width: number;
  height: number;
  sizeBytes: number;
}

/** A figure in the shared library: the image info plus what question generation writes from. */
export interface LibraryFigure extends Figure {
  subject?: Subject;
  chapter?: string;
  topic: string;
  /** The labelled parts, e.g. "A: nucleus". Students never receive these (they are an answer key). */
  labels: string[];
}

export interface Question {
  id: string;
  questionNumber: number;   // 1-based position within the list being shown
  subject: Subject;
  chapter: string;
  grade: Grade;
  text: string;
  type: QuestionType;
  difficulty: QuestionDifficulty;
  marks: Marks;
  baseMarks?: Marks;        // the question's own marks when a paper overrides them
  topic: string;
  section?: string;         // "Section A" ... — only on blueprint papers
  options?: string[];       // Only for MCQ
  answer: string;
  explanation: string;
  tags: string[];
  // Answer-key check done at generation time (rule check or an independent AI pass).
  verificationStatus?: VerificationStatus;
  verificationNote?: string;
  figure?: Figure;          // printed with the question in the paper
  answerFigure?: Figure;    // printed only in the answer key
}

/** verified: confirmed · unverified: could not be checked · flagged: the key looked wrong */
export type VerificationStatus = 'verified' | 'unverified' | 'flagged';

// ============================================================
// Question Bank
// A "question bank" is a saved Paper on the backend: a titled, ordered set of
// stored questions for one subject. Chapter / grade / difficulty are derived
// from the questions it contains.
// ============================================================
export interface QuestionBank {
  id: string;
  name: string;
  subject: Subject;
  chapter: string;          // the chapter, or "Multiple chapters"
  grade: Grade;
  questionCount: number;
  difficulty: Difficulty;   // 'mixed' when the questions differ
  createdAt: string;
  totalMarks: number;
  questions: Question[];
}

// ============================================================
// Generation form
// ============================================================
export interface GenerateFormData {
  subject: Subject;
  chapter: string;
  grade: Grade;
  questionCount: number;
  questionType: QuestionType | 'Mixed';
  difficulty: Difficulty;
  marksPerQuestion: Marks;
  fresh: boolean;           // skip stored questions and force new generation
}

// ============================================================
// User / Auth
// ============================================================
export interface User {
  id: string;
  name: string;
  email: string;
  role: 'Teacher' | 'Student' | 'Admin';
  avatar?: string;
}

// ============================================================
// Settings
// ============================================================
export interface AppSettings {
  theme: 'light' | 'dark' | 'system';
  notifications: boolean;
  defaultQuestionCount: number;
  defaultDifficulty: Difficulty;
  defaultQuestionType: QuestionType | 'Mixed';
  defaultMarks: Marks;
}

// ============================================================
// Syllabus
// ============================================================
export interface ChapterInfo {
  id: string;
  name: string;
  orderIndex: number;
  questionCount: number;
}

// (type -> allowed marks), from GET /generation/combinations
export type MarksByType = Record<QuestionType, Marks[]>;

// ============================================================
// Blueprint papers (Question Papers page)
// ============================================================
export interface BlueprintChapter {
  name: string;
  weightage: number;        // percent of the paper's total marks
}

export interface BlueprintSection {
  name: string;
  type: QuestionType;
  marksPerQuestion: Marks;
  totalMarks: number;       // what the whole section is worth
  difficulty: Difficulty;
}

export interface BlueprintInput {
  title: string;
  subject: Subject;
  grade: Grade;
  chapters: BlueprintChapter[];
  sections: BlueprintSection[];
  refresh: boolean;
}

/** What a blueprint would produce, worked out by the server without generating. */
export interface BlueprintPlan {
  totalMarks: number;
  totalQuestions: number;
  sections: {
    name: string;
    type: QuestionType;
    marksPerQuestion: number;
    questions: number;
    marks: number;
    allocations: { chapter: string; questions: number; marks: number }[];
  }[];
  chapters: {
    chapter: string;
    weightage: number;
    targetMarks: number;
    plannedMarks: number;
    plannedQuestions: number;
  }[];
}
