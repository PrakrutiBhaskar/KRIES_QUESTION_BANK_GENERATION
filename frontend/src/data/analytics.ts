import type { AnalyticsData, Activity } from '../types';

export const ANALYTICS_DATA: AnalyticsData = {
  totalQuestions: 347,
  totalQuestionBanks: 24,
  totalSubjects: 5,
  recentGenerations: 8,
  questionsOverTime: [
    { date: 'Apr', count: 18 },
    { date: 'May', count: 35 },
    { date: 'Jun', count: 42 },
    { date: 'Jul', count: 28 },
    { date: 'Aug', count: 67 },
    { date: 'Sep', count: 89 },
    { date: 'Oct', count: 68 },
  ],
  bySubject: [
    { subject: 'Science', count: 112 },
    { subject: 'Math', count: 98 },
    { subject: 'Social Science', count: 74 },
    { subject: 'English', count: 42 },
    { subject: 'Kannada', count: 21 },
  ],
  byDifficulty: [
    { difficulty: 'Easy', count: 134 },
    { difficulty: 'Medium', count: 148 },
    { difficulty: 'Hard', count: 65 },
  ],
  byType: [
    { type: 'MCQ', count: 163 },
    { type: 'Short Answer', count: 121 },
    { type: 'Long Answer', count: 63 },
  ],
  byBlooms: [
    { level: 'Remember', count: 68 },
    { level: 'Understand', count: 87 },
    { level: 'Apply', count: 93 },
    { level: 'Analyse', count: 54 },
    { level: 'Evaluate', count: 29 },
    { level: 'Create', count: 16 },
  ],
  byGrade: [
    { grade: 'Grade 7', count: 98 },
    { grade: 'Grade 8', count: 147 },
    { grade: 'Grade 9', count: 102 },
  ],
};

export const RECENT_ACTIVITY: Activity[] = [
  {
    id: 'act-1',
    type: 'generate',
    description: 'Generated 5 questions for Photosynthesis',
    timestamp: '2026-09-26T23:00:00Z',
    subject: 'Science',
    questionBankName: 'Photosynthesis — Grade 8 Comprehensive',
  },
  {
    id: 'act-2',
    type: 'edit',
    description: 'Edited question in Linear Equations Practice Set',
    timestamp: '2026-09-26T21:30:00Z',
    subject: 'Math',
    questionBankName: 'Linear Equations Practice Set',
  },
  {
    id: 'act-3',
    type: 'create',
    description: 'Created new question bank: Revolt of 1857',
    timestamp: '2026-09-26T19:15:00Z',
    subject: 'Social Science',
    questionBankName: 'Revolt of 1857 — Key Concepts',
  },
  {
    id: 'act-4',
    type: 'export',
    description: 'Exported PDF for Metals and Non-metals question bank',
    timestamp: '2026-09-26T17:00:00Z',
    subject: 'Science',
    questionBankName: 'Metals and Non-metals — Mixed',
  },
  {
    id: 'act-5',
    type: 'delete',
    description: 'Deleted 2 duplicate questions from Gravitation bank',
    timestamp: '2026-09-25T14:45:00Z',
    subject: 'Science',
    questionBankName: 'Gravitation — Hard Problems',
  },
  {
    id: 'act-6',
    type: 'generate',
    description: 'Generated 8 questions for Comprehension — A Triumph of Surgery',
    timestamp: '2026-09-25T11:00:00Z',
    subject: 'English',
    questionBankName: 'A Triumph of Surgery — Comprehension',
  },
];
