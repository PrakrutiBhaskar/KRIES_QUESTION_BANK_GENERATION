import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SyllabusPage from './SyllabusPage';
import { setApp, testApp } from '../test/appContext';
import * as api from '../lib/api';

vi.mock('../hooks/useApp', () => ({ useApp: () => testApp.current }));
vi.mock('../lib/api', async (importActual) => ({
  ...(await importActual<typeof import('../lib/api')>()),
  fetchChapters: vi.fn(),
  fetchSeededChapters: vi.fn(),
  seedSyllabus: vi.fn(),
  removeSeededChapter: vi.fn(),
}));

const chapter = (id: string, name: string, questionCount = 0) => ({ id, name, orderIndex: 0, questionCount });
const seeded = (id: string, name: string, over: Partial<api.SeededChapter> = {}): api.SeededChapter => ({
  id, subject: 'Science', grade: 8, name, topics: [], canRemove: true, ...over,
});

let toast: ReturnType<typeof setApp>;

beforeEach(() => {
  toast = setApp('Teacher');
  vi.mocked(api.fetchChapters).mockResolvedValue([chapter('c1', 'Light', 4), chapter('c2', 'Crop Production')]);
  vi.mocked(api.fetchSeededChapters).mockResolvedValue([
    seeded('s1', 'Crop Production', { topics: ['Kharif crops', 'Rabi crops'] }),
  ]);
});

const typeChapters = async (text: string) => {
  const box = await screen.findByLabelText('Chapters');
  await userEvent.click(box);
  await userEvent.paste(text);
};

describe('SyllabusPage', () => {
  it('lists the current syllabus and marks the chapters added here', async () => {
    render(<SyllabusPage />);
    expect(await screen.findByText('Light')).toBeInTheDocument();
    const row = screen.getByText('Crop Production').closest('li')!;
    expect(within(row).getByText('Added here')).toBeInTheDocument();
    expect(within(row).getByText('Kharif crops · Rabi crops')).toBeInTheDocument();
    expect(within(screen.getByText('Light').closest('li')!).queryByText('Added here')).not.toBeInTheDocument();
    expect(api.fetchChapters).toHaveBeenCalledWith('Science', 8);
  });

  it('keeps Seed syllabus disabled until there is a chapter', async () => {
    render(<SyllabusPage />);
    const button = await screen.findByRole('button', { name: /seed syllabus/i });
    expect(button).toBeDisabled();
    await typeChapters('Microorganisms');
    expect(button).toBeEnabled();
    expect(screen.getByText(/1 chapter ready for Science Class 8/)).toBeInTheDocument();
  });

  it('sends the chosen subject, class, chapters and topics', async () => {
    vi.mocked(api.seedSyllabus).mockResolvedValue({ added: [seeded('s2', 'Microorganisms')], skipped: [], warning: null });
    render(<SyllabusPage />);
    await userEvent.selectOptions(await screen.findByLabelText('Subject'), 'Math');
    await userEvent.selectOptions(screen.getByLabelText('Class'), '9');
    await typeChapters('Rational Numbers: Fractions; Decimals\nLinear Equations');
    await userEvent.click(screen.getByRole('button', { name: /seed syllabus/i }));

    await waitFor(() => expect(api.seedSyllabus).toHaveBeenCalledTimes(1));
    expect(api.seedSyllabus).toHaveBeenCalledWith('Math', 9, [
      { name: 'Rational Numbers', topics: ['Fractions', 'Decimals'] },
      { name: 'Linear Equations', topics: [] },
    ]);
  });

  it('confirms, clears the box and reloads the list after seeding', async () => {
    vi.mocked(api.seedSyllabus).mockResolvedValue({
      added: [seeded('s2', 'Microorganisms')],
      skipped: ['Light'],
      warning: null,
    });
    render(<SyllabusPage />);
    await typeChapters('Microorganisms\nLight');
    await userEvent.click(screen.getByRole('button', { name: /seed syllabus/i }));

    await waitFor(() =>
      expect(toast.showToast).toHaveBeenCalledWith(
        'Added 1 chapter to Science Class 8, 1 already in the syllabus.',
        'success',
      ),
    );
    expect(screen.getByLabelText('Chapters')).toHaveValue('');
    await waitFor(() => expect(api.fetchChapters).toHaveBeenCalledTimes(2));
  });

  it('says so when every chapter was already there', async () => {
    vi.mocked(api.seedSyllabus).mockResolvedValue({ added: [], skipped: ['Light'], warning: null });
    render(<SyllabusPage />);
    await typeChapters('Light');
    await userEvent.click(screen.getByRole('button', { name: /seed syllabus/i }));
    await waitFor(() =>
      expect(toast.showToast).toHaveBeenCalledWith(
        'Nothing new to add: all 1 chapters are already in the syllabus.',
        'info',
      ),
    );
    expect(screen.getByLabelText('Chapters')).toHaveValue('Light'); // kept, so nothing the teacher typed is lost
  });

  it('warns before seeding a chapter the class already has', async () => {
    render(<SyllabusPage />);
    await typeChapters('light\nSound');
    expect(screen.getByText(/2 chapters ready for Science Class 8 \(1 already in the syllabus will be skipped\)/)).toBeInTheDocument();
  });

  it('shows the server warning when no syllabus was loaded before', async () => {
    vi.mocked(api.seedSyllabus).mockResolvedValue({
      added: [seeded('s2', 'Microorganisms')],
      skipped: [],
      warning: 'No syllabus was loaded before, so generation now accepts only the chapters seeded here.',
    });
    render(<SyllabusPage />);
    await typeChapters('Microorganisms');
    await userEvent.click(screen.getByRole('button', { name: /seed syllabus/i }));
    expect(await screen.findByText(/generation now accepts only the chapters seeded here/)).toBeInTheDocument();
  });

  it('shows the error when the server refuses', async () => {
    vi.mocked(api.seedSyllabus).mockRejectedValue(new api.ApiError(403, 'editor_required', 'Only teachers and administrators can edit questions and papers.'));
    render(<SyllabusPage />);
    await typeChapters('Microorganisms');
    await userEvent.click(screen.getByRole('button', { name: /seed syllabus/i }));
    await waitFor(() =>
      expect(toast.showToast).toHaveBeenCalledWith('Only teachers and administrators can edit questions and papers.', 'error'),
    );
    expect(screen.getByLabelText('Chapters')).toHaveValue('Microorganisms');
  });

  it('only offers Remove for chapters the person may remove', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue([chapter('c1', 'Crop Production'), chapter('c2', 'Microorganisms')]);
    vi.mocked(api.fetchSeededChapters).mockResolvedValue([
      seeded('s1', 'Crop Production', { canRemove: true }),
      seeded('s2', 'Microorganisms', { canRemove: false }),
    ]);
    render(<SyllabusPage />);
    await screen.findByText('Microorganisms');
    expect(screen.getByRole('button', { name: 'Remove Crop Production' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove Microorganisms' })).not.toBeInTheDocument();
  });

  it('removes a chapter only after confirmation', async () => {
    vi.mocked(api.removeSeededChapter).mockResolvedValue(undefined);
    render(<SyllabusPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Crop Production' }));
    expect(api.removeSeededChapter).not.toHaveBeenCalled();

    const dialog = screen.getByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(api.removeSeededChapter).toHaveBeenCalledWith('s1'));
    expect(toast.showToast).toHaveBeenCalledWith('Removed "Crop Production" from the syllabus.');
  });

  it('cancelling the confirmation keeps the chapter', async () => {
    render(<SyllabusPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Remove Crop Production' }));
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: /cancel/i }));
    expect(api.removeSeededChapter).not.toHaveBeenCalled();
  });

  it('reloads the syllabus when the subject changes', async () => {
    render(<SyllabusPage />);
    await userEvent.selectOptions(await screen.findByLabelText('Subject'), 'Kannada');
    await waitFor(() => expect(api.fetchChapters).toHaveBeenLastCalledWith('Kannada', 8));
    expect(api.fetchSeededChapters).toHaveBeenLastCalledWith('Kannada', 8);
  });

  it('shows an empty state when the class has no chapters yet', async () => {
    vi.mocked(api.fetchChapters).mockResolvedValue([]);
    vi.mocked(api.fetchSeededChapters).mockResolvedValue([]);
    render(<SyllabusPage />);
    expect(await screen.findByText('No chapters yet')).toBeInTheDocument();
  });

  it('shows why the syllabus could not load', async () => {
    vi.mocked(api.fetchChapters).mockRejectedValue(new Error('boom'));
    render(<SyllabusPage />);
    expect(await screen.findByText('boom')).toBeInTheDocument();
  });
});
