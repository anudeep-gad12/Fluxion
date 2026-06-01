import { useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import { ChevronDown, Globe2, Plus, Terminal, X } from 'lucide-react';

import { cn } from '@/lib/utils';

export type ToolTab =
  | {
      id: string;
      kind: 'terminal';
      label: string;
      active: boolean;
      canClose: boolean;
    }
  | {
      id: string;
      kind: 'browser';
      label: string;
      active: boolean;
      canClose: boolean;
    };

interface TerminalSessionRailProps {
  tabs: ToolTab[];
  terminalAtLimit: boolean;
  maxTerminals: number;
  onSelect: (tabId: string) => void;
  onNewTerminal: () => void;
  onNewBrowser: () => void;
  onClose: (tabId: string, kind: ToolTab['kind']) => void;
}

export function TerminalSessionRail({
  tabs,
  terminalAtLimit,
  maxTerminals,
  onSelect,
  onNewTerminal,
  onNewBrowser,
  onClose,
}: TerminalSessionRailProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [menuOpen]);

  const handleClose = (tab: ToolTab, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    onClose(tab.id, tab.kind);
  };

  return (
    <div className="desktop-terminal-tabs flex h-10 shrink-0 items-center gap-1 border-b border-white/[0.06] bg-[var(--desktop-bg-0)] px-2">
      <div className="min-w-0 flex-1 overflow-x-auto">
        <div className="flex min-w-max items-center gap-1">
          {tabs.map((tab) => {
            const Icon = tab.kind === 'browser' ? Globe2 : Terminal;
            return (
              <div
                key={tab.id}
                className={cn('desktop-terminal-tab', tab.active && 'is-active')}
              >
                <button
                  type="button"
                  onClick={() => onSelect(tab.id)}
                  className="desktop-terminal-tab-select desktop-no-drag"
                  title={tab.label}
                >
                  <Icon className="h-3 w-3 shrink-0 opacity-55" aria-hidden />
                  <span className="truncate">{tab.label}</span>
                </button>
                {tab.canClose ? (
                  <button
                    type="button"
                    onClick={(event) => handleClose(tab, event)}
                    className="desktop-terminal-tab-close desktop-no-drag"
                    aria-label={`Close ${tab.label}`}
                  >
                    <X className="h-3 w-3" strokeWidth={2} />
                  </button>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      <div ref={menuRef} className="relative shrink-0">
        <button
          type="button"
          onClick={() => setMenuOpen((value) => !value)}
          className="desktop-no-drag flex h-6 items-center justify-center gap-0.5 rounded-md px-1.5 text-zinc-500 transition-colors hover:bg-white/[0.06] hover:text-zinc-200"
          title="New panel tab"
          aria-label="New panel tab"
          aria-expanded={menuOpen}
        >
          <Plus className="h-3.5 w-3.5" />
          <ChevronDown className="h-3 w-3" />
        </button>
        {menuOpen ? (
          <div className="desktop-tool-add-menu absolute right-0 top-8 z-30 w-36 overflow-hidden rounded-lg border border-white/[0.08] bg-[#14161a] p-1 shadow-xl shadow-black/35">
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onNewTerminal();
              }}
              disabled={terminalAtLimit}
              className={cn(
                'desktop-no-drag flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-zinc-300',
                terminalAtLimit
                  ? 'cursor-not-allowed opacity-40'
                  : 'hover:bg-white/[0.06] hover:text-zinc-100'
              )}
              title={terminalAtLimit ? `Maximum ${maxTerminals} terminals` : 'New terminal'}
            >
              <Terminal className="h-3.5 w-3.5" />
              Terminal
            </button>
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                onNewBrowser();
              }}
              className="desktop-no-drag flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12px] text-zinc-300 hover:bg-white/[0.06] hover:text-zinc-100"
            >
              <Globe2 className="h-3.5 w-3.5" />
              Browser
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
