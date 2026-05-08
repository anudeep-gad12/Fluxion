import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';

import { browseWorkspaceDirectories, type WorkspaceBrowseResponse } from '@/api/client';
import { cn } from '@/lib/utils';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';

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

  const visibleEntries = useMemo(() => {
    const rows: Array<{ key: string; path: string; label: string; hidden?: boolean }> = [];
    if (data?.parent) {
      rows.push({ key: '__parent__', path: data.parent, label: '../' });
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle className="font-mono text-sm">Choose workspace</DialogTitle>
      </DialogHeader>
      <DialogContent>
        <div className="space-y-3 font-mono text-xs" onKeyDown={handleDialogKeyDown}>
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
              className="flex-1 bg-zinc-950 border border-zinc-700 px-2 py-1.5 text-zinc-300 outline-none"
              placeholder="/path/to/repo"
            />
            <button
              onClick={() => loadPath(pathInput, 'input')}
              className="px-2 py-1.5 text-zinc-300 hover:text-zinc-200 border border-zinc-700"
            >
              open
            </button>
          </div>

          {error && <p className="text-red-400">{error}</p>}

          <div className="border border-zinc-700 max-h-72 overflow-y-auto">
            {loading ? (
              <p className="px-3 py-2 text-zinc-400">Loading...</p>
            ) : (
              <>
                {visibleEntries.map((entry, index) => (
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
                    className={cn(
                      'block w-full text-left px-3 py-1.5 outline-none hover:text-zinc-200 hover:bg-zinc-800/50 focus:bg-zinc-800/60',
                      activeIndex === index && 'bg-zinc-800/60 text-zinc-200',
                      entry.hidden ? 'text-zinc-500' : 'text-zinc-300'
                    )}
                  >
                    {entry.label}
                  </button>
                ))}
              </>
            )}
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-zinc-400 truncate">{data?.path || pathInput}</span>
            <button
              onClick={chooseCurrent}
              disabled={!data?.path}
              className="text-emerald-500/80 hover:text-emerald-400 disabled:text-zinc-600"
            >
              [use this folder]
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
