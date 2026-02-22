/**
 * Final answer display with inline citation rendering.
 * Parses [N] patterns and replaces with CitationInline components.
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

export function AnswerWithCitations({
  content,
  citations,
  isStreaming = false,
}: AnswerWithCitationsProps) {
  // Build citation map for quick lookup
  const citationMap = useMemo(() => {
    const map = new Map<number, AgentCitation>();
    citations.forEach((c, i) => map.set(i + 1, c));
    return map;
  }, [citations]);

  // Parse content and replace [N] with citation components
  // MUST be before any early returns to follow Rules of Hooks
  const parts = useMemo(() => {
    if (!content || citations.length === 0) return [];

    const result: Array<{ type: 'text'; content: string } | { type: 'citation'; index: number }> = [];
    let lastIndex = 0;
    const regex = /\[(\d+)\]/g;
    let match;

    while ((match = regex.exec(content)) !== null) {
      // Add text before the citation
      if (match.index > lastIndex) {
        result.push({ type: 'text', content: content.slice(lastIndex, match.index) });
      }

      const citationIndex = parseInt(match[1], 10);
      if (citationMap.has(citationIndex)) {
        result.push({ type: 'citation', index: citationIndex });
      } else {
        // Citation not found, keep as text
        result.push({ type: 'text', content: match[0] });
      }

      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < content.length) {
      result.push({ type: 'text', content: content.slice(lastIndex) });
    }

    return result;
  }, [content, citationMap, citations.length]);

  // For streaming, show markdown with cursor
  if (isStreaming) {
    return (
      <div>
        <AnswerMarkdown content={content} />
        <span className="inline-block w-2 h-4 bg-zinc-400 animate-pulse ml-0.5" />
      </div>
    );
  }

  // If no citation references found in content, render plain markdown
  const hasCitationRefs = parts.some((p) => p.type === 'citation');
  if (!hasCitationRefs) {
    return (
      <div>
        <AnswerMarkdown content={content} />
        <CitationsList citations={citations} />
      </div>
    );
  }

  // Render with inline citations
  // Note: This renders text parts as markdown and citations inline
  return (
    <div className="answer-with-citations">
      {parts.map((part, i) => {
        if (part.type === 'text') {
          return <AnswerMarkdown key={i} content={part.content} />;
        } else {
          const citation = citationMap.get(part.index);
          if (citation) {
            return (
              <CitationInline key={i} index={part.index} citation={citation} />
            );
          }
          return null;
        }
      })}

      {/* Citation list at bottom */}
      <CitationsList citations={citations} />
    </div>
  );
}

/** Source list at the bottom of the answer */
function CitationsList({ citations }: { citations: AgentCitation[] }) {
  const [expanded, setExpanded] = useState(false);

  if (citations.length === 0) return null;

  const hasMore = citations.length > INITIAL_SOURCES_SHOWN;
  const visibleCitations = expanded ? citations : citations.slice(0, INITIAL_SOURCES_SHOWN);
  const hiddenCount = citations.length - INITIAL_SOURCES_SHOWN;

  return (
    <div className="mt-4 pt-4 border-t border-zinc-800">
      <div className="text-xs font-medium text-zinc-500 mb-2">Sources</div>
      <div className="space-y-1">
        {visibleCitations.map((citation, i) => {
          let hostname = '';
          try {
            hostname = new URL(citation.source_url).hostname;
          } catch {
            hostname = citation.source_url;
          }

          return (
            <a
              key={citation.id}
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-2 text-xs text-zinc-400 hover:text-zinc-200"
            >
              <span
                className="flex-shrink-0 text-zinc-400 bg-transparent text-[10px] font-mono"
              >
                [{i + 1}]
              </span>
              <span className="line-clamp-1">
                {citation.title || hostname}
              </span>
            </a>
          );
        })}
      </div>
      {hasMore && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="mt-2 text-xs text-zinc-400 hover:text-zinc-200 font-medium"
        >
          {expanded ? 'Show less' : `+${hiddenCount} more sources`}
        </button>
      )}
    </div>
  );
}
