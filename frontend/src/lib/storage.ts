import type { QuestionBank } from '../types';
import { INITIAL_QUESTION_BANKS } from '../data/mockData';

const BANKS_KEY = 'kries_question_banks';

export function loadQuestionBanks(): QuestionBank[] {
  try {
    const raw = localStorage.getItem(BANKS_KEY);
    return raw ? (JSON.parse(raw) as QuestionBank[]) : INITIAL_QUESTION_BANKS;
  } catch {
    return INITIAL_QUESTION_BANKS;
  }
}

export function saveQuestionBanks(banks: QuestionBank[]): void {
  localStorage.setItem(BANKS_KEY, JSON.stringify(banks));
}
