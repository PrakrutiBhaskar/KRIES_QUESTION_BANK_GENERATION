import { useEffect, useState } from 'react';
import { ImageOff, Loader2 } from 'lucide-react';
import type { Figure } from '../types';
import { fetchFigureUrl } from '../lib/api';

/**
 * Shows a stored figure. The image route needs the bearer token, which an
 * <img src> cannot send, so the bytes are fetched with it (see fetchFigureUrl).
 */
export function FigureImage({ figure, className = '' }: { figure: Figure; className?: string }) {
  // The result is tagged with the figure it belongs to, so a stale result from
  // a previous figure is ignored without resetting state inside the effect.
  const [result, setResult] = useState<{ id: string; src?: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchFigureUrl(figure.id)
      .then((src) => { if (!cancelled) setResult({ id: figure.id, src }); })
      .catch(() => { if (!cancelled) setResult({ id: figure.id }); });
    return () => { cancelled = true; };
  }, [figure.id]);

  const current = result?.id === figure.id ? result : null;
  const src = current?.src ?? null;
  const failed = current !== null && !current.src;

  return (
    <figure className={`inline-block max-w-full ${className}`}>
      {src ? (
        <img
          src={src}
          alt={figure.caption || 'Figure'}
          width={figure.width}
          height={figure.height}
          className="max-h-56 w-auto max-w-full rounded-lg border border-slate-200 bg-white object-contain"
        />
      ) : (
        <div className="flex h-24 w-40 items-center justify-center rounded-lg border border-dashed border-slate-200 bg-slate-50 text-slate-400">
          {failed ? <ImageOff className="h-5 w-5" aria-label="Figure unavailable" /> : <Loader2 className="h-5 w-5 animate-spin" />}
        </div>
      )}
      {figure.caption && (
        <figcaption className="mt-1 text-xs italic text-slate-500">{figure.caption}</figcaption>
      )}
    </figure>
  );
}
