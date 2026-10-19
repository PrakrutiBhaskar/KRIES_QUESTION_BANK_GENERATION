export interface ParsedChapter {
  name: string;
  topics: string[];
}

/**
 * One chapter per line. Topics are optional: "Chapter name: topic one; topic two".
 * A leading bullet or number ("1.", "-") is dropped.
 */
export function parseChapters(text: string): ParsedChapter[] {
  const out: ParsedChapter[] = [];
  for (const raw of text.split('\n')) {
    const line = raw.replace(/^\s*(?:[-•*]|\d+[.)])\s+/, '').trim();
    if (!line) continue;
    const colon = line.indexOf(':');
    const name = (colon === -1 ? line : line.slice(0, colon)).trim();
    const topics = colon === -1 ? [] : line.slice(colon + 1).split(';').map((t) => t.trim()).filter(Boolean);
    if (name) out.push({ name, topics });
  }
  return out;
}
