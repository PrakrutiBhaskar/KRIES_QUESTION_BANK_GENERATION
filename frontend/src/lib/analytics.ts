import type { AnalyticsData, Question } from '../types';

const SUBJECT_ORDER = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];

function countBy<T>(items: T[], key: (item: T) => string): Map<string, number> {
  const m = new Map<string, number>();
  for (const it of items) m.set(key(it), (m.get(key(it)) ?? 0) + 1);
  return m;
}

/** Aggregate stored questions into the shapes the charts use. */
export function buildAnalytics(
  questions: Question[],
  total: number,
  bankCount: number,
): AnalyticsData {
  const bySubject = countBy(questions, (q) => q.subject);
  const byDiff = countBy(questions, (q) => q.difficulty);
  const byType = countBy(questions, (q) => q.type);
  const byGrade = countBy(questions, (q) => `Grade ${q.grade}`);
  const byMarks = countBy(questions, (q) => `${q.marks} mark${q.marks > 1 ? 's' : ''}`);

  return {
    totalQuestions: total,
    totalQuestionBanks: bankCount,
    subjectsCovered: bySubject.size,
    bySubject: SUBJECT_ORDER.filter((s) => bySubject.has(s)).map((s) => ({ subject: s, count: bySubject.get(s)! })),
    byDifficulty: ['easy', 'medium', 'hard'].map((d) => ({ difficulty: d, count: byDiff.get(d) ?? 0 })),
    byType: [
      { type: 'MCQ', count: byType.get('MCQ') ?? 0 },
      { type: 'Short Answer', count: byType.get('Short') ?? 0 },
      { type: 'Long Answer', count: byType.get('Long') ?? 0 },
    ],
    byGrade: ['Grade 7', 'Grade 8', 'Grade 9'].map((g) => ({ grade: g, count: byGrade.get(g) ?? 0 })),
    byMarks: ['1 mark', '2 marks', '3 marks', '5 marks'].map((m) => ({ marks: m, count: byMarks.get(m) ?? 0 })),
    truncated: questions.length < total,
  };
}
