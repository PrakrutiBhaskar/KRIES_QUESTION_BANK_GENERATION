import { describe, expect, it } from 'vitest';
import { parseChapters } from './syllabus';

describe('parseChapters', () => {
  it('reads one chapter per line', () => {
    expect(parseChapters('Crop Production\nMicroorganisms')).toEqual([
      { name: 'Crop Production', topics: [] },
      { name: 'Microorganisms', topics: [] },
    ]);
  });

  it('reads topics after a colon, split on semicolons', () => {
    expect(parseChapters('Crop Production: Kharif crops; Rabi crops ;Irrigation')).toEqual([
      { name: 'Crop Production', topics: ['Kharif crops', 'Rabi crops', 'Irrigation'] },
    ]);
  });

  it('skips blank lines and trims whitespace', () => {
    expect(parseChapters('\n   Light  \n\n\t\nSound\n')).toEqual([
      { name: 'Light', topics: [] },
      { name: 'Sound', topics: [] },
    ]);
  });

  it('drops a leading bullet or number', () => {
    expect(parseChapters('1. Light\n2) Sound\n- Heat\n• Force\n* Pressure').map((c) => c.name)).toEqual([
      'Light', 'Sound', 'Heat', 'Force', 'Pressure',
    ]);
  });

  it('keeps a number that is part of the name', () => {
    expect(parseChapters('Class 8 Revision')[0].name).toBe('Class 8 Revision');
  });

  it('ignores a line that has topics but no chapter name', () => {
    expect(parseChapters(': orphan topic\nLight')).toEqual([{ name: 'Light', topics: [] }]);
  });

  it('returns nothing for empty input', () => {
    expect(parseChapters('')).toEqual([]);
    expect(parseChapters('  \n \n')).toEqual([]);
  });
});
