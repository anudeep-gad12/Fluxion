import type { CostUsage, TokenUsage } from '@/types/agent';

type RawUsage = Partial<TokenUsage> & {
  prompt_tokens?: number;
  completion_tokens?: number;
  thinking_tokens?: number;
};

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

export function normalizeTokenUsage(usage?: RawUsage | null): TokenUsage | null {
  if (!usage) return null;

  const inputTokens = asNumber(usage.input_tokens) ?? asNumber(usage.prompt_tokens) ?? 0;
  const outputTokens = asNumber(usage.output_tokens) ?? asNumber(usage.completion_tokens) ?? 0;
  const reasoningTokens = asNumber(usage.reasoning_tokens) ?? asNumber(usage.thinking_tokens) ?? 0;
  const cachedTokens = asNumber(usage.cached_tokens) ?? 0;
  const totalTokens = asNumber(usage.total_tokens) ?? inputTokens + outputTokens;

  if (
    inputTokens === 0
    && outputTokens === 0
    && reasoningTokens === 0
    && cachedTokens === 0
    && totalTokens === 0
  ) {
    return null;
  }

  return {
    input_tokens: inputTokens,
    output_tokens: outputTokens,
    reasoning_tokens: reasoningTokens,
    cached_tokens: cachedTokens,
    total_tokens: totalTokens,
  };
}

export function inputCostTotal(cost?: CostUsage | null): number {
  if (!cost) return 0;
  return (cost.input_cost ?? 0) + (cost.cached_input_cost ?? 0);
}

export function outputCostTotal(cost?: CostUsage | null): number {
  return cost?.output_cost ?? 0;
}
