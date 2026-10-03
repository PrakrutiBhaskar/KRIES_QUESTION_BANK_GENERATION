// ============================================================
// Skeleton loaders
//
// Placeholders that mirror the real layout while data loads, so the page doesn't
// jump when content arrives. They use the slate scale, so they follow the dark
// theme automatically, and the pulse is skipped for users who prefer reduced motion.
// ============================================================

/** A single pulsing block. Size and shape come from `className` (e.g. "h-4 w-32"). */
export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden="true" className={`rounded-md bg-slate-200 motion-safe:animate-pulse ${className}`} />;
}

/** Wraps a skeleton so screen readers announce a loading state once, not every block. */
export function SkeletonRegion({
  label,
  className = '',
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div role="status" aria-busy="true" aria-live="polite" className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

// ------------------------------------------------------------
// Question banks
// ------------------------------------------------------------

/** Rows for a question-bank table. `columns` is how many cells each row has. */
export function BankTableRowsSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: columns }).map((__, c) => (
            <td key={c} className={c === 0 ? 'px-5 py-3.5' : 'px-4 py-3.5'}>
              {c === 0 ? (
                <div className="space-y-1.5">
                  <Skeleton className="h-4 w-40 max-w-full" />
                  <Skeleton className="h-3 w-24 max-w-full" />
                </div>
              ) : (
                <Skeleton className="h-4 w-16" />
              )}
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** Grid of cards matching the Question Banks grid view. */
export function BankGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <SkeletonRegion label="Loading question banks…" className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col gap-3">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-1/2" />
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-14 rounded-full" />
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-14 rounded-full" />
          </div>
          <Skeleton className="h-3 w-28" />
          <div className="flex items-center gap-1.5 pt-3 border-t border-slate-100">
            <Skeleton className="h-7 w-16 rounded-lg" />
            <Skeleton className="h-7 w-7 rounded-lg" />
            <Skeleton className="h-7 w-7 rounded-lg ml-auto" />
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Table matching the Question Banks list view. */
export function BankListSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
      <SkeletonRegion label="Loading question banks…">
        <table className="w-full text-sm">
          <tbody className="divide-y divide-slate-100">
            <BankTableRowsSkeleton rows={rows} columns={6} />
          </tbody>
        </table>
      </SkeletonRegion>
    </div>
  );
}

/** Whole Question Bank detail page: header card, then a few question cards. */
export function BankDetailSkeleton() {
  return (
    <SkeletonRegion label="Loading question bank…" className="max-w-4xl mx-auto space-y-5">
      <Skeleton className="h-4 w-40" />
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-start gap-4">
          <div className="flex-1 space-y-3">
            <div className="flex gap-2">
              <Skeleton className="h-5 w-16 rounded-full" />
              <Skeleton className="h-5 w-14" />
            </div>
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
          <Skeleton className="h-9 w-28 rounded-lg" />
        </div>
        <div className="grid grid-cols-3 gap-3 mt-5 pt-5 border-t border-slate-100">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-2">
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-4 w-12" />
            </div>
          ))}
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between mb-4">
          <Skeleton className="h-4 w-28" />
          <Skeleton className="h-9 w-40 rounded-lg" />
        </div>
        <QuestionCardsSkeleton count={3} />
      </div>
    </SkeletonRegion>
  );
}

/** Stack of question cards (number, text lines, option rows, meta badges). */
export function QuestionCardsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <Skeleton className="h-7 w-7 rounded-full shrink-0" />
            <div className="flex-1 space-y-2.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-4/5" />
              <div className="grid sm:grid-cols-2 gap-2 pt-1">
                <Skeleton className="h-8 w-full rounded-lg" />
                <Skeleton className="h-8 w-full rounded-lg" />
                <Skeleton className="h-8 w-full rounded-lg" />
                <Skeleton className="h-8 w-full rounded-lg" />
              </div>
              <div className="flex gap-1.5 pt-1">
                <Skeleton className="h-5 w-12 rounded-full" />
                <Skeleton className="h-5 w-16 rounded-full" />
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------
// Chapters list (question paper builder)
// ------------------------------------------------------------
export function ChapterListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <SkeletonRegion label="Loading chapters…" className="space-y-1.5">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-slate-200">
          <Skeleton className="h-4 w-4" />
          <Skeleton className="h-4 flex-1 max-w-xs" />
          <Skeleton className="h-7 w-16 rounded-lg ml-auto" />
        </div>
      ))}
    </SkeletonRegion>
  );
}

// ------------------------------------------------------------
// Figure library
// ------------------------------------------------------------
export function FigureGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <SkeletonRegion label="Loading figures…" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-white rounded-xl border border-slate-200 p-4 flex flex-col gap-3">
          <Skeleton className="h-32 w-full rounded-lg" />
          <div className="flex gap-1.5">
            <Skeleton className="h-5 w-16 rounded-full" />
            <Skeleton className="h-5 w-24 rounded-full" />
          </div>
          <Skeleton className="h-3 w-3/4" />
          <div className="flex gap-2 pt-2 border-t border-slate-100">
            <Skeleton className="h-7 w-16 rounded-lg" />
            <Skeleton className="h-7 w-20 rounded-lg" />
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}
