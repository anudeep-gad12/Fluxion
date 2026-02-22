/**
 * Inline citation reference with tooltip.
 * Displays as a clickable [N] badge that opens the source URL.
 */

import { useState } from 'react';
import type { AgentCitation } from '@/types/agent';

interface CitationInlineProps {
  index: number; // 1-based citation number
  citation: AgentCitation;
}

export function CitationInline({ index, citation }: CitationInlineProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  const handleClick = () => {
    window.open(citation.source_url, '_blank', 'noopener,noreferrer');
  };

  // Extract hostname safely
  let hostname = '';
  try {
    hostname = new URL(citation.source_url).hostname;
  } catch {
    hostname = citation.source_url;
  }

  return (
    <span className="relative inline-block">
      <button
        onClick={handleClick}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className="inline-flex items-center justify-center text-xs font-medium font-mono
                   bg-transparent text-zinc-400 rounded-none hover:text-zinc-200 underline
                   transition-colors cursor-pointer align-super"
        title={citation.title || citation.source_url}
      >
        [{index}]
      </button>

      {showTooltip && (
        <div
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2
                        w-64 p-3 bg-zinc-900 border border-zinc-700 rounded-none shadow-none"
        >
          {citation.title && (
            <div className="font-medium text-sm text-zinc-200 mb-1 line-clamp-2">
              {citation.title}
            </div>
          )}
          <div className="text-xs text-zinc-400 line-clamp-3 mb-2">
            {citation.snippet}
          </div>
          <div className="text-xs text-zinc-300 truncate">{hostname}</div>
          <div
            className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2
                          w-2 h-2 bg-zinc-900 border-r border-b border-zinc-700
                          rotate-45"
          />
        </div>
      )}
    </span>
  );
}
