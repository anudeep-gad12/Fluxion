/**
 * Hook for managing ChatGPT OAuth authentication state.
 *
 * Handles:
 * - Polling /api/auth/chatgpt/status for auth state
 * - Opening popup window for OAuth login
 * - Listening for postMessage from callback popup
 * - Provider preference persistence (localStorage)
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const PROVIDER_PREF_KEY = 'reasoner_provider';
const API_BASE = '/api';

export type Provider = 'deepinfra' | 'chatgpt';

interface ChatGPTAuthStatus {
  enabled: boolean;
  authenticated: boolean;
  account_id?: string;
  expires_at?: number;
  model?: string;
}

interface UseChatGPTAuth {
  /** Whether the ChatGPT OAuth feature is enabled on the backend */
  enabled: boolean;
  /** Whether the user is authenticated with ChatGPT */
  authenticated: boolean;
  /** Truncated account ID (for display) */
  accountId: string | null;
  /** Default model when using ChatGPT provider */
  model: string | null;
  /** Currently selected provider */
  provider: Provider;
  /** Set the active provider */
  setProvider: (p: Provider) => void;
  /** Open the ChatGPT login popup */
  login: () => void;
  /** Log out of ChatGPT */
  logout: () => Promise<void>;
  /** Whether a login popup is currently open */
  loginPending: boolean;
}

export function useChatGPTAuth(): UseChatGPTAuth {
  const [status, setStatus] = useState<ChatGPTAuthStatus>({
    enabled: false,
    authenticated: false,
  });
  const [provider, setProviderState] = useState<Provider>(() => {
    const stored = localStorage.getItem(PROVIDER_PREF_KEY);
    return stored === 'chatgpt' ? 'chatgpt' : 'deepinfra';
  });
  const [loginPending, setLoginPending] = useState(false);
  const popupRef = useRef<Window | null>(null);

  // Fetch auth status on mount
  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/chatgpt/status`);
      if (response.ok) {
        const data: ChatGPTAuthStatus = await response.json();
        setStatus(data);

        // If not authenticated but provider is chatgpt, reset to deepinfra
        if (!data.authenticated && provider === 'chatgpt') {
          setProviderState('deepinfra');
          localStorage.setItem(PROVIDER_PREF_KEY, 'deepinfra');
        }
      }
    } catch {
      // Status endpoint unavailable - feature disabled
      setStatus({ enabled: false, authenticated: false });
    }
  }, [provider]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Listen for postMessage from OAuth popup
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === 'chatgpt-auth-success') {
        setLoginPending(false);
        // Re-fetch status after successful login
        fetchStatus();
      }
    }

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [fetchStatus]);

  // Poll for popup close (in case postMessage fails)
  useEffect(() => {
    if (!loginPending || !popupRef.current) return;

    const interval = setInterval(() => {
      if (popupRef.current?.closed) {
        setLoginPending(false);
        popupRef.current = null;
        // Re-fetch status in case login succeeded
        fetchStatus();
      }
    }, 500);

    return () => clearInterval(interval);
  }, [loginPending, fetchStatus]);

  const login = useCallback(() => {
    // Open popup to OAuth login endpoint
    const width = 500;
    const height = 700;
    const left = window.screenX + (window.innerWidth - width) / 2;
    const top = window.screenY + (window.innerHeight - height) / 2;

    const popup = window.open(
      `${API_BASE}/auth/chatgpt/login`,
      'chatgpt-login',
      `width=${width},height=${height},left=${left},top=${top},toolbar=no,menubar=no`,
    );

    if (popup) {
      popupRef.current = popup;
      setLoginPending(true);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/auth/chatgpt/logout`, { method: 'POST' });
    } catch {
      // Ignore errors
    }
    setStatus((prev) => ({ ...prev, authenticated: false }));
    setProviderState('deepinfra');
    localStorage.setItem(PROVIDER_PREF_KEY, 'deepinfra');
  }, []);

  const setProvider = useCallback(
    (p: Provider) => {
      setProviderState(p);
      localStorage.setItem(PROVIDER_PREF_KEY, p);
    },
    [],
  );

  return {
    enabled: status.enabled,
    authenticated: status.authenticated,
    accountId: status.account_id ?? null,
    model: status.model ?? null,
    provider,
    setProvider,
    login,
    logout,
    loginPending,
  };
}
