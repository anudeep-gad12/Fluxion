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
              <pre className="my-3 overflow-x-auto rounded-xl border border-zinc-800/95 bg-zinc-950/92 px-3 py-2.5 text-xs text-zinc-200">
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
  const stepSummaries = useMemo(
    () =>
      steps
        .map((step) => ({ seq: step.seq, text: stripThinkTags(step.summary || '').trim() }))
        .filter((step) => step.text),
    [steps],
  );

  if (!cleanSummary && stepSummaries.length === 0 && !cleanStreamingContent && !isStreaming) {
    return null;
  }

  const hasContent = !!cleanSummary || stepSummaries.length > 0 || !!cleanStreamingContent;

  return (
    <div className="tr-item mb-4">
      <button
        type="button"
        className="tr-thinking-toggle"
        onClick={() => setExpanded((value) => !value)}
        data-expanded={expanded}
      >
        <span className="tr-marker" data-tone={isStreaming ? 'running' : 'pending'} aria-hidden>
          ⏺
        </span>
        <span className="tr-thinking-label">Thinking…</span>
      </button>

      {expanded && (
        <div className={cn('tr-thinking-content max-h-[26rem] overflow-y-auto', !hasContent && 'italic')}>
          {cleanStreamingContent ? (
            <>
              <ThinkingMarkdown content={cleanStreamingContent} />
              {isStreaming && (
                <span className="agent-caret ml-1" />
              )}
            </>
          ) : (
            <div className="space-y-3">
              {cleanSummary && <ThinkingMarkdown content={cleanSummary} />}
              {stepSummaries.map((step) => (
                <ThinkingMarkdown key={step.seq} content={step.text} />
              ))}
            </div>
          )}

          {!hasContent && isStreaming && <span>Thinking…</span>}
        </div>
      )}
    </div>
  );
}
