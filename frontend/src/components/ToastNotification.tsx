import { useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import type { Toast } from '../hooks/useApp';

interface ToastNotificationProps {
  toast: Toast;
  onClose: () => void;
}

const ICONS = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const COLORS = {
  success: 'bg-emerald-50 border-emerald-200 text-emerald-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
};

const ICON_COLORS = {
  success: 'text-emerald-500',
  error: 'text-red-500',
  warning: 'text-amber-500',
  info: 'text-blue-500',
};

export default function ToastNotification({ toast, onClose }: ToastNotificationProps) {
  const Icon = ICONS[toast.type];

  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div
      className={`
        fixed bottom-6 right-6 z-50 flex items-start gap-3 px-4 py-3
        rounded-xl border shadow-lg min-w-[280px] max-w-sm
        animate-in slide-in-from-right-5 fade-in duration-200
        ${COLORS[toast.type]}
      `}
      role="alert"
    >
      <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${ICON_COLORS[toast.type]}`} />
      <p className="text-sm font-medium flex-1">{toast.message}</p>
      <button
        onClick={onClose}
        className="shrink-0 opacity-60 hover:opacity-100 transition-opacity"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
