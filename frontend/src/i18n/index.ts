/**
 * M18 — i18n setup using a lightweight built-in solution.
 *
 * We use a minimal custom i18n hook rather than bundling react-i18next to
 * avoid adding heavy dependencies. The hook provides the same `t(key)` API
 * and can be swapped for react-i18next later with no call-site changes.
 *
 * Supported locales: "en" (default), "es"
 * Locale persisted in localStorage under "omniai_locale".
 */

import { useCallback, useEffect, useState } from "react";
import { en } from "./en";
import { es } from "./es";

export type Locale = "en" | "es";

type TranslationTree = typeof en.translation;

const LOCALES: Record<Locale, { translation: TranslationTree }> = { en, es };

const STORAGE_KEY = "omniai_locale";

function getInitialLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "es") return stored;
  const nav = navigator.language.slice(0, 2).toLowerCase();
  return nav === "es" ? "es" : "en";
}

/** Resolve a dot-separated key path (e.g. "knowledge.delete") from a nested object. */
function resolve(obj: Record<string, unknown>, path: string): string {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== "object") return path;
    cur = (cur as Record<string, unknown>)[p];
  }
  return typeof cur === "string" ? cur : path;
}

/** Replace {{variable}} placeholders in a translated string. */
function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, k) =>
    vars[k] !== undefined ? String(vars[k]) : `{{${k}}}`
  );
}

export function useI18n() {
  const [locale, setLocaleState] = useState<Locale>(getInitialLocale);

  const setLocale = useCallback((next: Locale) => {
    localStorage.setItem(STORAGE_KEY, next);
    setLocaleState(next);
    document.documentElement.lang = next;
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>): string => {
      const tree = LOCALES[locale]?.translation ?? en.translation;
      const raw = resolve(tree as Record<string, unknown>, key);
      return interpolate(raw, vars);
    },
    [locale]
  );

  return { t, locale, setLocale };
}

/** Singleton store so that components deep in the tree can call t() without prop drilling. */
type I18nStore = { t: (key: string, vars?: Record<string, string | number>) => string; locale: Locale };
let _store: I18nStore = {
  t: (key) => key,
  locale: "en",
};

export function setI18nStore(store: I18nStore) {
  _store = store;
}

/** Call this ONLY when you cannot use the hook (e.g. in utility functions). */
export function t(key: string, vars?: Record<string, string | number>): string {
  return _store.t(key, vars);
}
