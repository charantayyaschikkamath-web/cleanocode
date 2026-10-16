import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';
import type { ReactNode } from 'react';

export type ToastMessage = { id: string; title: string; message?: string; kind: 'success' | 'error' | 'info' };

export function Toasts({ items, onDismiss }: { items: ToastMessage[]; onDismiss: (id: string) => void }) {
  return <div className="toast-stack" aria-live="polite" aria-relevant="additions">
    {items.map((item) => <div className={`toast toast-${item.kind}`} key={item.id}>
      <div className="toast-icon">{item.kind === 'success' ? <CheckCircle2 size={18} /> : item.kind === 'error' ? <AlertCircle size={18} /> : <Info size={18} />}</div>
      <div className="toast-copy"><strong>{item.title}</strong>{item.message && <span>{item.message}</span>}</div>
      <button className="icon-button" onClick={() => onDismiss(item.id)} aria-label="Dismiss notification"><X size={15} /></button>
    </div>)}
  </div>;
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-header">
    <div><div className="eyebrow">{eyebrow || 'CAMPUS OPERATIONS'}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>
    {actions && <div className="page-header-actions">{actions}</div>}
  </div>;
}
