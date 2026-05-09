/**
 * Final answer display with inline citation rendering.
 */

import { useMemo, useState } from 'react';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import { CitationInline } from '@/components/CitationInline';
import type { AgentCitation } from '@/types/agent';

const INITIAL_SOURCES_SHOWN = 4;

interface AnswerWithCitationsProps {
  content: string;
  citations: AgentCitation[];
  isStreaming?: boolean;
}

function getSourceHost(sourceUrl: string): string {
  try {
    return new URL(sourceUrl).hostname.replace(/^www\./, '');
  } catch {
    return sourceUrl;
  }
}

function summarizeSnippet(snippet?: string | null): string | null {
  const clean = (snippet || '').trim();
  if (!clean) return null;
  return clean.length > 180 ? `${clean.slice(0, 177)}...` : clean;
}

export function AnswerWithCitations({
  content,
  citations,
  isStreaming = false,
}: AnswerWithCitationsProps) {
  const citationMap = useMemo(() => {
    const map = new Map<number, AgentCitation>();
    citations.forEach((c, i) => map.set(i + 1, c));
    return map;
  }, [citations]);

  const parts = useMemo(() => {
    if (!content || citations.length === 0) return [];

    const result: Array<{ type: 'text'; content: string } | { type: 'citation'; index: number }> = [];
    let lastIndex = 0;
    const regex = /\[(\d+)\]/g;
    let match;

    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        result.push({ type: 'text', content: content.slice(lastIndex, match.index) });
      }

      const citationIndex = parseInt(match[1], 10);
      if (citationMap.has(citationIndex)) {
        result.push({ type: 'citation', index: citationIndex });
      } else {
        result.push({ type: 'text', content: match[0] });
      }

      lastIndex = match.index + match[0].length;
    }

    if (lastIndex < content.length) {
      result.push({ type: 'text', content: content.slice(lastIndex) });
    }

    return result;
  }, [content, citationMap, citations.length]);

  if (isStreaming) {
    return (
      <div className="space-y-5">
        <div>
          <AnswerMarkdown content={content} />
          <span className="inline-block h-4 w-2 animate-pulse bg-zinc-400 align-[-0.2em] ml-0.5" />
        </div>
        <CitationsList citations={citations} />
      </div>
    );
  }

  const hasCitationRefs = parts.some((p) => p.type === 'citation');
  if (!hasCitationRefs) {
    return (
      <div className="space-y-5">
        <AnswerMarkdown content={content} />
        <CitationsList citations={citations} />
      </div>
    );
  }

  return (
    <div className="answer-with-citations space-y-5">
      <div>
        {parts.map((part, i) => {
          if (part.type === 'text') {
            return <AnswerMarkdown key={i} content={part.content} />;
          }
          const citation = citationMap.get(part.index);
          return citation ? <CitationInline key={i} index={part.index} citation={citation} /> : null;
        })}
      </div>
      <CitationsList citations={citations} />
    </div>
  );
}

function CitationsList({ citations }: { citations: AgentCitation[] }) {
  const [expanded, setExpanded] = useState(false);

  if (citations.length === 0) return null;

  const hasMore = citations.length > INITIAL_SOURCES_SHOWN;
  const visibleCitations = expanded ? citations : citations.slice(0, INITIAL_SOURCES_SHOWN);
  const hiddenCount = Math.max(0, citations.length - INITIAL_SOURCES_SHOWN);

  return (
    <section className="rounded-[1.3rem] border border-zinc-800/85 bg-zinc-950/42 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="premium-section-label">sources</div>
          <p className="mt-1 text-[12px] leading-5 text-zinc-500">
            {citations.length} reference{citations.length !== 1 ? 's' : ''}
          </p>
        </div>
        {hasMore && (
          <button
            onClick={() => setExpanded((value) => !value)}
            className="premium-subtle-button px-3 py-1"
            type="button"
          >
            {expanded ? 'show less' : `show ${hiddenCount} more`}
          </button>
        )}
      </div>

      <div className="space-y-2">
        {visibleCitations.map((citation, index) => {
          const host = getSourceHost(citation.source_url);
          const snippet = summarizeSnippet(citation.snippet);
          return (
            <a
              key={citation.id}
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ui-transition group flex gap-3 rounded-[1rem] border border-zinc-800/80 bg-zinc-950/72 px-3.5 py-3 hover:border-cyan-500/24 hover:bg-cyan-500/[0.04]"
            >
              <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border border-zinc-800/85 bg-zinc-900/85 font-mono text-[10px] text-zinc-300 group-hover:border-cyan-500/25 group-hover:text-cyan-100">
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="line-clamp-1 text-[13px] font-medium leading-5 text-zinc-100">
                    {citation.title || host}
                  </span>
                  <span className="text-[11px] uppercase tracking-[0.18em] text-zinc-500">
                    {host}
                  </span>
                </div>
                {snippet && (
                  <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-zinc-400">
                    {snippet}
                  </p>
                )}
              </div>
            </a>
          );
        })}
      </div>
    </section>
  );
}
