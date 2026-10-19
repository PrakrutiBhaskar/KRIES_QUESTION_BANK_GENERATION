import { describe, expect, it } from 'vitest';
import { canEditContent } from './roles';

describe('canEditContent', () => {
  it('lets teachers and administrators edit', () => {
    expect(canEditContent('Teacher')).toBe(true);
    expect(canEditContent('Admin')).toBe(true);
  });

  it('keeps students out', () => {
    expect(canEditContent('Student')).toBe(false);
  });

  it('keeps out anyone who is not signed in', () => {
    expect(canEditContent(undefined)).toBe(false);
  });
});
