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
  options?: string[];       // Only for MCQ
  answer: string;
  explanation: string;
  tags: string[];
}

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
