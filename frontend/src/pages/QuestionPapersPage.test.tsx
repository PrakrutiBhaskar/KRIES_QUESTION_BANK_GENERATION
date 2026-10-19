import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import QuestionPapersPage from './QuestionPapersPage';
import { setApp, testApp } from '../test/appContext';
import * as api from '../lib/api';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));
vi.mock('../lib/api', async (importActual) => ({
  ...(await importActual<typeof import('../lib/api')>()),
  fetchChapters: vi.fn(),
  fetchCombinations: vi.fn(),
  previewBlueprint: vi.fn(),
  buildBlueprintPaper: vi.fn(),
}));

const chapterList = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ id: `c${i + 1}`, name: `Chapter ${i + 1}`, orderIndex: i, questionCount: 0 }));

const planFor = (chapters: string[], questionsEach = 1) => ({
  totalMarks: 30,
  totalQuestions: chapters.length * questionsEach,
  sections: [],
  chapters: chapters.map((chapter) => ({
    chapter, weightage: 100 / chapters.length, targetMarks: 30 / chapters.length, plannedMarks: 30 / chapters.length, plannedQuestions: questionsEach,
  })),
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <QuestionPapersPage />
    </MemoryRouter>,
  );

const checked = () => screen.getAllByRole('checkbox').filter((c) => (c as HTMLInputElement).checked);

beforeEach(() => {
  setApp('Teacher');
  vi.mocked(api.fetchCombinations).mockResolvedValue({ MCQ: [1], Short: [1, 2, 3], Long: [5], Fill: [1], Match: [3, 5] });
  vi.mocked(api.previewBlueprint).mockImplementation(async (bp) => planFor(bp.chapters.map((c) => c.name)));
});

describe('a paper for the entire subject', () => {
  it('selects every chapter, even when there are more than twelve', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(18));
    renderPage();
    await screen.findByText('Chapter 18');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));

    expect(checked()).toHaveLength(18);
    expect(screen.getByText(/this paper covers all 18 chapters of Science, Grade 8/i)).toBeInTheDocument();
    expect(screen.getByText('Total: 100%')).toBeInTheDocument();
  });

  it('shares the marks as evenly as whole percentages allow', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(18));
    renderPage();
    await screen.findByText('Chapter 1');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));

    const weights = screen.getAllByLabelText(/^Weightage for/).map((i) => Number((i as HTMLInputElement).value));
    expect(weights).toHaveLength(18);
    expect(weights.reduce((a, b) => a + b, 0)).toBe(100);
    expect(Math.max(...weights) - Math.min(...weights)).toBeLessThanOrEqual(1);
  });

  it('asks the preview for all the chapters', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(15));
    renderPage();
    await screen.findByText('Chapter 15');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    await waitFor(() => expect(api.previewBlueprint).toHaveBeenCalled(), { timeout: 3000 });
    const sent = vi.mocked(api.previewBlueprint).mock.calls.at(-1)![0];
    expect(sent.chapters).toHaveLength(15);
  });

  it('does not show the whole-subject note for a partial selection', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(5));
    renderPage();
    await screen.findByText('Chapter 5');
    await userEvent.click(screen.getByRole('checkbox', { name: /Chapter 1$/ }));
    expect(screen.queryByText(/this paper covers all/i)).not.toBeInTheDocument();
  });

  it('warns when the paper has fewer questions than chapters', async () => {
    // The default sections are 10 + 5 + 2 = 17 questions; 20 chapters cannot all get one.
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(20));
    renderPage();
    await screen.findByText('Chapter 20');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    expect(screen.getByText(/at least 3 chapters will have no question/i)).toBeInTheDocument();
  });

  it('does not warn when every chapter can get a question', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(10));
    renderPage();
    await screen.findByText('Chapter 10');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    expect(screen.queryByText(/will have no question/i)).not.toBeInTheDocument();
  });

  it('names any chapter the plan leaves without a question', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(3));
    vi.mocked(api.previewBlueprint).mockResolvedValue({
      ...planFor(['Chapter 1', 'Chapter 2', 'Chapter 3']),
      chapters: [
        { chapter: 'Chapter 1', weightage: 34, targetMarks: 10, plannedMarks: 10, plannedQuestions: 2 },
        { chapter: 'Chapter 2', weightage: 33, targetMarks: 10, plannedMarks: 10, plannedQuestions: 2 },
        { chapter: 'Chapter 3', weightage: 33, targetMarks: 10, plannedMarks: 0, plannedQuestions: 0 },
      ],
    });
    renderPage();
    await screen.findByText('Chapter 3');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    expect(await screen.findByText('No question is planned for Chapter 3.', undefined, { timeout: 3000 })).toBeInTheDocument();
  });

  it('refuses, with a message, when the subject has more chapters than a paper can hold', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(61));
    const app = setApp('Teacher');
    renderPage();
    await screen.findByText('Chapter 61');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    expect(app.showToast).toHaveBeenCalledWith('A paper can draw on at most 60 chapters; this subject has 61.', 'warning');
    expect(checked()).toHaveLength(0);
  });

  it('Clear drops the selection', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue(chapterList(4));
    renderPage();
    await screen.findByText('Chapter 4');
    await userEvent.click(screen.getByRole('button', { name: 'Entire subject' }));
    await userEvent.click(screen.getByRole('button', { name: 'Clear' }));
    expect(checked()).toHaveLength(0);
  });
});
