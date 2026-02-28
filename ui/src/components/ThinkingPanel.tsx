// ThinkingPanel - Collapsible panel showing AI thinking process

import { useState } from 'react';
import { cn, sanitizeThinking } from '@/lib/utils';
import type { ThinkingStep } from '@/types';

import 'katex/dist/katex.min.css';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

interface ThinkingPanelProps {
  summary?: string;
  steps?: ThinkingStep[];
  isStreaming?: boolean;
  streamingContent?: string;
  defaultExpanded?: boolean;
}

/** Alias for backward compat within this file */
const stripThinkTags = sanitizeThinking;

/**
 * Fix common LaTeX issues that cause KaTeX parsing errors.
 */
function fixLatexIssues(content: string): string {
  let result = content;
  result = result.replace(/\\\\\s*\\end\{/g, '\\end{');
  result = result.replace(/\\\\\s*\n\s*\\end\{/g, '\n\\end{');
  return result;
}

/**
 * Normalize various LaTeX math delimiter formats to standard $$ and $ delimiters.
 */
function normalizeMathDelimiters(content: string): string {
  let result = content;

  const toBlockMath = (math: string) => {
    const fixedMath = fixLatexIssues(math.trim());
    return `\n$$\n${fixedMath}\n$$\n`;
  };

  const toInlineMath = (math: string) => `$${math.trim()}$`;

  // Normalize $$ ... $$ to fenced block math with line breaks
  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => toBlockMath(math));

  // Handle JSON-escaped delimiters (\\[ ... \\] and \\( ... \\))
  result = result.replace(/\\\\\[((?:.|\n)*?)\\\\\]/g, (_, math) => toBlockMath(math));
  result = result.replace(/\\\\\(((?:.|\n)*?)\\\\\)/g, (_, math) => toInlineMath(math));

  // Convert \[ ... \] to $$ ... $$ (display math)
  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => toBlockMath(math));

  // Convert \( ... \) to $ ... $ (inline math)
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => toInlineMath(math));

  return result;
}

/**
 * Render thinking content with markdown and LaTeX support.
 */
function ThinkingMarkdown({ content }: { content: string }) {
  const cleanContent = stripThinkTags(content);
  const normalizedContent = normalizeMathDelimiters(cleanContent);

  return (
    <div className="thinking-markdown text-sm text-zinc-500">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="rounded-none bg-zinc-800 px-1 py-0.5 text-xs text-zinc-300" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return (
              <pre className="my-2 overflow-x-auto rounded-none bg-zinc-900 p-2 text-xs text-zinc-300 border border-zinc-800">
                {children}
              </pre>
            );
          },
          p({ children }) {
            return <p className="mb-2 last:mb-0">{children}</p>;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

export function ThinkingPanel({
  summary,
  steps = [],
  isStreaming = false,
  streamingContent = '',
  defaultExpanded = false,
}: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  // Clean content for display
  const cleanStreamingContent = stripThinkTags(streamingContent);
  const cleanSummary = stripThinkTags(summary || '');

  // Don't render if no thinking content
  if (!cleanSummary && steps.length === 0 && !cleanStreamingContent && !isStreaming) {
    return null;
  }

  const hasContent = cleanSummary || steps.length > 0 || cleanStreamingContent;

  return (
    <div className="mb-3 rounded-none border border-zinc-800 bg-zinc-900 overflow-hidden">
      {/* Header - always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-full px-3 py-2 flex items-center gap-2 text-xs font-mono text-zinc-400 hover:bg-zinc-800',
          expanded && 'border-b border-zinc-800'
        )}
      >
        <span className="text-zinc-600 select-none">{expanded ? '▼' : '▶'}</span>

        <span className="font-medium">[thinking]</span>

        {isStreaming && (
          <span className="text-zinc-500">[streaming...]</span>
        )}

        {steps.length > 0 && (
          <span className="text-zinc-600">
            ({steps.length} step{steps.length !== 1 ? 's' : ''})
          </span>
        )}

        {!expanded && hasContent && (
          <span className="ml-auto text-zinc-600 truncate max-w-[200px]">
            {cleanSummary?.split('\n')[0] || cleanStreamingContent?.slice(0, 50) || ''}
          </span>
        )}
      </button>

      {/* Animated collapsible content */}
      <div className="collapsible-content" data-expanded={expanded}>
        <div>
          <div className="px-3 py-3 space-y-3 max-h-[300px] overflow-y-auto">
            {/* Streaming content (live) */}
            {cleanStreamingContent && (
              <div>
                <ThinkingMarkdown content={cleanStreamingContent} />
                {isStreaming && (
                  <span className="inline-block w-2 h-3 bg-zinc-400 animate-pulse ml-0.5" />
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
                        'text-[10px] font-medium uppercase font-mono',
                        step.status === 'done'
                          ? 'text-zinc-400'
                          : step.status === 'thinking'
                            ? 'text-zinc-500'
                            : 'text-zinc-600'
                      )}>
                        {step.step_type}
                      </span>
                      <span className="text-zinc-600">Step {step.seq}</span>
                    </div>
                    <div className="text-zinc-600 pl-2 border-l-2 border-zinc-800">
                      <ThinkingMarkdown content={step.summary} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Summary (if no steps) */}
            {!cleanStreamingContent && steps.length === 0 && cleanSummary && (
              <ThinkingMarkdown content={cleanSummary} />
            )}

            {/* Empty state */}
            {!hasContent && isStreaming && (
              <div className="text-xs text-zinc-500 font-mono">
                [thinking...]
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
