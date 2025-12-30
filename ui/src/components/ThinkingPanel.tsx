// ThinkingPanel - Collapsible panel showing AI thinking process

import { useState } from 'react';
import { ChevronDown, ChevronRight, Brain, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ThinkingStep } from '@/types';

interface ThinkingPanelProps {
  summary?: string;
  steps?: ThinkingStep[];
  isStreaming?: boolean;
  streamingContent?: string;
  defaultExpanded?: boolean;
}

export function ThinkingPanel({
  summary,
  steps = [],
  isStreaming = false,
  streamingContent = '',
  defaultExpanded = false,
}: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Don't render if no thinking content
  if (!summary && steps.length === 0 && !streamingContent && !isStreaming) {
    return null;
  }

  const hasContent = summary || steps.length > 0 || streamingContent;

  return (
    <div className="mb-3 rounded-lg border border-slate-200 bg-slate-50 overflow-hidden">
      {/* Header - always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full px-3 py-2 flex items-center gap-2 text-sm text-slate-600 hover:bg-slate-100 transition-colors',
          expanded && 'border-b border-slate-200'
        )}
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronRight className="h-4 w-4 text-slate-400" />
        )}

        <Brain className="h-4 w-4 text-indigo-500" />

        <span className="font-medium">Thinking</span>

        {isStreaming && (
          <Loader2 className="h-3 w-3 animate-spin text-indigo-500" />
        )}

        {steps.length > 0 && (
          <span className="text-xs text-slate-400">
            ({steps.length} step{steps.length !== 1 ? 's' : ''})
          </span>
        )}

        {!expanded && hasContent && (
          <span className="ml-auto text-xs text-slate-400 truncate max-w-[200px]">
            {summary?.split('\n')[0] || streamingContent?.slice(0, 50) || 'Click to expand'}
          </span>
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="px-3 py-3 space-y-3 max-h-[300px] overflow-y-auto">
          {/* Streaming content (live) */}
          {streamingContent && (
            <div className="text-sm text-slate-600 whitespace-pre-wrap font-mono text-xs leading-relaxed">
              {streamingContent}
              {isStreaming && (
                <span className="inline-block w-2 h-3 bg-indigo-400 animate-pulse ml-0.5" />
              )}
            </div>
          )}

          {/* Completed steps */}
          {steps.length > 0 && (
            <div className="space-y-2">
              {steps.map((step) => (
                <div key={step.seq} className="text-xs">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn(
                      'px-1.5 py-0.5 rounded text-[10px] font-medium uppercase',
                      step.status === 'done'
                        ? 'bg-emerald-100 text-emerald-700'
                        : step.status === 'thinking'
                          ? 'bg-indigo-100 text-indigo-700'
                          : 'bg-slate-100 text-slate-600'
                    )}>
                      {step.step_type}
                    </span>
                    <span className="text-slate-400">Step {step.seq}</span>
                  </div>
                  <div className="text-slate-600 whitespace-pre-wrap pl-2 border-l-2 border-slate-200">
                    {step.summary}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Summary (if no steps) */}
          {!streamingContent && steps.length === 0 && summary && (
            <div className="text-sm text-slate-600 whitespace-pre-wrap">
              {summary}
            </div>
          )}

          {/* Empty state */}
          {!hasContent && isStreaming && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Thinking...
            </div>
          )}
        </div>
      )}
    </div>
  );
}
