import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Globe2, RotateCw, Search, XCircle } from 'lucide-react';
import { invoke } from '@tauri-apps/api/core';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';
import { listen, type UnlistenFn } from '@tauri-apps/api/event';
import { Webview } from '@tauri-apps/api/webview';

import type { BrowserTabState } from '@/hooks/useStore';
import { cn } from '@/lib/utils';

interface BrowserPaneProps {
  conversationId: string;
  tab: BrowserTabState;
  active: boolean;
  obscured?: boolean;
  onUpdate: (tabId: string, updates: Partial<BrowserTabState>) => void;
  onOpenNewTab?: (url: string) => void;
}

function browserLabel(conversationId: string, tabId: string): string {
  return `fluxion-browser-${conversationId}-${tabId}`.replace(/[^a-zA-Z0-9\-_:]/g, '-');
}

function displayTitle(url: string): string {
  if (!url) return 'New Browser';
  try {
    const parsed = new URL(url);
    return parsed.hostname || parsed.href;
  } catch {
    return url;
  }
}

function normalizeBrowserInput(input: string): string {
  const value = input.trim();
  if (!value) return '';
  if (/^(https?|file):\/\//i.test(value) || value.toLowerCase() === 'about:blank') {
    return value;
  }
  if (/^(localhost|127(?:\.\d{1,3}){3}|\[?::1\]?)(:\d+)?([/?#].*)?$/i.test(value)) {
    return `http://${value}`;
  }
  if (/^[\w.-]+\.[a-z]{2,}(:\d+)?([/?#].*)?$/i.test(value)) {
    return `https://${value}`;
  }
  return `https://www.google.com/search?q=${encodeURIComponent(value)}`;
}

export function BrowserPane({
  conversationId,
  tab,
  active,
  obscured = false,
  onUpdate,
  onOpenNewTab,
}: BrowserPaneProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const webviewRef = useRef<Webview | null>(null);
  const lastUrlRef = useRef(tab.url);
  const labelRef = useRef(tab.webviewLabel || browserLabel(conversationId, tab.id));
  const mountedRef = useRef(true);
  const [address, setAddress] = useState(tab.url);

  useEffect(() => {
    setAddress(tab.url);
  }, [tab.url]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const syncBounds = useCallback(async () => {
    const webview = webviewRef.current;
    const node = viewportRef.current;
    if (!webview || !node || !active || obscured) return;
    const rect = node.getBoundingClientRect();
    if (rect.width < 8 || rect.height < 8) return;
    await webview.setPosition(new LogicalPosition(Math.round(rect.left), Math.round(rect.top)));
    await webview.setSize(new LogicalSize(Math.round(rect.width), Math.round(rect.height)));
  }, [active, obscured]);

  const hideWebview = useCallback(() => {
    void webviewRef.current?.hide().catch(() => undefined);
  }, []);

  const showWebview = useCallback(async () => {
    if (!tab.url || obscured) return;
    if (!webviewRef.current) {
      const rect = viewportRef.current?.getBoundingClientRect();
      if (!rect || rect.width < 8 || rect.height < 8) return;
      onUpdate(tab.id, { status: 'loading', error: null });
      try {
        await invoke('fluxion_browser_create', {
          label: labelRef.current,
          url: tab.url,
          x: Math.round(rect.left),
          y: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height),
        });
        const webview = await Webview.getByLabel(labelRef.current);
        if (!webview) {
          throw new Error('Could not attach browser webview');
        }
        if (!mountedRef.current) {
          void webview.close().catch(() => undefined);
          return;
        }
        webviewRef.current = webview;
        lastUrlRef.current = tab.url;
        onUpdate(tab.id, { status: 'ready', title: displayTitle(tab.url), error: null });
        void syncBounds();
      } catch (error) {
        if (!mountedRef.current) return;
        onUpdate(tab.id, {
          status: 'error',
          error: String(error || 'Could not load browser tab'),
        });
      }
      return;
    }
    await webviewRef.current.show();
    await syncBounds();
  }, [obscured, onUpdate, syncBounds, tab.id, tab.url]);

  useEffect(() => {
    let unlisten: UnlistenFn | undefined;
    let cancelled = false;
    void listen<{ source_label: string; url: string }>('fluxion-browser-new-window', (event) => {
      if (event.payload?.source_label !== labelRef.current) return;
      if (event.payload.url) onOpenNewTab?.(event.payload.url);
    }).then((cleanup) => {
      if (cancelled) cleanup();
      else unlisten = cleanup;
    });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [onOpenNewTab]);

  useEffect(() => {
    if (!active || obscured) {
      hideWebview();
      return;
    }
    if (!tab.url) {
      hideWebview();
      window.setTimeout(() => inputRef.current?.focus(), 0);
      return;
    }
    void showWebview();
  }, [active, hideWebview, obscured, showWebview, tab.url]);

  useEffect(() => {
    if (!active || obscured || !tab.url || !webviewRef.current || lastUrlRef.current === tab.url) return;
    lastUrlRef.current = tab.url;
    onUpdate(tab.id, { status: 'loading', title: displayTitle(tab.url), error: null });
    void invoke('fluxion_browser_navigate', {
      label: labelRef.current,
      url: tab.url,
    })
      .then(() => onUpdate(tab.id, { status: 'ready', title: displayTitle(tab.url), error: null }))
      .catch((error) => onUpdate(tab.id, { status: 'error', error: String(error) }));
  }, [active, obscured, onUpdate, tab.id, tab.url]);

  useEffect(() => {
    if (!active || obscured) return;
    const observer = new ResizeObserver(() => void syncBounds());
    if (viewportRef.current) observer.observe(viewportRef.current);
    window.addEventListener('resize', syncBounds);
    const raf = requestAnimationFrame(() => void syncBounds());
    const interval = window.setInterval(() => void syncBounds(), 250);
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', syncBounds);
      cancelAnimationFrame(raf);
      window.clearInterval(interval);
    };
  }, [active, obscured, syncBounds]);

  useEffect(() => {
    return () => {
      void webviewRef.current?.close().catch(() => undefined);
      webviewRef.current = null;
    };
  }, []);

  const navigate = useCallback((raw: string) => {
    const nextUrl = normalizeBrowserInput(raw);
    if (!nextUrl) return;
    setAddress(nextUrl);
    onUpdate(tab.id, {
      url: nextUrl,
      title: displayTitle(nextUrl),
      status: 'loading',
      error: null,
    });
  }, [onUpdate, tab.id]);

  const runBrowserCommand = useCallback((command: string) => {
    if (!webviewRef.current) return;
    void invoke(command, { label: labelRef.current })
      .then(() => onUpdate(tab.id, { status: 'ready', error: null }))
      .catch((error) => onUpdate(tab.id, { status: 'error', error: String(error) }));
  }, [onUpdate, tab.id]);

  return (
    <div className={cn('flex h-full min-h-0 flex-col', !active && 'hidden')}>
      <div className="desktop-browser-toolbar flex h-11 shrink-0 items-center gap-1 border-b border-white/[0.06] bg-[var(--desktop-bg-0)] px-2">
        <button
          type="button"
          className="desktop-browser-nav-btn"
          onClick={() => runBrowserCommand('fluxion_browser_go_back')}
          disabled={!tab.url}
          title="Back"
          aria-label="Back"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="desktop-browser-nav-btn"
          onClick={() => runBrowserCommand('fluxion_browser_go_forward')}
          disabled={!tab.url}
          title="Forward"
          aria-label="Forward"
        >
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="desktop-browser-nav-btn"
          onClick={() => runBrowserCommand('fluxion_browser_reload')}
          disabled={!tab.url}
          title="Reload"
          aria-label="Reload"
        >
          <RotateCw className="h-3.5 w-3.5" />
        </button>
        <form
          className="relative min-w-0 flex-1"
          onSubmit={(event) => {
            event.preventDefault();
            navigate(address);
          }}
        >
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-zinc-600" />
          <input
            ref={inputRef}
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="Search or enter URL"
            className="desktop-browser-address h-7 w-full rounded-lg border border-white/[0.07] bg-white/[0.035] pl-8 pr-3 text-[12px] text-zinc-300 outline-none transition-colors placeholder:text-zinc-600 focus:border-cyan-300/30 focus:bg-white/[0.055]"
          />
        </form>
      </div>
      <div className="relative min-h-0 flex-1 bg-[#141212]">
        <div ref={viewportRef} className="absolute inset-0" />
        {!tab.url ? (
          <div className="pointer-events-none absolute inset-0 flex items-start gap-2 px-5 py-5 text-[12px] text-zinc-600">
            <Globe2 className="mt-0.5 h-4 w-4" />
            <span>Enter a URL or search above</span>
          </div>
        ) : null}
        {tab.status === 'loading' ? (
          <div className="pointer-events-none absolute left-0 right-0 top-0 h-px overflow-hidden bg-cyan-300/20">
            <div className="h-full w-1/3 animate-pulse bg-cyan-300/70" />
          </div>
        ) : null}
        {tab.status === 'error' ? (
          <div className="absolute inset-x-3 top-3 flex items-start gap-2 rounded-lg border border-red-400/20 bg-red-500/10 px-3 py-2 text-[12px] text-red-200">
            <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="break-words">{tab.error || 'Browser failed to load this page'}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}
