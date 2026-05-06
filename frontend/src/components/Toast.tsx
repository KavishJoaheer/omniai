/**
 * Toast notification system.
 *
 * Usage:
 *   const { toast } = useToast();
 *   toast("Saved!", "success");
 *   toast("Something went wrong.", "error");
 *
 * Wrap the app in <ToastProvider> once (done in App.tsx).
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

export type ToastKind = "success" | "error" | "info" | "warning";

export interface ToastItem {
  id: number;
  message: string;
  kind: ToastKind;
}

interface ToastCtx {
  toast: (message: string, kind?: ToastKind) => void;
}

const Ctx = createContext<ToastCtx>({ toast: () => {} });

let _nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
    const t = timers.current.get(id);
    if (t) { clearTimeout(t); timers.current.delete(id); }
  }, []);

  const toast = useCallback((message: string, kind: ToastKind = "info") => {
    const id = _nextId++;
    setItems((prev) => [...prev.slice(-4), { id, message, kind }]);
    const delay = kind === "error" ? 6000 : 3500;
    const timer = setTimeout(() => dismiss(id), delay);
    timers.current.set(id, timer);
  }, [dismiss]);

  // clean up on unmount
  useEffect(() => () => { timers.current.forEach(clearTimeout); }, []);

  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="false">
        {items.map((item) => (
          <div key={item.id} className={`toast toast-${item.kind}`}>
            <span className="toast-icon">{icons[item.kind]}</span>
            <span className="toast-msg">{item.message}</span>
            <button
              className="toast-close"
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(item.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

const icons: Record<ToastKind, string> = {
  success: "✓",
  error: "✕",
  info: "i",
  warning: "!",
};

export function useToast() {
  return useContext(Ctx);
}
