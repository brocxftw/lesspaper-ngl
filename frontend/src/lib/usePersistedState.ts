import { useEffect, useState } from "react";

export function usePersistedState<T>(
  key: string,
  defaultValue: T,
  legacyKey?: string,
) {
  const [value, setValue] = useState<T>(() => {
    try {
      let raw = localStorage.getItem(key);
      if (raw == null && legacyKey) {
        raw = localStorage.getItem(legacyKey);
        if (raw != null) {
          localStorage.setItem(key, raw);
        }
      }
      if (raw == null) return defaultValue;
      return JSON.parse(raw) as T;
    } catch {
      return defaultValue;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* ignore quota / private mode */
    }
  }, [key, value]);

  return [value, setValue] as const;
}
