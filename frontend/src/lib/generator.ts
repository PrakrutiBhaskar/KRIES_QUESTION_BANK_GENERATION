import type {
  Question,
  QuestionType,
  BloomsLevel,
  Marks,
  Subject,
  GenerateFormData,
} from '../types';

// ============================================================
// Realistic question templates per subject/type
// ============================================================

interface QuestionTemplate {
  textFn: (chapter: string) => string;
  type: QuestionType;
  answerFn: (chapter: string) => string;
  explanation: string;
  optionsFn?: (chapter: string) => string[];
  bloomsLevel: BloomsLevel;
}

const MCQ_TEMPLATES: QuestionTemplate[] = [
  {
    textFn: (chapter) => `Which of the following best describes "${chapter}"?`,
    type: 'MCQ',
    answerFn: (chapter) => `The systematic study of ${chapter} principles`,
    optionsFn: (chapter) => [
      `The systematic study of ${chapter} principles`,
      `A historical overview of ${chapter}`,
      `A mathematical formula related to ${chapter}`,
      `An experimental method for ${chapter}`,
    ],
    explanation: 'This option accurately captures the core definition as per the Karnataka State Board curriculum.',
    bloomsLevel: 'Remember',
  },
  {
    textFn: (chapter) => `What is the primary significance of studying "${chapter}" in the Karnataka State Board curriculum?`,
    type: 'MCQ',
    answerFn: () => 'It builds foundational understanding required for higher-grade concepts',
    optionsFn: () => [
      'It builds foundational understanding required for higher-grade concepts',
      'It is only relevant for competitive examinations',
      'It has no practical application in daily life',
      'It is an optional topic not tested in board exams',
    ],
    explanation: 'The chapter forms a key foundational concept that is built upon in subsequent grades.',
    bloomsLevel: 'Understand',
  },
  {
    textFn: (chapter) => `In the context of "${chapter}", which statement is CORRECT?`,
    type: 'MCQ',
    answerFn: (chapter) => `${chapter} follows established scientific/mathematical principles`,
    optionsFn: (chapter) => [
      `${chapter} follows established scientific/mathematical principles`,
      `${chapter} contradicts classical theory`,
      `${chapter} was discovered in the 21st century`,
      `${chapter} is not relevant to the Indian context`,
    ],
    explanation: 'This is consistent with the standard academic definition as per the Karnataka State Board.',
    bloomsLevel: 'Apply',
  },
];

const SHORT_TEMPLATES: QuestionTemplate[] = [
  {
    textFn: (chapter) => `Define the key concept studied in "${chapter}" and give one example.`,
    type: 'Short',
    answerFn: (chapter) =>
      `"${chapter}" refers to the study of fundamental principles and their real-world applications. For example, these principles are applied in everyday situations encountered by students in Karnataka schools.`,
    explanation: 'A brief, focused definition with one concrete example is expected for a 2-mark question.',
    bloomsLevel: 'Understand',
  },
  {
    textFn: (chapter) => `State two important facts about "${chapter}".`,
    type: 'Short',
    answerFn: (chapter) =>
      `1. "${chapter}" is a fundamental chapter in the Karnataka State Board curriculum that introduces students to core concepts.\n2. The principles of "${chapter}" have wide applications in science, technology, and daily life.`,
    explanation: 'Two clearly stated, distinct facts are required for full marks.',
    bloomsLevel: 'Remember',
  },
];

const LONG_TEMPLATES: QuestionTemplate[] = [
  {
    textFn: (chapter) => `Explain the three main aspects of "${chapter}" with suitable examples.`,
    type: 'Long',
    answerFn: (chapter) =>
      `1. Definition and Background:\n"${chapter}" encompasses the fundamental principles that govern this area of study. It was systematically developed to explain observed phenomena.\n\n2. Key Principles:\nThe subject involves several interrelated concepts that build upon each other. Students must understand the cause-and-effect relationships within the topic.\n\n3. Real-World Applications:\nThe concepts from "${chapter}" are applied in various fields including technology, medicine, and everyday problem-solving, making it highly relevant for Grade 7–9 students.`,
    explanation: 'A 3-mark answer should cover exactly 3 distinct, well-elaborated points.',
    bloomsLevel: 'Analyse',
  },
  {
    textFn: (chapter) => `Discuss the importance of "${chapter}" in modern education. How does it connect to other chapters in the curriculum?`,
    type: 'Long',
    answerFn: (chapter) =>
      `Introduction:\n"${chapter}" is one of the most important chapters for Grade 8–9 students in the Karnataka State Board curriculum.\n\nImportance:\n• It establishes foundational knowledge necessary for understanding advanced topics.\n• It develops critical thinking and analytical skills.\n• It connects theoretical learning to practical, real-world scenarios.\n\nConnections to Other Chapters:\n• This chapter builds on concepts introduced in lower grades.\n• Its principles are extended and applied in subsequent chapters.\n• Understanding this topic is essential for successfully mastering related chapters.\n\nConclusion:\nA thorough understanding of "${chapter}" enables students to excel not only in board examinations but also in future academic and professional pursuits.`,
    explanation: 'A 5-mark answer requires a structured, multi-paragraph response with introduction, body, and conclusion.',
    bloomsLevel: 'Evaluate',
  },
];

// ============================================================
// Mock question generator
// ============================================================

export function generateMockQuestions(formData: GenerateFormData): Question[] {
  const {
    chapter,
    questionCount,
    questionType,
    difficulty,
    bloomsLevel,
    marksPerQuestion,
  } = formData;

  const questions: Question[] = [];
  const difficulties: Array<'easy' | 'medium' | 'hard'> =
    difficulty === 'mixed' ? ['easy', 'medium', 'hard'] : [difficulty as 'easy' | 'medium' | 'hard'];
  const types: QuestionType[] =
    questionType === 'Mixed' ? ['MCQ', 'Short', 'Long'] : [questionType as QuestionType];
  const blooms: BloomsLevel[] =
    bloomsLevel === 'Mixed'
      ? ['Remember', 'Understand', 'Apply', 'Analyse', 'Evaluate', 'Create']
      : [bloomsLevel as BloomsLevel];

  const subjectTopics: Record<Subject, string[]> = {
    Math: ['Algebra', 'Geometry', 'Arithmetic', 'Statistics', 'Mensuration'],
    Science: ['Biology', 'Chemistry', 'Physics', 'Environmental Science'],
    'Social Science': ['History', 'Geography', 'Civics', 'Economics'],
    English: ['Comprehension', 'Grammar', 'Literature', 'Writing Skills'],
    Kannada: ['ವ್ಯಾಕರಣ', 'ಗದ್ಯ', 'ಪದ್ಯ', 'ಪ್ರಬಂಧ'],
  };

  const topics = subjectTopics[formData.subject] || ['General'];

  for (let i = 0; i < questionCount; i++) {
    const qType = types[i % types.length];
    const diff = difficulties[i % difficulties.length];
    const bloom = blooms[i % blooms.length];
    const topic = topics[i % topics.length];

    let template: QuestionTemplate;
    if (qType === 'MCQ') {
      template = MCQ_TEMPLATES[i % MCQ_TEMPLATES.length];
    } else if (qType === 'Short') {
      template = SHORT_TEMPLATES[i % SHORT_TEMPLATES.length];
    } else {
      template = LONG_TEMPLATES[i % LONG_TEMPLATES.length];
    }

    const effectiveMarks = (() => {
      if (marksPerQuestion) return marksPerQuestion;
      if (qType === 'MCQ') return 1;
      if (qType === 'Short') return 2;
      return diff === 'hard' ? 5 : 3;
    })() as Marks;

    questions.push({
      id: Math.random().toString(36).slice(2, 18),
      questionNumber: i + 1,
      text: template.textFn(chapter),
      type: qType,
      difficulty: diff,
      marks: effectiveMarks,
      topic,
      bloomsLevel: bloom,
      options: template.optionsFn?.(chapter),
      answer: template.answerFn(chapter),
      explanation: template.explanation,
      tags: [chapter, formData.subject, `grade-${formData.grade}`, diff],
    });
  }

  return questions;
}
