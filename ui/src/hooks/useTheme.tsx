import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { isLocalDesktopApp, isTauriRuntime } from '@/lib/platform';

export type Theme = 'light' | 'dark';

interface ThemeContextValue {
  theme: Theme;
  toggleTheme: () => void;
}

const THEME_STORAGE_KEY = 'theme';
const ThemeContext = createContext<ThemeContextValue | null>(null);

function savedTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function initialTheme(): Theme {
  if (!isLocalDesktopApp()) return 'dark';
  const bootstrapped = document.documentElement.dataset.theme;
  if (bootstrapped === 'light' || bootstrapped === 'dark') return bootstrapped;
  return savedTheme() ?? systemTheme();
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute(
    'content',
    theme === 'light' ? '#f7f7f4' : '#09090b',
  );
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const desktop = isLocalDesktopApp();
  const [theme, setTheme] = useState<Theme>(initialTheme);
  const explicitChoiceRef = useRef(savedTheme() !== null);

  useEffect(() => {
    if (!desktop) return;
    applyTheme(theme);

    if (isTauriRuntime()) {
      void import('@tauri-apps/api/window')
        .then(({ getCurrentWindow }) => getCurrentWindow().setTheme(theme))
        .catch(() => undefined);
    }
  }, [desktop, theme]);

  useEffect(() => {
    if (!desktop || savedTheme()) return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (!explicitChoiceRef.current) {
        setTheme(media.matches ? 'dark' : 'light');
      }
    };
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [desktop]);

  const toggleTheme = useCallback(() => {
    if (!desktop) return;
    explicitChoiceRef.current = true;
    setTheme((current) => {
      const next = current === 'dark' ? 'light' : 'dark';
      try {
        localStorage.setItem(THEME_STORAGE_KEY, next);
      } catch {
        // Keep the in-memory choice when storage is unavailable.
      }
      return next;
    });
  }, [desktop]);

  const value = useMemo(() => ({ theme, toggleTheme }), [theme, toggleTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside ThemeProvider');
  return value;
}
