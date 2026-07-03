import { Fragment } from 'react';

interface AgentContextFooterProps {
  show: boolean;
  composerContextUtilizationPct: number | null;
  composerPromptTokens: number | null;
  composerContextWindow: number | null;
  conversationInputTokens: number;
  conversationOutputTokens: number;
  conversationInputCost: number;
  conversationOutputCost: number;
  formatContextTokens: (value: number) => string;
  formatCost: (value: number) => string;
}

export function AgentContextFooter({
  show,
  composerContextUtilizationPct,
  composerPromptTokens,
  composerContextWindow,
  conversationInputTokens,
  conversationOutputTokens,
  conversationInputCost,
  conversationOutputCost,
  formatContextTokens,
  formatCost,
}: AgentContextFooterProps) {
  if (!show) {
    return null;
  }

  // Only metrics with real values render — an idle composer shows nothing
  // instead of a row of placeholders.
  const segments: string[] = [];
  if (composerContextUtilizationPct !== null) {
    segments.push(`${Math.round(composerContextUtilizationPct)}% ctx`);
  }
  if (typeof composerPromptTokens === 'number' && composerContextWindow) {
    segments.push(
      `${formatContextTokens(composerPromptTokens)} / ${formatContextTokens(composerContextWindow)} tok`
    );
  }
  if (conversationInputTokens > 0 || conversationOutputTokens > 0) {
    segments.push(
      `raw in ${formatContextTokens(conversationInputTokens)} / out ${formatContextTokens(conversationOutputTokens)}`
    );
  }
  if (conversationInputCost + conversationOutputCost > 0) {
    segments.push(
      `cost in ${formatCost(conversationInputCost)} / out ${formatCost(conversationOutputCost)}`
    );
  }

  if (segments.length === 0) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] tabular-nums text-zinc-500">
      {segments.map((segment, index) => (
        <Fragment key={segment}>
          {index > 0 && <span className="text-zinc-700">·</span>}
          <span>{segment}</span>
        </Fragment>
      ))}
    </div>
  );
}
