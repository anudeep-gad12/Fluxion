/** True when running inside the Tauri shell (embedded asset URL before navigate). */
export function isTauriWebview(): boolean {
  if (typeof window === 'undefined') return false;
  const { protocol, hostname } = window.location;
  if (protocol === 'tauri:') return true;
  return hostname === 'tauri.localhost' || hostname.endsWith('.tauri.localhost');
}

/** True when the UI is served from the local desktop app (Tauri / packaged API on :9000). */
export function isLocalDesktopApp(): boolean {
  if (typeof window === 'undefined') return false;
  if (isTauriWebview()) return true;
  const { hostname, port } = window.location;
  return (hostname === '127.0.0.1' || hostname === 'localhost') && port === '9000';
}

/** True only when the page is actually running inside the Tauri IPC runtime. */
export function isTauriRuntime(): boolean {
  if (typeof window === 'undefined') return false;
  return isTauriWebview() || '__TAURI_INTERNALS__' in window || '__TAURI__' in window;
}

/** Apply desktop dataset on <html> for scoped CSS. */
export function applyDesktopPlatformClass(forceDesktop = false): void {
  if (typeof document === 'undefined') return;
  if (forceDesktop || isLocalDesktopApp()) {
    document.documentElement.dataset.app = 'desktop';
    return;
  }
  delete document.documentElement.dataset.app;
}

/** Also enable desktop styling when the API reports a local packaged app (e.g. after config fetch). */
export async function syncDesktopPlatformClassFromApi(): Promise<void> {
  if (isLocalDesktopApp()) {
    applyDesktopPlatformClass(true);
    return;
  }
  try {
    const { getApiBase } = await import('@/api/client');
    const response = await fetch(`${getApiBase()}/config`);
    if (!response.ok) return;
    const data = (await response.json()) as { local_app?: boolean };
    if (data.local_app) {
      applyDesktopPlatformClass(true);
    }
  } catch {
    // Ignore — non-fatal
  }
}

export function isApplePlatform(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform);
}

/** Open a URL in the system browser from Tauri, falling back to window.open on web. */
export async function openExternalUrl(url: string): Promise<boolean> {
  if (typeof window === 'undefined') return false;

  if (isLocalDesktopApp()) {
    try {
      const { invoke } = await import('@tauri-apps/api/core');
      await invoke('plugin:opener|open_url', { url });
      return true;
    } catch {
      // Not actually in Tauri, or opener unavailable. Fall through to web open.
    }
  }

  const opened = window.open(url, '_blank', 'noopener,noreferrer');
  return !!opened;
}

/** Open a local path from terminal output in the default desktop app. */
export async function openExternalPath(path: string, workspacePath?: string): Promise<boolean> {
  if (typeof window === 'undefined' || !isLocalDesktopApp()) return false;

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('fluxion_open_terminal_path', {
      path,
      workspacePath: workspacePath?.trim() || null,
    });
    return true;
  } catch {
    return false;
  }
}

/** Open the system folder picker and return a selected directory path. */
export async function openNativeWorkspacePicker(): Promise<string | null> {
  if (typeof window === 'undefined') return null;

  try {
    const { invoke } = await import('@tauri-apps/api/core');
    const selected = await invoke<string | string[] | null>('plugin:dialog|open', {
      options: {
        directory: true,
        multiple: false,
        title: 'Choose Workspace',
      },
    });
    if (Array.isArray(selected)) {
      return selected[0] || null;
    }
    return selected || null;
  } catch {
    return null;
  }
}
