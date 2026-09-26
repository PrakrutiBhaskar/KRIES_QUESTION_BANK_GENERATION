// ============================================================
// Core domain types for KRIES Question Bank Generation System
// ============================================================

export type Subject = 'Math' | 'Science' | 'Social Science' | 'English' | 'Kannada';
export type Grade = 7 | 8 | 9;
export type QuestionType = 'MCQ' | 'Short' | 'Long';
export type Difficulty = 'easy' | 'medium' | 'hard' | 'mixed';
export type Marks = 1 | 2 | 3 | 5;
export type BloomsLevel =
  | 'Remember'
  | 'Understand'
  | 'Apply'
  | 'Analyse'
  | 'Evaluate'
  | 'Create';

export type QuestionBankStatus = 'draft' | 'published' | 'archived';

// ============================================================
// Question
// ============================================================
export interface Question {
  id: string;
  questionNumber: number;
  text: string;
  type: QuestionType;
  difficulty: 'easy' | 'medium' | 'hard';
  marks: Marks;
  topic: string;
  bloomsLevel: BloomsLevel;
  options?: string[];       // Only for MCQ
  answer: string;
  explanation: string;
  tags: string[];
}

// ============================================================
// Question Bank
// ============================================================
export interface QuestionBank {
  id: string;
  name: string;
  subject: Subject;
  chapter: string;
  description: string;
  grade: Grade;
  questionCount: number;
  difficulty: Difficulty;
  status: QuestionBankStatus;
  createdAt: string;
  updatedAt: string;
  totalMarks: number;
  questions: Question[];
}

// ============================================================
// Generation form
// ============================================================
export interface GenerateFormData {
  name: string;
  subject: Subject;
  chapter: string;
  description: string;
  grade: Grade;
  questionCount: number;
  questionType: QuestionType | 'Mixed';
  difficulty: Difficulty;
  bloomsLevel: BloomsLevel | 'Mixed';
  marksPerQuestion: Marks;
  learningOutcome: string;
}

// ============================================================
// Analytics
// ============================================================
export interface AnalyticsData {
  totalQuestions: number;
  totalQuestionBanks: number;
  totalSubjects: number;
  recentGenerations: number;
  questionsOverTime: { date: string; count: number }[];
  bySubject: { subject: string; count: number }[];
  byDifficulty: { difficulty: string; count: number }[];
  byType: { type: string; count: number }[];
  byBlooms: { level: string; count: number }[];
  byGrade: { grade: string; count: number }[];
}

// ============================================================
// Activity
// ============================================================
export interface Activity {
  id: string;
  type: 'generate' | 'edit' | 'delete' | 'export' | 'create';
  description: string;
  timestamp: string;
  subject?: Subject;
  questionBankName?: string;
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
  defaultBloomsLevel: BloomsLevel | 'Mixed';
  defaultMarks: Marks;
}

// ============================================================
// Syllabus
// ============================================================
export interface SyllabusSubject {
  name: Subject;
  chapters: string[];
}
