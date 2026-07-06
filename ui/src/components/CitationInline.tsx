/**
 * Inline citation reference with tooltip.
 */

import { useMemo, useState } from 'react';
import type { AgentCitation } from '@/types/agent';

interface CitationInlineProps {
  index: number;
  citation: AgentCitation;
}

function getHostname(sourceUrl: string): string {
  try {
    return new URL(sourceUrl).hostname.replace(/^www\./, '');
  } catch {
    return sourceUrl;
  }
}

export function CitationInline({ index, citation }: CitationInlineProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const hostname = useMemo(() => getHostname(citation.source_url), [citation.source_url]);

  return (
    <span className="relative inline-flex align-super">
      <button
        onClick={() => window.open(citation.source_url, '_blank', 'noopener,noreferrer')}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="ui-transition inline-flex h-5 min-w-5 items-center justify-center rounded-full border border-cyan-500/18 bg-transparent px-1.5 font-mono text-[10px] text-cyan-200 hover:border-cyan-400/28 hover:bg-[var(--desktop-accent-hover)] hover:text-cyan-100"
        aria-label={citation.title || citation.source_url}
      >
        {index}
      </button>

      {showTooltip && (
        <div className="ui-elevated absolute bottom-full left-1/2 z-50 mb-3 w-72 -translate-x-1/2 overflow-hidden rounded-xl border border-zinc-800/90 bg-[var(--desktop-panel-overlay)] p-3 text-left shadow-[var(--shadow-menu)]">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.16em] text-[var(--desktop-text-tertiary)]">
              <span className="rounded-full border border-zinc-800/90 bg-[var(--desktop-bg-3)] px-2 py-0.5 text-[var(--desktop-text-secondary)]">
                source {index}
              </span>
              <span className="truncate">{hostname}</span>
            </div>
            {citation.title && (
              <div className="line-clamp-2 text-sm font-medium leading-6 text-[var(--desktop-text-primary)]">
                {citation.title}
              </div>
            )}
            {citation.snippet && (
              <div className="line-clamp-4 text-xs leading-5 text-[var(--desktop-text-secondary)]">
                {citation.snippet}
              </div>
            )}
          </div>
          <div className="absolute bottom-0 left-1/2 h-3 w-3 -translate-x-1/2 translate-y-1/2 rotate-45 border-b border-r border-zinc-800/90 bg-[var(--desktop-panel-overlay)]" />
        </div>
      )}
    </span>
  );
}
