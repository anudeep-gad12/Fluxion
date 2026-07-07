/**
 * Final answer display with inline citation rendering.
 */

import { useMemo, useState } from 'react';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import { CitationInline } from '@/components/CitationInline';
import type { AgentCitation } from '@/types/agent';

const INITIAL_SOURCES_SHOWN = 3;

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
          <span className="agent-caret ml-0.5" />
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
    <section className="desktop-sources">
      <div className="desktop-sources-header">
        <div className="desktop-sources-label">
          sources
          <span>{citations.length} reference{citations.length !== 1 ? 's' : ''}</span>
        </div>
        {hasMore && (
          <button
            onClick={() => setExpanded((value) => !value)}
            className="desktop-sources-toggle"
            type="button"
          >
            {expanded ? 'show less' : `show ${hiddenCount} more`}
          </button>
        )}
      </div>

      <div className="desktop-sources-list">
        {visibleCitations.map((citation, index) => {
          const host = getSourceHost(citation.source_url);
          const snippet = summarizeSnippet(citation.snippet);
          return (
            <a
              key={citation.id}
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="desktop-source-row"
            >
              <div className="desktop-source-index">
                {index + 1}
              </div>
              <div className="min-w-0 flex-1">
                <div className="desktop-source-main">
                  <span className="desktop-source-title">
                    {citation.title || host}
                  </span>
                  <span className="desktop-source-host">
                    {host}
                  </span>
                </div>
                {snippet && (
                  <p className="desktop-source-snippet">
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
