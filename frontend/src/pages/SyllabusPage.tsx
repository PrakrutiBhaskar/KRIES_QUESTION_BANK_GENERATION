import { useEffect, useMemo, useState } from 'react';
import { Library, Loader2, Plus, Trash2 } from 'lucide-react';
import type { ChapterInfo, Subject } from '../types';
import {
  errorMessage,
  fetchChapters,
  fetchSeededChapters,
  removeSeededChapter,
  seedSyllabus,
  type SeededChapter,
} from '../lib/api';
import { useApp } from '../hooks/useApp';
import { ConfirmModal, EmptyState } from '../components/ui';
import { parseChapters } from '../lib/syllabus';

const SUBJECTS: Subject[] = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];
const GRADES = [7, 8, 9];

const INPUT =
  'w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
const LABEL = 'block text-sm font-medium text-slate-700 mb-1.5';

const norm = (s: string) => s.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

export default function SyllabusPage() {
  const { showToast } = useApp();
  const [subject, setSubject] = useState<Subject>('Science');
  const [grade, setGrade] = useState(8);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [warning, setWarning] = useState<string | null>(null);

  // What the syllabus holds now for the chosen subject and grade. Tagged with the
  // choice it belongs to, so a late reply for an earlier choice is ignored.
  const key = `${subject}|${grade}`;
  const [loaded, setLoaded] = useState<{ key: string; chapters: ChapterInfo[]; seeded: SeededChapter[] } | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const [removing, setRemoving] = useState<SeededChapter | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchChapters(subject, grade), fetchSeededChapters(subject, grade)])
      .then(([chapters, seeded]) => {
        if (cancelled) return;
        setLoaded({ key, chapters, seeded });
        setLoadError(null);
      })
      .catch((e) => { if (!cancelled) setLoadError(errorMessage(e)); });
    return () => { cancelled = true; };
  }, [subject, grade, key, reloads]);

  const current = loaded?.key === key ? loaded : null;
  const seededByName = useMemo(
    () => new Map((current?.seeded ?? []).map((s) => [norm(s.name), s])),
    [current],
  );

  const parsed = useMemo(() => parseChapters(text), [text]);
  const existing = useMemo(() => new Set((current?.chapters ?? []).map((c) => norm(c.name))), [current]);
  const duplicates = parsed.filter((c) => existing.has(norm(c.name))).length;

  const handleSeed = async () => {
    if (parsed.length === 0 || busy) return;
    setBusy(true);
    setWarning(null);
    try {
      const r = await seedSyllabus(subject, grade, parsed);
      const skipped = r.skipped.length ? `, ${r.skipped.length} already in the syllabus` : '';
      showToast(
        r.added.length
          ? `Added ${r.added.length} chapter${r.added.length === 1 ? '' : 's'} to ${subject} Class ${grade}${skipped}.`
          : `Nothing new to add: all ${r.skipped.length} chapters are already in the syllabus.`,
        r.added.length ? 'success' : 'info',
      );
      setWarning(r.warning);
      if (r.added.length) setText('');
      setReloads((n) => n + 1);
    } catch (e) {
      showToast(errorMessage(e), 'error');
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    if (!removing) return;
    const target = removing;
    setRemoving(null);
    try {
      await removeSeededChapter(target.id);
      showToast(`Removed "${target.name}" from the syllabus.`);
      setReloads((n) => n + 1);
    } catch (e) {
      showToast(errorMessage(e), 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-4 py-3 text-sm text-indigo-900">
        Add chapters for a subject and class and they can be used to generate questions straight away, with no restart.
        Chapters from the ingested textbooks stay as they are; this page only adds to them.
      </div>

      <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <h2 className="text-base font-semibold text-slate-900">Seed new chapters</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="seed-subject" className={LABEL}>Subject</label>
            <select id="seed-subject" value={subject} onChange={(e) => setSubject(e.target.value as Subject)} className={INPUT}>
              {SUBJECTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="seed-grade" className={LABEL}>Class</label>
            <select id="seed-grade" value={grade} onChange={(e) => setGrade(Number(e.target.value))} className={INPUT}>
              {GRADES.map((g) => <option key={g} value={g}>Class {g}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label htmlFor="seed-chapters" className={LABEL}>Chapters</label>
          <textarea
            id="seed-chapters"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={8}
            placeholder={'One chapter per line. Topics are optional:\nCrop Production: Kharif crops; Rabi crops; Irrigation\nMicroorganisms\nCoal and Petroleum'}
            className={`${INPUT} font-mono`}
          />
          <p className="mt-1.5 text-xs text-slate-500">
            Write <span className="font-mono">Chapter name: topic one; topic two</span> to give a chapter sub-topics. Questions
            for the chapter stay inside them. Up to 100 chapters at a time.
          </p>
        </div>

        {warning && (
          <p className="rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">{warning}</p>
        )}

        <div className="flex items-center justify-between gap-3">
          <p className="text-sm text-slate-600" aria-live="polite">
            {parsed.length === 0
              ? 'No chapters yet.'
              : `${parsed.length} chapter${parsed.length === 1 ? '' : 's'} ready for ${subject} Class ${grade}${
                  duplicates ? ` (${duplicates} already in the syllabus will be skipped)` : ''
                }.`}
          </p>
          <button
            onClick={handleSeed}
            disabled={parsed.length === 0 || parsed.length > 100 || busy}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-semibold rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
            Seed syllabus
          </button>
        </div>
      </section>

      <section className="bg-white rounded-xl border border-slate-200 p-5">
        <h2 className="text-base font-semibold text-slate-900 mb-3">
          Current syllabus: {subject}, Class {grade}
        </h2>
        {loadError ? (
          <p className="text-sm text-red-600">{loadError}</p>
        ) : !current ? (
          <p className="flex items-center gap-2 text-sm text-slate-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</p>
        ) : current.chapters.length === 0 ? (
          <EmptyState
            icon={<Library className="w-6 h-6" />}
            title="No chapters yet"
            description="Seed the first chapters for this subject and class above."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {current.chapters.map((c) => {
              const seeded = seededByName.get(norm(c.name));
              return (
                <li key={c.id} className="py-2.5 flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900">
                      {c.name}
                      {seeded && (
                        <span className="ml-2 rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700">Added here</span>
                      )}
                    </p>
                    {seeded && seeded.topics.length > 0 && (
                      <p className="text-xs text-slate-500 mt-0.5">{seeded.topics.join(' · ')}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-slate-500">{c.questionCount} question{c.questionCount === 1 ? '' : 's'}</span>
                    {seeded?.canRemove && (
                      <button
                        onClick={() => setRemoving(seeded)}
                        aria-label={`Remove ${c.name}`}
                        title="Remove"
                        className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <ConfirmModal
        open={removing !== null}
        title="Remove this chapter?"
        message={`"${removing?.name ?? ''}" will no longer be offered for ${subject} Class ${grade}. Questions already generated for it are kept.`}
        confirmLabel="Remove"
        danger
        onConfirm={handleRemove}
        onCancel={() => setRemoving(null)}
      />
    </div>
  );
}
