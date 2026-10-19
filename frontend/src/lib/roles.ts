import type { User } from '../types';

/**
 * Who may edit existing content (questions, answer keys, marks splits, papers):
 * teachers and administrators. Students can generate, practise and export, but
 * not edit. UI convenience only: the API enforces the same rule (403 `editor_required`).
 */
export function canEditContent(role: User['role'] | undefined): boolean {
  return role === 'Admin' || role === 'Teacher';
}
