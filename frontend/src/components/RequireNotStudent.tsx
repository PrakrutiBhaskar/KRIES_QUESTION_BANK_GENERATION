import { Navigate } from 'react-router-dom';
import { useApp } from '../hooks/useApp';

/**
 * Keeps student accounts off the Generate page. UI convenience only: the API
 * refuses live generation for students too (403 `generation_disabled_for_students`).
 */
export default function RequireNotStudent({ children }: { children: React.ReactNode }) {
  const { user } = useApp();
  if (user?.role === 'Student') return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
