import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ImagePlus, Images, Loader2, Pencil, Trash2, Upload, X } from 'lucide-react';
import type { ChapterInfo, LibraryFigure, Subject } from '../types';
import {
  ApiError,
  deleteFigure,
  errorMessage,
  fetchChapters,
  fetchFigureLibrary,
  updateFigure,
  uploadFigure,
  type FigureInput,
} from '../lib/api';
import { useApp } from '../hooks/useApp';
import { FigureImage } from '../components/FigureImage';
import { ConfirmModal, EmptyState } from '../components/ui';
import { FigureGridSkeleton } from '../components/Skeleton';

const SUBJECTS: Subject[] = ['Math', 'Science', 'Social Science', 'English', 'Kannada'];
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // matches the backend's MAX_FIGURE_BYTES default
const ACCEPT = 'image/png,image/jpeg,image/gif,image/webp';

const INPUT =
  'w-full px-3.5 py-2.5 rounded-lg border border-slate-300 text-sm text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500';
const LABEL = 'block text-sm font-medium text-slate-700 mb-1.5';

const EMPTY_META: FigureInput = { caption: '', subject: '', chapter: '', topic: '', labels: [] };

/** Why a figure can't be used to write questions yet; null when it is ready. */
function problemWith(meta: FigureInput): string | null {
  if (!meta.subject) return 'Choose a subject, so teachers can find this figure.';
  if (!meta.chapter.trim()) return 'Choose a chapter. Questions are written for one chapter at a time.';
  if (!meta.caption.trim() && meta.labels.length === 0) {
    return 'Add a caption or the labelled parts. Questions are written from that text (the model never sees the image).';
  }
  return null;
}

const splitLabels = (text: string) =>
  text.split('\n').map((l) => l.trim()).filter(Boolean);

// ============================================================
// Subject / chapter / topic / caption / labels — shared by "add" and "edit"
// ============================================================
function MetaFields({
  meta,
  onChange,
  idPrefix,
}: {
  meta: FigureInput;
  onChange: (next: FigureInput) => void;
  idPrefix: string;
}) {
  // Tagged with the subject they belong to, so a late reply for a previous
  // subject is ignored and "loading" can be derived instead of stored.
  const [loaded, setLoaded] = useState<{ subject: string; rows: ChapterInfo[] } | null>(null);
  const [labelsText, setLabelsText] = useState(meta.labels.join('\n'));
  const chapters = loaded?.subject === meta.subject ? loaded.rows : [];
  const chaptersLoading = meta.subject !== '' && loaded?.subject !== meta.subject;

  // Chapter names come from the backend syllabus, so they always match what
  // "Generate" asks for.
  useEffect(() => {
    if (!meta.subject) return;
    const subject = meta.subject;
    let cancelled = false;
    fetchChapters(subject as Subject)
      .then((rows) => { if (!cancelled) setLoaded({ subject, rows }); })
      .catch(() => { if (!cancelled) setLoaded({ subject, rows: [] }); });
    return () => { cancelled = true; };
  }, [meta.subject]);

  // A chapter the figure already has but the list lacks (renamed syllabus) must
  // still be selectable, or editing would silently change it.
  const names = chapters.map((c) => c.name);
  if (meta.chapter && !names.includes(meta.chapter)) names.unshift(meta.chapter);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${idPrefix}-subject`} className={LABEL}>Subject</label>
          <select
            id={`${idPrefix}-subject`}
            value={meta.subject}
            onChange={(e) => onChange({ ...meta, subject: e.target.value as Subject | '', chapter: '' })}
            className={INPUT}
          >
            <option value="">Select a subject…</option>
            {SUBJECTS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-chapter`} className={LABEL}>Chapter</label>
          <select
            id={`${idPrefix}-chapter`}
            value={meta.chapter}
            onChange={(e) => onChange({ ...meta, chapter: e.target.value })}
            disabled={!meta.subject || chaptersLoading}
            className={`${INPUT} disabled:bg-slate-100 disabled:text-slate-400`}
          >
            <option value="">{chaptersLoading ? 'Loading chapters…' : 'Select a chapter…'}</option>
            {names.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor={`${idPrefix}-topic`} className={LABEL}>
          Topic <span className="font-normal text-slate-400">(optional)</span>
        </label>
        <input
          id={`${idPrefix}-topic`}
          value={meta.topic}
          maxLength={120}
          onChange={(e) => onChange({ ...meta, topic: e.target.value })}
          placeholder="Leave empty if it fits the whole chapter"
          className={INPUT}
        />
      </div>

      <div>
        <label htmlFor={`${idPrefix}-caption`} className={LABEL}>Caption</label>
        <input
          id={`${idPrefix}-caption`}
          value={meta.caption}
          maxLength={300}
          onChange={(e) => onChange({ ...meta, caption: e.target.value })}
          placeholder="What the diagram shows, e.g. Cross-section of a leaf"
          className={INPUT}
        />
        <p className="mt-1 text-xs text-slate-400">Printed under the diagram, and used to write the questions.</p>
      </div>

      <div>
        <label htmlFor={`${idPrefix}-labels`} className={LABEL}>
          Labelled parts <span className="font-normal text-slate-400">(one per line)</span>
        </label>
        <textarea
          id={`${idPrefix}-labels`}
          value={labelsText}
          rows={4}
          onChange={(e) => {
            setLabelsText(e.target.value);
            onChange({ ...meta, labels: splitLabels(e.target.value) });
          }}
          placeholder={'A: nucleus\nB: cell wall\nC: chloroplast'}
          className={`${INPUT} font-mono`}
        />
        <p className="mt-1 text-xs text-slate-400">
          These become the answer key for "label the diagram" questions. Students never see them.
        </p>
      </div>
    </div>
  );
}

// ============================================================
// Add a figure
// ============================================================
function UploadCard({ onAdded }: { onAdded: (figure: LibraryFigure) => void }) {
  const { showToast } = useApp();
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState<FigureInput>(EMPTY_META);
  const [fileError, setFileError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  // Remounts MetaFields after a successful upload so its labels box clears too.
  const [formKey, setFormKey] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // An object URL for the preview; released when the file changes or the card goes away.
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const choose = (picked: File | undefined) => {
    setFileError(null);
    if (!picked) return;
    if (!picked.type.startsWith('image/')) {
      setFile(null);
      setFileError('That is not an image. Choose a PNG or JPEG.');
      return;
    }
    if (picked.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setFileError(`That image is ${(picked.size / 1048576).toFixed(1)} MB. The limit is 5 MB.`);
      return;
    }
    setFile(picked);
  };

  const problem = problemWith(meta);

  const submit = async () => {
    setSubmitted(true);
    if (!file || problem) return;
    setBusy(true);
    try {
      const added = await uploadFigure(file, meta);
      onAdded(added);
      showToast('Figure added to the library.', 'success');
      // Keep subject + chapter: admins usually add several diagrams to one chapter.
      setFile(null);
      setMeta((m) => ({ ...EMPTY_META, subject: m.subject, chapter: m.chapter }));
      setFormKey((k) => k + 1);
      setSubmitted(false);
      if (inputRef.current) inputRef.current.value = '';
    } catch (err) {
      showToast(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5">
      <h2 className="text-sm font-semibold text-slate-900 mb-1 flex items-center gap-2">
        <ImagePlus className="w-4 h-4 text-indigo-600" /> Add a diagram
      </h2>
      <p className="text-xs text-slate-500 mb-4">
        PNG or JPEG, up to 5 MB. Transparent backgrounds are flattened onto white so the diagram prints cleanly.
      </p>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,240px)_1fr]">
        <div>
          <label
            htmlFor="figure-file"
            className="flex h-48 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 bg-slate-50 text-center text-sm text-slate-500 hover:border-indigo-400 hover:bg-indigo-50/40 transition-colors overflow-hidden"
          >
            {preview ? (
              <img src={preview} alt="Selected diagram" className="max-h-full max-w-full object-contain" />
            ) : (
              <>
                <Upload className="w-6 h-6 mb-2 text-slate-400" />
                Choose an image
              </>
            )}
          </label>
          <input
            id="figure-file"
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => choose(e.target.files?.[0])}
          />
          {file && <p className="mt-1.5 truncate text-xs text-slate-500">{file.name}</p>}
          {(fileError || (submitted && !file)) && (
            <p className="mt-1.5 text-xs text-red-600" role="alert">
              {fileError ?? 'Choose an image to upload.'}
            </p>
          )}
        </div>

        <div>
          <MetaFields key={formKey} meta={meta} onChange={setMeta} idPrefix="new-figure" />
          {submitted && problem && (
            <p className="mt-3 text-xs text-red-600" role="alert">{problem}</p>
          )}
          <div className="mt-5 flex justify-end">
            <button
              onClick={submit}
              disabled={busy}
              className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60 transition-colors"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              {busy ? 'Uploading…' : 'Add to library'}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// ============================================================
// Edit a figure's tags
// ============================================================
function EditModal({
  figure,
  onClose,
  onSaved,
}: {
  figure: LibraryFigure;
  onClose: () => void;
  onSaved: (figure: LibraryFigure) => void;
}) {
  const { showToast } = useApp();
  const [meta, setMeta] = useState<FigureInput>({
    caption: figure.caption,
    subject: figure.subject ?? '',
    chapter: figure.chapter ?? '',
    topic: figure.topic,
    labels: figure.labels,
  });
  const [submitted, setSubmitted] = useState(false);
  const [busy, setBusy] = useState(false);
  const problem = problemWith(meta);

  const save = async () => {
    setSubmitted(true);
    if (problem) return;
    setBusy(true);
    try {
      onSaved(await updateFigure(figure.id, meta));
      showToast('Figure updated.', 'success');
      onClose();
    } catch (err) {
      showToast(errorMessage(err), 'error');
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Edit figure">
      <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto p-6">
        <div className="flex items-start justify-between mb-4">
          <h3 className="text-base font-semibold text-slate-900">Edit figure</h3>
          <button onClick={onClose} aria-label="Close" className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>
        <FigureImage figure={figure} className="mb-4" />
        <MetaFields meta={meta} onChange={setMeta} idPrefix="edit-figure" />
        {submitted && problem && <p className="mt-3 text-xs text-red-600" role="alert">{problem}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200">
            Cancel
          </button>
          <button
            onClick={save}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-60"
          >
            {busy ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================
// Page
// ============================================================
export default function FigureLibraryPage() {
  const { showToast } = useApp();
  const [figures, setFigures] = useState<LibraryFigure[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Subject | ''>('');
  const [editing, setEditing] = useState<LibraryFigure | null>(null);
  const [deleting, setDeleting] = useState<LibraryFigure | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      setFigures(await fetchFigureLibrary(filter ? { subject: filter } : {}));
    } catch (err) {
      setLoadError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { void load(); }, [load]);

  const confirmDelete = async () => {
    const target = deleting;
    if (!target) return;
    setDeleting(null);
    try {
      await deleteFigure(target.id);
      setFigures((list) => list.filter((f) => f.id !== target.id));
      showToast('Figure deleted.', 'info');
    } catch (err) {
      // 409: still attached to questions. The server's message says how many.
      showToast(errorMessage(err), err instanceof ApiError && err.status === 409 ? 'warning' : 'error');
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-indigo-100 bg-indigo-50/60 px-4 py-3 text-sm text-indigo-900">
        Diagrams added here are shared with every teacher. When a question bank or question paper is generated,
        some questions are picked at random to be diagram-based (for chapters that have diagrams here), and each
        question's diagram is printed again in the answer key.
      </div>

      <UploadCard
        onAdded={(f) => {
          // Show it straight away if it belongs under the current filter.
          if (!filter || f.subject === filter) setFigures((list) => [f, ...list]);
        }}
      />

      <section>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <h2 className="text-sm font-semibold text-slate-900">
            Library{!loading && !loadError && <span className="ml-2 font-normal text-slate-400">{figures.length}</span>}
          </h2>
          <select
            aria-label="Filter by subject"
            value={filter}
            onChange={(e) => setFilter(e.target.value as Subject | '')}
            className="px-3 py-2 rounded-lg border border-slate-300 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">All subjects</option>
            {SUBJECTS.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        {loading ? (
          <FigureGridSkeleton />
        ) : loadError ? (
          <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {loadError}{' '}
            <button onClick={() => void load()} className="font-medium underline">Try again</button>
          </div>
        ) : figures.length === 0 ? (
          <div className="bg-white rounded-xl border border-slate-200">
            <EmptyState
              icon={<Images className="w-6 h-6" />}
              title={filter ? `No ${filter} figures yet` : 'The library is empty'}
              description="Add a diagram above and it will be available to every teacher."
            />
          </div>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {figures.map((f) => {
              const unusable = problemWith({
                caption: f.caption, subject: f.subject ?? '', chapter: f.chapter ?? '', topic: f.topic, labels: f.labels,
              });
              return (
                <li key={f.id} className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col">
                  <div className="flex-1 flex justify-center bg-slate-50 rounded-lg p-2 mb-3 min-h-32">
                    <FigureImage figure={f} />
                  </div>
                  <div className="flex flex-wrap gap-1.5 text-xs mb-2">
                    {f.subject && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">{f.subject}</span>}
                    {f.chapter && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700">{f.chapter}</span>}
                    {f.topic && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-500">{f.topic}</span>}
                  </div>
                  {f.labels.length > 0 && (
                    <p className="text-xs text-slate-500 mb-2 line-clamp-2">{f.labels.join(' · ')}</p>
                  )}
                  {unusable && (
                    <p className="text-xs text-amber-700 mb-2">Not used for generation yet: {unusable}</p>
                  )}
                  <div className="mt-auto flex gap-2 pt-2 border-t border-slate-100">
                    <button
                      onClick={() => setEditing(f)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 rounded-lg hover:bg-slate-200"
                    >
                      <Pencil className="w-3.5 h-3.5" /> Edit
                    </button>
                    <button
                      onClick={() => setDeleting(f)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 rounded-lg hover:bg-red-50"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Delete
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {editing && (
        <EditModal
          figure={editing}
          onClose={() => setEditing(null)}
          onSaved={(saved) => setFigures((list) => list.map((f) => (f.id === saved.id ? saved : f)))}
        />
      )}

      <ConfirmModal
        open={deleting !== null}
        danger
        title="Delete this figure?"
        message="It will be removed from the library for everyone. If a question still prints it, the delete is refused."
        confirmLabel="Delete"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}
