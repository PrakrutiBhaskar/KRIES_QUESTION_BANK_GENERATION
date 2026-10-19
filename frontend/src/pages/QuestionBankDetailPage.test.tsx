import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import QuestionBankDetailPage from './QuestionBankDetailPage';
import { setApp, testApp } from '../test/appContext';
import { makeBank, makeQuestion } from '../test/fixtures';
import * as api from '../lib/api';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));
vi.mock('../lib/api', async (importActual) => ({
  ...(await importActual<typeof import('../lib/api')>()),
  fetchBank: vi.fn(),
  fetchCombinations: vi.fn(),
  fetchMarksSplit: vi.fn(),
  updateQuestion: vi.fn(),
  copyQuestion: vi.fn(),
  setBankQuestions: vi.fn(),
}));

const AUTO = [{ name: 'Diagram', marks: 1 }, { name: 'Explanation', marks: 2 }];

function renderBank(url = '/question-banks/bank-1') {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/question-banks/:id" element={<QuestionBankDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

const openEditor = async () => {
  await userEvent.click(await screen.findByRole('button', { name: /^edit$/i }));
  await userEvent.click(await screen.findByRole('button', { name: 'Edit question and answer' }));
  return screen.findByRole('dialog', { name: 'Edit question' });
};

const save = (dialog: HTMLElement) => userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }));

let app: ReturnType<typeof setApp>;

beforeEach(() => {
  app = setApp('Teacher');
  vi.mocked(api.fetchBank).mockResolvedValue(makeBank());
  vi.mocked(api.fetchCombinations).mockResolvedValue({ MCQ: [1], Short: [1, 2, 3], Long: [5], Fill: [1], Match: [3, 5] });
  vi.mocked(api.fetchMarksSplit).mockResolvedValue({ marks: 3, marksSplit: null, autoMarksSplit: AUTO, editable: true });
  vi.mocked(api.updateQuestion).mockImplementation(async (_id, changes) =>
    makeQuestion({ marksSplit: changes.marks_split ?? undefined }),
  );
});

describe('who can edit a question bank', () => {
  it.each(['Teacher', 'Admin'] as const)('gives %s an Edit button', async (role) => {
    setApp(role);
    renderBank();
    expect(await screen.findByRole('button', { name: /^edit$/i })).toBeInTheDocument();
  });

  it('gives a student no Edit button', async () => {
    setApp('Student');
    renderBank();
    await screen.findByText('Light revision');
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
  });

  it('ignores ?edit=1 for a student: no row actions appear', async () => {
    setApp('Student');
    renderBank('/question-banks/bank-1?edit=1');
    await screen.findByText('Light revision');
    expect(screen.queryByRole('button', { name: 'Edit question and answer' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^done$/i })).not.toBeInTheDocument();
  });

  it('honours ?edit=1 for a teacher', async () => {
    renderBank('/question-banks/bank-1?edit=1');
    expect(await screen.findByRole('button', { name: 'Edit question and answer' })).toBeInTheDocument();
  });

  it('shows a student the empty bank without an Edit shortcut', async () => {
    setApp('Student');
    vi.mocked(api.fetchBank).mockResolvedValue(makeBank({ questions: [], questionCount: 0, totalMarks: 0 }));
    renderBank();
    expect(await screen.findByText('This bank has no questions.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^edit$/i })).not.toBeInTheDocument();
  });
});

describe('editing the marks split', () => {
  it('shows the automatic split and starts from it when you choose Edit split', async () => {
    renderBank();
    const dialog = await openEditor();
    expect(await within(dialog).findByText(/Automatic: Diagram - 1, Explanation - 2/)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Edit split' }));
    expect(within(dialog).getByLabelText('Marks split part 1 name')).toHaveValue('Diagram');
    expect(within(dialog).getByLabelText('Marks split part 2 marks')).toHaveValue(2);
    expect(within(dialog).getByText('3 / 3 marks')).toBeInTheDocument();
  });

  it('saves a custom split', async () => {
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 1 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 1 marks'), '2');
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 2 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 2 marks'), '1');
    await save(dialog);

    await waitFor(() => expect(api.updateQuestion).toHaveBeenCalledTimes(1));
    expect(api.updateQuestion).toHaveBeenCalledWith('q1', {
      marks_split: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }],
    });
  });

  it('shows a live total and refuses a split that does not add up', async () => {
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 2 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 2 marks'), '5');
    expect(within(dialog).getByText('6 / 3 marks')).toBeInTheDocument();

    await save(dialog);
    expect(await within(dialog).findByText('The marks split adds up to 6, but this question is worth 3 marks.')).toBeInTheDocument();
    expect(api.updateQuestion).not.toHaveBeenCalled();
  });

  it('refuses a part with no name and parts with the same name', async () => {
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));

    await userEvent.clear(within(dialog).getByLabelText('Marks split part 1 name'));
    await save(dialog);
    expect(await within(dialog).findByText('Every part of the marks split needs a name.')).toBeInTheDocument();

    await userEvent.type(within(dialog).getByLabelText('Marks split part 1 name'), 'explanation');
    await save(dialog);
    expect(await within(dialog).findByText('Each part of the marks split needs a different name.')).toBeInTheDocument();
    expect(api.updateQuestion).not.toHaveBeenCalled();
  });

  it('adds and removes parts', async () => {
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));
    await userEvent.click(within(dialog).getByRole('button', { name: /add part/i }));
    expect(within(dialog).getByLabelText('Marks split part 3 name')).toBeInTheDocument();
    expect(within(dialog).getByText('4 / 3 marks')).toBeInTheDocument();

    await userEvent.click(within(dialog).getAllByRole('button', { name: 'Remove this part' })[2]);
    expect(within(dialog).queryByLabelText('Marks split part 3 name')).not.toBeInTheDocument();
    expect(within(dialog).getByText('3 / 3 marks')).toBeInTheDocument();
  });

  it('goes back to the automatic split by sending null', async () => {
    vi.mocked(api.fetchBank).mockResolvedValue(
      makeBank({ questions: [makeQuestion({ marksSplit: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }] })] }),
    );
    renderBank();
    const dialog = await openEditor();
    expect(within(dialog).getByLabelText('Marks split part 1 name')).toHaveValue('Diagram');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Use automatic split' }));
    await save(dialog);

    await waitFor(() => expect(api.updateQuestion).toHaveBeenCalledWith('q1', { marks_split: null }));
  });

  it('sends nothing when the split is left alone', async () => {
    vi.mocked(api.fetchBank).mockResolvedValue(
      makeBank({ questions: [makeQuestion({ marksSplit: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }] })] }),
    );
    renderBank();
    const dialog = await openEditor();
    await save(dialog);
    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Edit question' })).not.toBeInTheDocument());
    expect(api.updateQuestion).not.toHaveBeenCalled();
  });

  it('keeps a hand-edited split together with other edits in one save', async () => {
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 1 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 1 marks'), '2');
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 2 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 2 marks'), '1');
    const question = within(dialog).getByDisplayValue('Explain how a periscope works.');
    await userEvent.clear(question);
    await userEvent.type(question, 'Describe a periscope.');
    await save(dialog);

    await waitFor(() => expect(api.updateQuestion).toHaveBeenCalledTimes(1));
    expect(vi.mocked(api.updateQuestion).mock.calls[0][1]).toEqual({
      text: 'Describe a periscope.',
      marks_split: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }],
    });
  });

  it('offers no split for a one-mark question or an MCQ', async () => {
    vi.mocked(api.fetchBank).mockResolvedValue(
      makeBank({
        questions: [makeQuestion({ type: 'MCQ', marks: 1, options: ['a', 'b', 'c', 'd'], answer: 'a' })],
      }),
    );
    renderBank();
    const dialog = await openEditor();
    expect(within(dialog).queryByText(/Marks split/)).not.toBeInTheDocument();
    expect(api.fetchMarksSplit).not.toHaveBeenCalled();
  });

  it('shows a saved split under the answer', async () => {
    vi.mocked(api.fetchBank).mockResolvedValue(
      makeBank({ questions: [makeQuestion({ marksSplit: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }] })] }),
    );
    renderBank();
    await userEvent.click(await screen.findByRole('button', { name: /show answer & explanation/i }));
    expect(await screen.findByText('Marks split: Diagram - 2, Explanation - 1')).toBeInTheDocument();
  });

  it('shows no split line under the answer while the split is automatic', async () => {
    renderBank();
    await userEvent.click(await screen.findByRole('button', { name: /show answer & explanation/i }));
    expect(screen.queryByText(/^Marks split:/)).not.toBeInTheDocument();
  });

  it('warns when the paper counts the question as different marks', async () => {
    vi.mocked(api.fetchBank).mockResolvedValue(
      makeBank({ questions: [makeQuestion({ marks: 5, baseMarks: 3 })] }),
    );
    renderBank();
    const dialog = await openEditor();
    expect(within(dialog).getByText(/This paper counts the question as 5 marks/)).toBeInTheDocument();
    expect(within(dialog).getByText('Marks split (3 marks)')).toBeInTheDocument();
  });

  it('saves an own copy when the question belongs to someone else', async () => {
    vi.mocked(api.updateQuestion)
      .mockRejectedValueOnce(new api.ApiError(403, 'forbidden', 'Not your question'))
      .mockImplementationOnce(async (_id, changes) => makeQuestion({ id: 'copy-1', marksSplit: changes.marks_split ?? undefined }));
    vi.mocked(api.copyQuestion).mockResolvedValue(makeQuestion({ id: 'copy-1' }));
    vi.mocked(api.setBankQuestions).mockResolvedValue(makeBank());
    renderBank();
    const dialog = await openEditor();
    await userEvent.click(await within(dialog).findByRole('button', { name: 'Edit split' }));
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 1 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 1 marks'), '2');
    await userEvent.clear(within(dialog).getByLabelText('Marks split part 2 marks'));
    await userEvent.type(within(dialog).getByLabelText('Marks split part 2 marks'), '1');
    await save(dialog);

    await waitFor(() => expect(api.copyQuestion).toHaveBeenCalledWith('q1'));
    expect(api.updateQuestion).toHaveBeenLastCalledWith('copy-1', {
      marks_split: [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }],
    });
    expect(app.showToast).toHaveBeenCalledWith(expect.stringContaining('Saved as your own copy'), 'success');
  });
});
