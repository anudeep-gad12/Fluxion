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
        className="inline-flex items-center justify-center w-5 h-5 text-xs font-medium
                   bg-indigo-100 text-indigo-700 rounded-full hover:bg-indigo-200
                   transition-colors cursor-pointer align-super"
        title={citation.title || citation.source_url}
      >
        {index}
      </button>

      {showTooltip && (
        <div
          className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2
                        w-64 p-3 bg-white border border-slate-200 rounded-lg shadow-lg"
        >
          {citation.title && (
            <div className="font-medium text-sm text-slate-900 mb-1 line-clamp-2">
              {citation.title}
            </div>
          )}
          <div className="text-xs text-slate-600 line-clamp-3 mb-2">
            {citation.snippet}
          </div>
          <div className="text-xs text-indigo-600 truncate">{hostname}</div>
          <div
            className="absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2
                          w-2 h-2 bg-white border-r border-b border-slate-200
                          rotate-45"
          />
        </div>
      )}
    </span>
  );
}
