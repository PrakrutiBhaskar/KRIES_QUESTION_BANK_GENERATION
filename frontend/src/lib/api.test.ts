import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, fetchMarksSplit, removeSeededChapter, seedSyllabus, fetchSeededChapters, updateQuestion } from './api';

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const lastCall = () => {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: String(url), init: init as RequestInit, body: init?.body ? JSON.parse(init.body as string) : undefined };
};

const questionWire = {
  id: 'q1', subject: 'Science', chapter: 'Light', grade: 8, text: 'Explain reflection', type: 'Short',
  difficulty: 'medium', marks: 3, topic: '', answer: 'a', explanation: 'e', tags: [],
};

describe('marks split in the API client', () => {
  it('reads a stored split off a question', async () => {
    const split = [{ name: 'Diagram', marks: 2 }, { name: 'Explanation', marks: 1 }];
    fetchMock.mockResolvedValue(json({ ...questionWire, marks_split: split }));
    const q = await updateQuestion('q1', { marks_split: split });
    expect(q.marksSplit).toEqual(split);
  });

  it('leaves marksSplit empty when the question has none', async () => {
    fetchMock.mockResolvedValue(json(questionWire));
    expect((await updateQuestion('q1', { text: 'x' })).marksSplit).toBeUndefined();
  });

  it('sends null to go back to the automatic split', async () => {
    fetchMock.mockResolvedValue(json(questionWire));
    await updateQuestion('q1', { marks_split: null });
    const { url, init, body } = lastCall();
    expect(url).toContain('/questions/q1');
    expect(init.method).toBe('PATCH');
    expect(body).toEqual({ marks_split: null });
  });

  it('maps the marks-split lookup', async () => {
    fetchMock.mockResolvedValue(
      json({ marks: 3, marks_split: null, auto_marks_split: [{ name: 'Explanation', marks: 3 }], editable: true }),
    );
    expect(await fetchMarksSplit('q1')).toEqual({
      marks: 3,
      marksSplit: null,
      autoMarksSplit: [{ name: 'Explanation', marks: 3 }],
      editable: true,
    });
    expect(lastCall().url).toContain('/questions/q1/marks-split');
  });
});

describe('syllabus seeding in the API client', () => {
  const seeded = { id: 's1', subject: 'Science', grade: 8, name: 'Crop Production', topics: ['Kharif'], can_remove: true };

  it('posts the chapters and maps the result', async () => {
    fetchMock.mockResolvedValue(json({ added: [seeded], skipped: ['Light'], warning: null }, 201));
    const r = await seedSyllabus('Science', 8, [{ name: 'Crop Production', topics: ['Kharif'] }]);
    const { url, init, body } = lastCall();
    expect(url).toContain('/syllabus/seed');
    expect(init.method).toBe('POST');
    expect(body).toEqual({ subject: 'Science', grade: 8, chapters: [{ name: 'Crop Production', topics: ['Kharif'] }] });
    expect(r.added[0]).toMatchObject({ id: 's1', name: 'Crop Production', canRemove: true, topics: ['Kharif'] });
    expect(r.skipped).toEqual(['Light']);
    expect(r.warning).toBeNull();
  });

  it('lists seeded chapters, filtered by subject and grade', async () => {
    fetchMock.mockResolvedValue(json([seeded]));
    const rows = await fetchSeededChapters('Science', 8);
    expect(lastCall().url).toMatch(/\/syllabus\/seeded\?subject=Science&grade=8$/);
    expect(rows).toHaveLength(1);
  });

  it('removes a seeded chapter', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await removeSeededChapter('s1');
    expect(lastCall().url).toContain('/syllabus/seeded/s1');
    expect(lastCall().init.method).toBe('DELETE');
  });

  it('turns a student being refused into an ApiError the pages can show', async () => {
    fetchMock.mockResolvedValue(
      json({ error: 'editor_required', detail: 'Only teachers and administrators can edit questions and papers.' }, 403),
    );
    await expect(seedSyllabus('Science', 8, [{ name: 'X', topics: [] }])).rejects.toMatchObject({
      status: 403,
      code: 'editor_required',
    });
    await expect(seedSyllabus('Science', 8, [{ name: 'X', topics: [] }])).rejects.toBeInstanceOf(ApiError);
  });
});
