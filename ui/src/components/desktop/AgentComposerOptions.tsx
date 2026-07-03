
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

  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] tabular-nums text-zinc-500">
      <span>
        {composerContextUtilizationPct !== null
          ? `${Math.round(composerContextUtilizationPct)}% ctx`
          : '— ctx'}
      </span>
      <span className="text-zinc-700">·</span>
      <span>
        {typeof composerPromptTokens === 'number' && composerContextWindow
          ? `${formatContextTokens(composerPromptTokens)} / ${formatContextTokens(composerContextWindow)}`
          : '— tok'}
      </span>
      <span className="text-zinc-700">·</span>
      <span>
        raw in {formatContextTokens(conversationInputTokens)} / out {formatContextTokens(conversationOutputTokens)}
      </span>
      <span className="text-zinc-700">·</span>
      <span>
        cost in {conversationInputCost + conversationOutputCost > 0 ? formatCost(conversationInputCost) : 'n/a'}
        {' / '}
        out {conversationInputCost + conversationOutputCost > 0 ? formatCost(conversationOutputCost) : 'n/a'}
      </span>
    </div>
  );
}
