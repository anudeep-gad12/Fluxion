/**
 * Workspace @file mention picker for the composer.
 */

import { useEffect, useRef } from 'react';
import type { WorkspaceFileEntry } from '@/api/client';
import { cn } from '@/lib/utils';

export function extractActiveMention(value: string, cursor: number): { start: number; end: number; query: string } | null {
  const safeCursor = Math.max(0, Math.min(cursor, value.length));
  const beforeCursor = value.slice(0, safeCursor);
  const tokenStart = Math.max(
    beforeCursor.lastIndexOf(" "),
    beforeCursor.lastIndexOf("\n"),
    beforeCursor.lastIndexOf("\t"),
  ) + 1;
  const token = beforeCursor.slice(tokenStart);
  if (!token.startsWith("@")) return null;
  if (token.length > 1 && token.includes("@", 1)) return null;
  return {
    start: tokenStart,
    end: safeCursor,
    query: token.slice(1),
  };
}

export function MentionPicker({
  open,
  loading,
  error,
  entries,
  selectedIndex,
  onSelect,
  desktop,
}: {
  open: boolean;
  loading: boolean;
  error: string | null;
  entries: WorkspaceFileEntry[];
  selectedIndex: number;
  onSelect: (entry: WorkspaceFileEntry) => void;
  desktop?: boolean;
}) {
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    if (!open) return;
    const activeItem = itemRefs.current[selectedIndex];
    activeItem?.scrollIntoView({ block: 'nearest' });
  }, [open, selectedIndex, entries]);

  if (!open) return null;

  const statusMessage = loading
    ? 'Searching files…'
    : error
      ? error
      : entries.length === 0
        ? 'No matching files'
        : null;

  if (desktop) {
    return (
      <div
        className="desktop-mention-picker absolute left-0 right-0 bottom-full z-[var(--z-popover)] mb-2"
        role="listbox"
        aria-label="Workspace files"
      >
        {statusMessage ? (
          <p
            className={cn(
              'desktop-settings-hint px-2 py-2',
              error && 'desktop-settings-hint-error'
            )}
          >
            {statusMessage}
          </p>
        ) : (
          <div className="desktop-settings-list-panel desktop-mention-picker-list">
            {entries.map((entry, index) => (
              <button
                key={entry.path}
                type="button"
                role="option"
                aria-selected={index === selectedIndex}
                data-active={index === selectedIndex ? 'true' : undefined}
                ref={(node) => {
                  itemRefs.current[index] = node;
                }}
                onMouseDown={(e) => {
                  e.preventDefault();
                  onSelect(entry);
                }}
                className="desktop-settings-list-item font-mono"
              >
                <div className="desktop-settings-list-title truncate">{entry.path}</div>
                <div className="desktop-settings-list-meta truncate">{entry.name}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="ui-panel-strong ui-elevated absolute left-0 right-0 bottom-full z-[var(--z-popover)] mb-2 max-h-64 overflow-y-auto rounded-xl border border-[var(--desktop-border-strong)]">
      {loading ? (
        <div className="px-3 py-2 text-[11px] font-mono text-[var(--desktop-text-secondary)]">searching files...</div>
      ) : error ? (
        <div className="px-3 py-2 text-[11px] font-mono text-red-300">{error}</div>
      ) : entries.length === 0 ? (
        <div className="px-3 py-2 text-[11px] font-mono text-[var(--desktop-text-tertiary)]">no matching files</div>
      ) : (
        entries.map((entry, index) => (
          <button
            key={entry.path}
            type="button"
            ref={(node) => {
              itemRefs.current[index] = node;
            }}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(entry);
            }}
            className={cn(
              "ui-transition block w-full px-3 py-2.5 text-left font-mono text-[11px]",
              index === selectedIndex
                ? "bg-cyan-300/[0.08] text-[var(--desktop-text-primary)]"
                : "text-[var(--desktop-text-secondary)] hover:bg-[var(--desktop-hover)] hover:text-cyan-100"
            )}
          >
            <div className="truncate">{entry.path}</div>
            <div className="truncate text-[10px] text-[var(--desktop-text-tertiary)]">{entry.name}</div>
          </button>
        ))
      )}
    </div>
  );
}
