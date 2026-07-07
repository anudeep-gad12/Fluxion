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
export type ThemePreference = Theme | 'system';

interface ThemeContextValue {
  preference: ThemePreference;
  theme: Theme;
  setPreference: (preference: ThemePreference) => void;
}

const THEME_STORAGE_KEY = 'theme';
const ThemeContext = createContext<ThemeContextValue | null>(null);

function savedPreference(): ThemePreference {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === 'light' || value === 'dark' || value === 'system' ? value : 'system';
  } catch {
    return 'system';
  }
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function initialResolvedTheme(preference: ThemePreference): Theme {
  const bootstrapped = document.documentElement.dataset.theme;
  if (bootstrapped === 'light' || bootstrapped === 'dark') return bootstrapped;
  return preference === 'system' ? systemTheme() : preference;
}

function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  const chromeBg = getComputedStyle(document.documentElement)
    .getPropertyValue('--desktop-bg-0')
    .trim();
  if (chromeBg) {
    document
      .querySelector<HTMLMetaElement>('meta[name="theme-color"]')
      ?.setAttribute('content', chromeBg);
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const desktop = isLocalDesktopApp();
  const [preference, setPreferenceState] = useState<ThemePreference>(() => (
    desktop ? savedPreference() : 'dark'
  ));
  const [resolvedSystemTheme, setResolvedSystemTheme] = useState<Theme>(() => (
    desktop ? initialResolvedTheme(preference) : 'dark'
  ));
  const theme = preference === 'system' ? resolvedSystemTheme : preference;
  const appliedTheme = useRef<Theme | null>(null);

  useEffect(() => {
    if (!desktop) return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => setResolvedSystemTheme(media.matches ? 'dark' : 'light');
    handleChange();
    media.addEventListener('change', handleChange);
    return () => media.removeEventListener('change', handleChange);
  }, [desktop]);

  useEffect(() => {
    if (!desktop) return;

    // Crossfade colors when the visible theme actually changes (not on the
    // initial paint, which already matches the bootstrapped theme). A one-shot
    // .theme-animating window drives the transition in index.css.
    const previous = appliedTheme.current;
    appliedTheme.current = theme;
    if (previous && previous !== theme) {
      const root = document.documentElement;
      root.classList.add('theme-animating');
      window.setTimeout(() => root.classList.remove('theme-animating'), 260);
    }

    applyTheme(theme);

    if (isTauriRuntime()) {
      void import('@tauri-apps/api/window')
        .then(({ getCurrentWindow }) => (
          getCurrentWindow().setTheme(preference === 'system' ? null : preference)
        ))
        .catch(() => undefined);
    }
  }, [desktop, preference, theme]);

  const setPreference = useCallback((nextPreference: ThemePreference) => {
    if (!desktop) return;
    try {
      localStorage.setItem(THEME_STORAGE_KEY, nextPreference);
    } catch {
      // Keep the in-memory choice when storage is unavailable.
    }
    setPreferenceState(nextPreference);
  }, [desktop]);

  const value = useMemo(
    () => ({ preference, theme, setPreference }),
    [preference, setPreference, theme],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside ThemeProvider');
  return value;
}
