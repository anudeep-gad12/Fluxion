// ThinkingPanel - Collapsible panel showing AI thinking process

import { useMemo, useState } from 'react';
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

const stripThinkTags = sanitizeThinking;

function fixLatexIssues(content: string): string {
  let result = content;
  result = result.replace(/\\\\\s*\\end\{/g, '\\end{');
  result = result.replace(/\\\\\s*\n\s*\\end\{/g, '\n\\end{');
  return result;
}

function normalizeMathDelimiters(content: string): string {
  let result = content;

  const toBlockMath = (math: string) => {
    const fixedMath = fixLatexIssues(math.trim());
    return `\n$$\n${fixedMath}\n$$\n`;
  };

  const toInlineMath = (math: string) => `$${math.trim()}$`;

  result = result.replace(/\$\$([\s\S]*?)\$\$/g, (_, math) => toBlockMath(math));
  result = result.replace(/\\\\\[((?:.|\n)*?)\\\\\]/g, (_, math) => toBlockMath(math));
  result = result.replace(/\\\\\(((?:.|\n)*?)\\\\\)/g, (_, math) => toInlineMath(math));
  result = result.replace(/\\\[([\s\S]*?)\\\]/g, (_, math) => toBlockMath(math));
  result = result.replace(/\\\(([\s\S]*?)\\\)/g, (_, math) => toInlineMath(math));

  return result;
}

function ThinkingMarkdown({ content }: { content: string }) {
  const cleanContent = stripThinkTags(content);
  const normalizedContent = normalizeMathDelimiters(cleanContent);

  return (
    <div className="thinking-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          code({ className, children, ...props }) {
            const isInline = !className;
            if (isInline) {
              return (
                <code className="rounded-md border border-zinc-800/90 bg-zinc-950/90 px-1.5 py-0.5 text-[11px] text-zinc-200" {...props}>
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
              <pre className="my-3 overflow-x-auto rounded-xl border border-zinc-800/95 bg-zinc-950/92 px-3 py-2.5 text-[12px] text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
                {children}
              </pre>
            );
          },
          p({ children }) {
            return <p className="mb-2.5 last:mb-0">{children}</p>;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

function excerpt(content: string): string {
  const firstLine = content
    .split('\n')
    .map((line) => line.trim())
    .find(Boolean) || '';
  return firstLine.length > 92 ? `${firstLine.slice(0, 89)}...` : firstLine;
}

export function ThinkingPanel({
  summary,
  steps = [],
  isStreaming = false,
  streamingContent = '',
  defaultExpanded = false,
}: ThinkingPanelProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const cleanStreamingContent = stripThinkTags(streamingContent).trim();
  const cleanSummary = stripThinkTags(summary || '').trim();
  const displaySummary = useMemo(() => {
    if (cleanStreamingContent) return excerpt(cleanStreamingContent);
    if (cleanSummary) return excerpt(cleanSummary);
    for (const step of steps) {
      const next = stripThinkTags(step.summary || '').trim();
      if (next) return excerpt(next);
    }
    return '';
  }, [cleanStreamingContent, cleanSummary, steps]);

  if (!cleanSummary && steps.length === 0 && !cleanStreamingContent && !isStreaming) {
    return null;
  }

  const hasContent = cleanSummary || steps.length > 0 || cleanStreamingContent;

  return (
    <div className="mb-5 rounded-[1.25rem] border border-zinc-800/85 bg-zinc-950/48 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className={cn(
          'ui-transition flex w-full items-start gap-3 px-4 py-3.5 text-left',
          expanded ? 'border-b border-zinc-800/75' : 'hover:bg-zinc-900/28'
        )}
      >
        <span className="mt-0.5 text-zinc-500">{expanded ? '▾' : '▸'}</span>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-zinc-800/90 bg-zinc-950/80 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-zinc-300">
              thinking
            </span>
            {isStreaming && (
              <span className="rounded-full border border-cyan-500/25 bg-cyan-500/[0.10] px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-cyan-200">
                live
              </span>
            )}
          </div>
          {displaySummary ? (
            <p className="truncate text-[12px] leading-6 text-zinc-400">{displaySummary}</p>
          ) : isStreaming ? (
            <p className="text-[12px] leading-6 text-zinc-500">Thinking in progress...</p>
          ) : null}
        </div>
      </button>

      <div className="collapsible-content" data-expanded={expanded}>
        <div>
          <div className="max-h-[26rem] space-y-4 overflow-y-auto px-4 py-4">
            {cleanStreamingContent && (
              <section className="space-y-2">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.18em] text-cyan-200/85">
                  <span className="h-1.5 w-1.5 rounded-full bg-cyan-400" />
                  Live reasoning
                </div>
                <div className="rounded-[1rem] border border-cyan-500/16 bg-cyan-500/[0.06] px-3.5 py-3">
                  <ThinkingMarkdown content={cleanStreamingContent} />
                  {isStreaming && (
                    <span className="agent-caret ml-1 inline-block h-3.5 w-1.5 translate-y-0.5 bg-cyan-400/75" />
                  )}
                </div>
              </section>
            )}

            {!cleanStreamingContent && cleanSummary && (
              <section className="space-y-2">
                <div className="premium-section-label">summary</div>
                <div className="rounded-[1rem] border border-zinc-800/85 bg-zinc-950/78 px-3.5 py-3">
                  <ThinkingMarkdown content={cleanSummary} />
                </div>
              </section>
            )}

            {steps.length > 0 && (
              <section className="space-y-3">
                <div className="premium-section-label">timeline</div>
                <div className="space-y-3">
                  {steps.map((step) => {
                    const stepSummary = stripThinkTags(step.summary || '').trim();
                    return (
                      <div
                        key={step.seq}
                        className="rounded-[1rem] border border-zinc-800/85 bg-zinc-950/62 px-3.5 py-3"
                      >
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <span
                            className={cn(
                              'rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em]',
                              step.status === 'done'
                                ? 'bg-zinc-900 text-zinc-300'
                                : step.status === 'thinking'
                                  ? 'bg-cyan-500/[0.10] text-cyan-200'
                                  : 'bg-zinc-900 text-zinc-500'
                            )}
                          >
                            {step.step_type}
                          </span>
                        </div>
                        {stepSummary ? (
                          <ThinkingMarkdown content={stepSummary} />
                        ) : (
                          <p className="text-[12px] text-zinc-500">No summary captured.</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            )}

            {!hasContent && isStreaming && (
              <div className="text-[12px] font-mono text-zinc-500">Thinking...</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
