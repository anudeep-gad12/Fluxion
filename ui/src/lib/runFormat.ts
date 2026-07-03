/**
 * Shared formatting helpers for run transcript rendering.
 */

import { formatAgentCost, formatAgentTokens } from '@/lib/agentLiveState';
import { normalizeTokenUsage } from '@/lib/usageMetrics';
import type { Run } from '@/types';

export function formatRunStatusLabel(run: Run): string {
  if (run.status === 'succeeded') return 'done';
  if (run.status === 'failed') return 'failed';
  if (run.status === 'cancelled') return 'stopped';
  if (run.status === 'interrupted') return 'interrupted';
  return 'running';
}

export function getRunFooterMetrics(run: Run): string[] {
  const metrics: string[] = [];
  const usage = normalizeTokenUsage(run.usage);

  if (usage?.total_tokens) {
    metrics.push(`${formatAgentTokens(usage.total_tokens)} tok`);
  }
  if (usage) {
    metrics.push(
      `in ${formatAgentTokens(usage.input_tokens)} / out ${formatAgentTokens(usage.output_tokens)}`
    );
  }
  if (run.cost && typeof run.cost.total_cost === 'number') {
    metrics.push(`est ${formatAgentCost(run.cost.total_cost)}`);
  }
  if (typeof run.context_usage?.utilization_pct_effective === 'number') {
    metrics.push(`ctx ${Math.round(run.context_usage.utilization_pct_effective)}%`);
  }
  if (run.mode === 'chat') {
    metrics.push('chat');
  }

  return metrics;
}

export function formatContextTokens(tokens: number): string {
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens >= 10_000_000 ? 0 : 1)}m`;
  if (tokens >= 1_000) return `${(tokens / 1_000).toFixed(tokens >= 10_000 ? 0 : 1)}k`;
  return tokens.toLocaleString();
}
