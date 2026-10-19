import type { Question, QuestionBank } from '../types';

export const makeQuestion = (over: Partial<Question> = {}): Question => ({
  id: 'q1',
  questionNumber: 1,
  subject: 'Science',
  chapter: 'Light',
  grade: 8,
  text: 'Explain how a periscope works.',
  type: 'Short',
  difficulty: 'medium',
  marks: 3,
  topic: '',
  answer: '1. Two mirrors are fixed at 45 degrees.\n2. Light reflects twice.',
  explanation: 'Reflection from plane mirrors.',
  tags: [],
  ...over,
});

export const makeBank = (over: Partial<QuestionBank> = {}): QuestionBank => ({
  id: 'bank-1',
  name: 'Light revision',
  subject: 'Science',
  chapter: 'Light',
  grade: 8,
  questionCount: 1,
  difficulty: 'medium',
  createdAt: '2026-10-01T10:00:00Z',
  totalMarks: 3,
  questions: [makeQuestion()],
  ...over,
});
