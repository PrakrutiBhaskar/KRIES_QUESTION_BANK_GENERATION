import { Navigate } from 'react-router-dom';
import { useApp } from '../hooks/useApp';
import { canEditContent } from '../lib/roles';

/**
 * Keeps pages that change shared content (such as the Syllabus page) away from
 * students: teachers and administrators only. A UI convenience; the API enforces
 * the same rule (403 `editor_required`).
 */
export default function RequireEditor({ children }: { children: React.ReactNode }) {
  const { user } = useApp();
  if (!canEditContent(user?.role)) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
