import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

import { browseWorkspaceDirectories, type WorkspaceBrowseResponse } from '@/api/client';
import { cn } from '@/lib/utils';
import { isLocalDesktopApp, openNativeWorkspacePicker } from '@/lib/platform';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';

export function WorkspacePickerDialog({
  open,
  onOpenChange,
  value,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onSelect: (path: string) => void;
}) {
  const [data, setData] = useState<WorkspaceBrowseResponse | null>(null);
  const [pathInput, setPathInput] = useState(value);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [pendingFocusTarget, setPendingFocusTarget] = useState<'input' | 'list'>('input');
  const inputRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const onSelectRef = useRef(onSelect);
  const onOpenChangeRef = useRef(onOpenChange);

  useEffect(() => {
    onSelectRef.current = onSelect;
    onOpenChangeRef.current = onOpenChange;
  }, [onOpenChange, onSelect]);

  const visibleEntries = useMemo(() => {
    const rows: Array<{ key: string; path: string; label: string; hidden?: boolean; isParent?: boolean }> = [];
    if (data?.parent) {
      rows.push({ key: '__parent__', path: data.parent, label: '../', isParent: true });
    }
    for (const entry of data?.entries ?? []) {
      rows.push({
        key: entry.path,
        path: entry.path,
        label: `${entry.name}/`,
        hidden: entry.hidden,
      });
    }
    return rows;
  }, [data]);

  const loadPath = useCallback((path?: string, nextFocusTarget: 'input' | 'list' = 'input') => {
    setLoading(true);
    setError(null);
    setPendingFocusTarget(nextFocusTarget);
    browseWorkspaceDirectories(path || undefined)
      .then((next) => {
        setData(next);
        setPathInput(next.path);
        setActiveIndex(0);
      })
      .catch((err: { message?: string }) => setError(err.message || 'Failed to browse path'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!open) return;
    if (isLocalDesktopApp()) {
      let cancelled = false;
      void openNativeWorkspacePicker().then((selectedPath) => {
        if (cancelled) return;
        if (selectedPath) {
          onSelectRef.current(selectedPath);
        }
        onOpenChangeRef.current(false);
      });
      return () => {
        cancelled = true;
      };
    }
    setPathInput(value);
    setActiveIndex(0);
    loadPath(value || undefined, 'input');
  }, [open, value, loadPath]);

  const chooseCurrent = () => {
    if (!data?.path) return;
    onSelect(data.path);
    onOpenChange(false);
  };

  useEffect(() => {
    if (!open) return;
    const focusTarget = pendingFocusTarget;
    const rafId = window.requestAnimationFrame(() => {
      if (focusTarget === 'list' && visibleEntries.length > 0) {
        rowRefs.current[activeIndex]?.focus();
        return;
      }
      inputRef.current?.focus();
      if (focusTarget === 'input') {
        inputRef.current?.select();
      }
    });
    return () => window.cancelAnimationFrame(rafId);
  }, [activeIndex, open, pendingFocusTarget, visibleEntries.length]);

  const focusRow = useCallback((index: number) => {
    if (visibleEntries.length === 0) return;
    const nextIndex = Math.max(0, Math.min(index, visibleEntries.length - 1));
    setActiveIndex(nextIndex);
    setPendingFocusTarget('list');
    rowRefs.current[nextIndex]?.focus();
  }, [visibleEntries.length]);

  const openActiveRow = useCallback((index: number) => {
    const row = visibleEntries[index];
    if (!row) return;
    loadPath(row.path, 'list');
  }, [loadPath, visibleEntries]);

  const navigateParent = useCallback(() => {
    if (!data?.parent) return;
    loadPath(data.parent, 'list');
  }, [data?.parent, loadPath]);

  const handleDialogKeyDown = useCallback((event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onOpenChange(false);
      return;
    }
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      chooseCurrent();
    }
  }, [onOpenChange, chooseCurrent]);

  const desktop = isLocalDesktopApp();

  return (
    <Dialog open={open} onOpenChange={onOpenChange} className="max-w-3xl">
      <DialogHeader>
        <DialogTitle>Choose workspace</DialogTitle>
        <DialogDescription className={cn(
          desktop ? 'desktop-settings-hint text-[12px] leading-6' : 'font-mono text-[12px] leading-6 text-zinc-500'
        )}>
          Browse to the repo root. Enter opens a folder. Cmd/Ctrl+Enter selects the current path.
        </DialogDescription>
      </DialogHeader>
      <DialogContent>
        <div className={cn('space-y-4', !desktop && 'font-mono text-xs')} onKeyDown={handleDialogKeyDown}>
          <div className="flex gap-2">
            <input
              ref={inputRef}
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  loadPath(pathInput, 'input');
                  return;
                }
                if (e.key === 'ArrowDown' && visibleEntries.length > 0) {
                  e.preventDefault();
                  focusRow(0);
                  return;
                }
                if (e.key === 'ArrowUp' && visibleEntries.length > 0) {
                  e.preventDefault();
                  focusRow(visibleEntries.length - 1);
                }
              }}
              className={cn(desktop ? 'desktop-settings-field flex-1' : 'premium-field flex-1')}
              placeholder="/path/to/repo"
            />
            <button
              onClick={() => loadPath(pathInput, 'input')}
              className={cn(desktop ? 'desktop-settings-btn-ghost px-4' : 'premium-subtle-button px-4')}
              type="button"
            >
              open
            </button>
          </div>

          {error && (
            <p className={cn(
              desktop ? 'desktop-settings-hint-error' : 'rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-red-300'
            )}>{error}</p>
          )}

          <div className={cn(
            desktop ? 'desktop-settings-list-panel' : 'premium-panel max-h-[24rem] overflow-y-auto p-1.5'
          )}>
            {loading ? (
              <p className={cn(desktop ? 'desktop-settings-hint px-3 py-3' : 'px-3 py-3 text-zinc-400')}>Loading directories...</p>
            ) : visibleEntries.length === 0 ? (
              <p className={cn(desktop ? 'desktop-settings-hint px-3 py-3' : 'px-3 py-3 text-zinc-500')}>No subdirectories found here.</p>
            ) : (
              visibleEntries.map((entry, index) => (
                <button
                  key={entry.key}
                  ref={(node) => {
                    rowRefs.current[index] = node;
                  }}
                  onClick={() => loadPath(entry.path, 'list')}
                  onFocus={() => {
                    setActiveIndex(index);
                    setPendingFocusTarget('list');
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      focusRow(index + 1);
                      return;
                    }
                    if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      focusRow(index - 1);
                      return;
                    }
                    if (e.key === 'Home') {
                      e.preventDefault();
                      focusRow(0);
                      return;
                    }
                    if (e.key === 'End') {
                      e.preventDefault();
                      focusRow(visibleEntries.length - 1);
                      return;
                    }
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      openActiveRow(index);
                      return;
                    }
                    if (e.key === 'Backspace' || (e.altKey && e.key === 'ArrowUp')) {
                      e.preventDefault();
                      navigateParent();
                    }
                  }}
                  data-active={desktop && activeIndex === index ? 'true' : undefined}
                  className={cn(
                    desktop
                      ? 'desktop-settings-list-item text-left'
                      : 'ui-transition block w-full rounded-[0.95rem] px-3 py-2.5 text-left outline-none',
                    !desktop && activeIndex === index
                      ? 'border border-cyan-300/28 bg-cyan-300/[0.08] text-zinc-50'
                      : !desktop && 'border border-transparent text-zinc-300 hover:border-white/10 hover:bg-white/[0.045] hover:text-cyan-100',
                    !desktop && entry.hidden ? 'text-zinc-500' : '',
                    desktop && entry.hidden ? 'opacity-60' : '',
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className={cn(desktop ? 'desktop-settings-list-title truncate' : 'truncate')}>{entry.label}</span>
                    {entry.isParent ? (
                      <span className={cn(desktop ? 'desktop-settings-list-meta uppercase' : 'text-[10px] uppercase tracking-[0.18em] text-zinc-500')}>parent</span>
                    ) : entry.hidden ? (
                      <span className={cn(desktop ? 'desktop-settings-list-meta uppercase' : 'text-[10px] uppercase tracking-[0.18em] text-zinc-500')}>hidden</span>
                    ) : null}
                  </div>
                </button>
              ))
            )}
          </div>

          <div className={cn(
            desktop ? 'desktop-settings-section flex items-center justify-between gap-3 !mb-0 !border-b-0 !pb-0' : 'premium-panel flex items-center justify-between gap-3 px-4 py-3'
          )}>
            <div className="min-w-0">
              <div className={cn(desktop ? 'desktop-settings-label !mb-1' : 'premium-section-label')}>selected path</div>
              <div className={cn(desktop ? 'desktop-settings-model-line truncate' : 'mt-1 truncate text-zinc-300')}>{data?.path || pathInput}</div>
            </div>
            <button
              onClick={chooseCurrent}
              disabled={!data?.path}
              className={cn(desktop ? 'desktop-settings-btn-primary shrink-0' : 'premium-primary-button shrink-0')}
              type="button"
            >
              use folder
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
