/**
 * Hook to load agent run details for both streaming and historical runs.
 * During streaming: uses Zustand store (in-memory)
 * After completion/refresh: fetches from API and transforms to AgentUIState
 */

import { useEffect, useState } from 'react';
import { getAgentRunTrace } from '@/api/client';
import type { AgentUIState, AgentStep, AgentToolCall, AgentCitation } from '@/types/agent';
import { useAgentRunState } from './useStore';

/**
 * Get agent run state, either from streaming state or loaded from API.
 *
 * @param runId - The agent run ID
 * @param isStreaming - Whether the run is currently streaming
 * @returns AgentUIState or undefined if not available yet
 */
export function useAgentRunDetails(
  runId: string,
  isStreaming: boolean
): AgentUIState | undefined {
  const streamingState = useAgentRunState(runId);
  const [historicalState, setHistoricalState] = useState<AgentUIState | undefined>();

  useEffect(() => {
    // If streaming or already have streaming state, don't load from API
    if (isStreaming || streamingState) {
      return;
    }

    // Load from API for completed runs
    let cancelled = false;

    getAgentRunTrace(runId)
      .then((trace) => {
        if (cancelled) return;

        // Transform API response to AgentUIState format
        const steps: AgentStep[] = trace.steps.map((s) => ({
          id: s.id,
          run_id: s.run_id,
          step_number: s.step_number,
          state: s.state,
          thinking_text: s.thinking_text,
          decision: s.decision,
          created_at: s.created_at,
          completed_at: s.completed_at,
          error_message: s.error_message,
        }));

        const toolCalls: AgentToolCall[] = trace.tool_calls.map((tc) => ({
          id: tc.id,
          run_id: tc.run_id,
          step_id: tc.step_id,
          tool_name: tc.tool_name,
          arguments: tc.arguments,
          status: tc.status,
          result_summary: tc.result_summary,
          error_message: tc.error_message,
          duration_ms: tc.duration_ms,
          created_at: tc.created_at,
          started_at: tc.started_at,
          completed_at: tc.completed_at,
          idempotency_key: tc.idempotency_key,
          execution_attempt: tc.execution_attempt,
        }));

        const citations: AgentCitation[] = trace.citations.map((c) => ({
          id: c.id,
          run_id: c.run_id,
          tool_call_id: c.tool_call_id,
          source_url: c.source_url,
          title: c.title,
          snippet: c.snippet,
          used_in_answer: c.used_in_answer,
          created_at: c.created_at,
        }));

        setHistoricalState({
          isActive: false,
          currentStep: steps.length,
          maxSteps: 10, // Default, could be stored in run metadata
          agentState: trace.status === 'succeeded' ? 'complete' : trace.status,
          thinkingBuffer: '',
          answerBuffer: trace.final_answer || '',
          steps,
          toolCalls,
          citations,
          injectedSteers: [],
          lastSeq: 0,
          total_tokens: trace.usage?.total_tokens,
          usage: trace.usage,
          cost: trace.cost,
          context_usage: trace.context_usage,
        });
      })
      .catch((error) => {
        if (cancelled) return;
        console.error('Failed to load agent run trace:', error);
      });

    return () => {
      cancelled = true;
    };
  }, [runId, isStreaming, streamingState]);

  // Return streaming state if available, otherwise historical state
  return streamingState || historicalState;
}
