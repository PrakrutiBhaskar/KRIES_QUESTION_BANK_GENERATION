import type { AppSettings } from '../types';

export type Theme = AppSettings['theme'];

const DARK_QUERY = '(prefers-color-scheme: dark)';

export function prefersDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(DARK_QUERY).matches;
}

/** Put the theme on <html>: the `dark` class drives the palette in index.css. */
export function applyTheme(theme: Theme): void {
  const dark = theme === 'dark' || (theme === 'system' && prefersDark());
  const root = document.documentElement;
  root.classList.toggle('dark', dark);
  root.style.colorScheme = dark ? 'dark' : 'light';
}

/** Re-apply when the OS switches between light and dark (only matters for 'system'). */
export function watchSystemTheme(onChange: () => void): () => void {
  const mq = window.matchMedia(DARK_QUERY);
  mq.addEventListener('change', onChange);
  return () => mq.removeEventListener('change', onChange);
}
