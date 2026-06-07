/**
 * Hook to load agent run details for both streaming and historical runs.
 * During streaming: uses Zustand store (in-memory)
 * After completion/refresh: fetches from API and transforms to AgentUIState
 */

import { useEffect, useState } from 'react';
import { getAgentRunTrace } from '@/api/client';
import type { AgentUIState, AgentStep, AgentToolCall, AgentCitation } from '@/types/agent';
import { useAgentRunState } from './useStore';

const historicalAgentRunCache = new Map<string, AgentUIState>();
const historicalAgentRunInFlight = new Map<string, Promise<AgentUIState>>();

const MAX_HISTORICAL_TRACE_REQUESTS = 2;
let historicalTraceActiveCount = 0;
const historicalTraceQueue: Array<() => void> = [];

function parseResultDetail(resultDetail?: string | null): unknown {
  if (!resultDetail) return null;
  try {
    return JSON.parse(resultDetail);
  } catch {
    return resultDetail;
  }
}

function resultDataFromTraceToolCall(tc: AgentToolCall): string | undefined {
  if (tc.result_data) return tc.result_data;
  if (tc.tool_name !== 'write_file' && tc.tool_name !== 'edit_file') return undefined;

  const payload = parseResultDetail(tc.result_detail);
  if (typeof payload === 'string') return payload;
  if (payload && typeof payload === 'object') {
    const diff = (payload as Record<string, unknown>).diff ?? (payload as Record<string, unknown>).preview;
    return typeof diff === 'string' ? diff : undefined;
  }
  return undefined;
}

function bashOutputFromTraceToolCall(
  tc: AgentToolCall
): AgentToolCall['bash_output'] | undefined {
  if (tc.bash_output) return tc.bash_output;
  if (tc.tool_name !== 'bash') return undefined;

  const payload = parseResultDetail(tc.result_detail);
  if (!payload || typeof payload !== 'object') return undefined;
  const data = payload as Record<string, unknown>;
  return {
    stdout: String(data.stdout ?? ''),
    stderr: String(data.stderr ?? ''),
    exit_code: typeof data.exit_code === 'number' ? data.exit_code : undefined,
    truncated: Boolean(data.truncated ?? data.timed_out),
  };
}

function runHistoricalTraceTask<T>(task: () => Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const start = () => {
      historicalTraceActiveCount += 1;
      task()
        .then(resolve, reject)
        .finally(() => {
          historicalTraceActiveCount = Math.max(0, historicalTraceActiveCount - 1);
          const next = historicalTraceQueue.shift();
          if (next) next();
        });
    };

    if (historicalTraceActiveCount < MAX_HISTORICAL_TRACE_REQUESTS) {
      start();
    } else {
      historicalTraceQueue.push(start);
    }
  });
}

function loadHistoricalAgentRun(runId: string): Promise<AgentUIState> {
  const cached = historicalAgentRunCache.get(runId);
  if (cached) return Promise.resolve(cached);

  const inFlight = historicalAgentRunInFlight.get(runId);
  if (inFlight) return inFlight;

  const request = runHistoricalTraceTask(async () => {
    const trace = await getAgentRunTrace(runId);

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
      result_detail: tc.result_detail,
      result_data: resultDataFromTraceToolCall(tc),
      bash_output: bashOutputFromTraceToolCall(tc),
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

    const nextState: AgentUIState = {
      isActive: false,
      currentStep: steps.length,
      maxSteps: Math.max(steps.length, 1),
      agentState: trace.status === 'succeeded' ? 'complete' : trace.status,
      thinkingBuffer: '',
      answerBuffer: trace.final_answer || '',
      steps,
      toolCalls,
      citations,
      assistantUpdates: trace.assistant_updates || [],
      systemEvents: trace.system_events || [],
      injectedSteers: [],
      lastSeq: 0,
      total_tokens: trace.usage?.total_tokens,
      usage: trace.usage,
      cost: trace.cost,
      context_usage: trace.context_usage,
      stored_context: trace.stored_context,
      context_profile: trace.context_profile,
      compaction_count: trace.compaction_count,
      last_compacted_at_step: trace.last_compacted_at_step,
    };

    historicalAgentRunCache.set(runId, nextState);
    return nextState;
  }).finally(() => {
    historicalAgentRunInFlight.delete(runId);
  });

  historicalAgentRunInFlight.set(runId, request);
  return request;
}

/**
 * Get agent run state, either from streaming state or loaded from API.
 *
 * @param runId - The agent run ID
 * @param isStreaming - Whether the run is currently streaming
 * @returns AgentUIState or undefined if not available yet
 */
export function useAgentRunDetails(
  runId: string | null,
  isStreaming: boolean
): AgentUIState | undefined {
  const streamingState = useAgentRunState(runId);
  const [historicalState, setHistoricalState] = useState<AgentUIState | undefined>(
    () => (runId ? historicalAgentRunCache.get(runId) : undefined)
  );

  useEffect(() => {
    setHistoricalState(runId ? historicalAgentRunCache.get(runId) : undefined);
  }, [runId]);

  useEffect(() => {
    if (!runId || isStreaming || historicalState) {
      return;
    }

    // Historical traces can be large. Limit them globally and dedupe in-flight
    // requests so old conversations cannot starve foreground API calls like the
    // model picker behind dozens of trace/status fetches.
    let cancelled = false;

    loadHistoricalAgentRun(runId)
      .then((state) => {
        if (!cancelled) setHistoricalState(state);
      })
      .catch((error) => {
        if (cancelled) return;
        console.error('Failed to load agent run trace:', error);
      });

    return () => {
      cancelled = true;
    };
  }, [runId, isStreaming, historicalState]);

  // While streaming, prefer live state. Once complete, prefer persisted trace
  // data so stale in-memory state cannot hide thinking/tool history.
  return isStreaming ? (streamingState || historicalState) : (historicalState || streamingState);
}
