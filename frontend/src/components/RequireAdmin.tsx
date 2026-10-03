import { Navigate } from 'react-router-dom';
import { useApp } from '../hooks/useApp';

/**
 * Keeps administrator-only pages away from everyone else. This is a convenience
 * for the UI only: the API enforces the same rule (403 `admin_required`), so
 * nothing here is a security boundary.
 */
export default function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { user } = useApp();
  if (user?.role !== 'Admin') return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}
