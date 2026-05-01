import { useCallback, useEffect, useState } from 'react';

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

  const loadPath = useCallback((path?: string) => {
    setLoading(true);
    setError(null);
    browseWorkspaceDirectories(path || undefined)
      .then((next) => {
        setData(next);
        setPathInput(next.path);
      })
      .catch((err: { message?: string }) => setError(err.message || 'Failed to browse path'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!open) return;
    loadPath(value || undefined);
  }, [open, value, loadPath]);

  const chooseCurrent = () => {
    if (!data?.path) return;
    onSelect(data.path);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogHeader>
        <DialogTitle className="font-mono text-sm">Choose workspace</DialogTitle>
      </DialogHeader>
      <DialogContent>
        <div className="space-y-3 font-mono text-xs">
          <div className="flex gap-2">
            <input
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') loadPath(pathInput);
              }}
              className="flex-1 bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-zinc-300 outline-none"
              placeholder="/path/to/repo"
            />
            <button
              onClick={() => loadPath(pathInput)}
              className="px-2 py-1.5 text-zinc-400 hover:text-zinc-200 border border-zinc-800"
            >
              open
            </button>
          </div>

          {error && <p className="text-red-400">{error}</p>}

          <div className="border border-zinc-800 max-h-72 overflow-y-auto">
            {loading ? (
              <p className="px-3 py-2 text-zinc-600">Loading...</p>
            ) : (
              <>
                {data?.parent && (
                  <button
                    onClick={() => loadPath(data.parent!)}
                    className="block w-full text-left px-3 py-1.5 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800/50"
                  >
                    ../
                  </button>
                )}
                {data?.entries.map((entry) => (
                  <button
                    key={entry.path}
                    onClick={() => loadPath(entry.path)}
                    className={cn(
                      'block w-full text-left px-3 py-1.5 hover:text-zinc-200 hover:bg-zinc-800/50',
                      entry.hidden ? 'text-zinc-700' : 'text-zinc-400'
                    )}
                  >
                    {entry.name}/
                  </button>
                ))}
              </>
            )}
          </div>

          <div className="flex items-center justify-between gap-3">
            <span className="text-zinc-600 truncate">{data?.path || pathInput}</span>
            <button
              onClick={chooseCurrent}
              disabled={!data?.path}
              className="text-emerald-500/80 hover:text-emerald-400 disabled:text-zinc-700"
            >
              [use this folder]
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
