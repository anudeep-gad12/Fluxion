/**
 * Agent SSE hook for streaming agent run events.
 * Handles real-time event streaming with reconnection support.
 */

import { useEffect, useRef, useCallback } from 'react';
import { subscribeToAgentRun } from '@/api/client';
import { useStore } from './useStore';
import type {
  AgentSSEEvent,
  AgentStep,
  AgentCitation,
  ContextUsage,
  StepStartEvent,
  ThinkingEvent,
  ToolStartEvent,
  ToolApprovalRequiredEvent,
  ToolResultEvent,
  AnswerEvent,
  TokenUsage,
  CostUsage,
} from '@/types/agent';

export function useAgentSSE(runId: string | null, maxSteps: number = 10) {
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const lastSeqRef = useRef<number>(0);
  const streamTokenRef = useRef<string | undefined>();
  const thinkingBufferRef = useRef<Record<string, string>>({});
  const answerBufferRef = useRef<Record<string, string>>({});
  const flushTimerRef = useRef<Record<string, number>>({});
  const reconnectTimerRef = useRef<number | null>(null);
  // Guard against stale events from previous EventSource connections.
  // When subscribe() is called, connectionIdRef increments. The handleEvent
  // closure captures the current value; late events from a closed EventSource
  // will have a stale connectionId and get dropped.
  const connectionIdRef = useRef<number>(0);

  // Store actions
  const initAgentRun = useStore((s) => s.initAgentRun);
  const updateAgentState = useStore((s) => s.updateAgentState);
  const appendAgentThinking = useStore((s) => s.appendAgentThinking);
  const appendAgentAnswer = useStore((s) => s.appendAgentAnswer);
  const addAgentStep = useStore((s) => s.addAgentStep);
  const updateAgentStep = useStore((s) => s.updateAgentStep);
  const addAgentToolCall = useStore((s) => s.addAgentToolCall);
  const updateAgentToolCall = useStore((s) => s.updateAgentToolCall);
  const setAgentCitations = useStore((s) => s.setAgentCitations);
  const updateRun = useStore((s) => s.updateRun);

  const subscribe = useCallback(
    (id: string, sinceSeq: number = 0, streamToken?: string) => {
      // Store token for reconnection
      if (streamToken !== undefined) {
        streamTokenRef.current = streamToken;
      }
      // Unsubscribe from previous
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }

      // New connection — stale events from previous EventSource are ignored
      const myConnectionId = ++connectionIdRef.current;

      // Initialize agent state in store
      initAgentRun(id, maxSteps);
      lastSeqRef.current = sinceSeq;

      const flushBufferedTokens = () => {
        const thinking = thinkingBufferRef.current[id];
        if (thinking) {
          appendAgentThinking(id, thinking);
          thinkingBufferRef.current[id] = '';
        }

        const answer = answerBufferRef.current[id];
        if (answer) {
          appendAgentAnswer(id, answer);
          answerBufferRef.current[id] = '';
        }

        if (flushTimerRef.current[id]) {
          window.clearTimeout(flushTimerRef.current[id]);
          delete flushTimerRef.current[id];
        }
      };

      const scheduleTokenFlush = () => {
        if (flushTimerRef.current[id]) return;
        flushTimerRef.current[id] = window.setTimeout(flushBufferedTokens, 100);
      };

      const handleEvent = (event: AgentSSEEvent) => {
        // Drop events from a previous (stale) EventSource connection
        if (myConnectionId !== connectionIdRef.current) return;

        // Drop replayed/duplicated events after reconnect. Reconnects resume
        // from lastSeq, but defensive de-duping prevents repeated streamed text.
        if (event.seq <= lastSeqRef.current) return;

        // Track sequence for resumption
        lastSeqRef.current = event.seq;

        // Get current step from store
        const getCurrentStep = () => {
          const state = useStore.getState().agentRunState[id];
          return state?.currentStep || 0;
        };

        // Handle steer events (not in the typed union)
        const rawEvent = event as unknown as Record<string, unknown>;
        if (rawEvent.type === 'steer') {
          const currentState = useStore.getState().agentRunState[id];
          if (currentState) {
            updateAgentState(id, {
              injectedSteers: [
                ...currentState.injectedSteers,
                {
                  content: (rawEvent.content as string) || '',
                  step_number: (rawEvent.step_number as number) || getCurrentStep(),
                },
              ],
            });
          }
          return;
        }

        switch (event.type) {
          case 'agent_state':
            updateAgentState(id, {
              agentState: 'query' in event ? 'running' : 'synthesizing',
            });
            break;

          case 'step_start': {
            const stepEvent = event as StepStartEvent;
            flushBufferedTokens();
            const currentState = useStore.getState().agentRunState[id];

            // Save current thinking to previous step before starting new step
            if (currentState && currentState.currentStep > 0 && currentState.thinkingBuffer) {
              updateAgentStep(id, currentState.currentStep, {
                thinking_text: currentState.thinkingBuffer,
                state: 'complete',
              });
            }

            addAgentStep(id, {
              id: `step-${stepEvent.step_number}`,
              run_id: id,
              step_number: stepEvent.step_number,
              state: 'planning',
              created_at: stepEvent.timestamp,
            } as AgentStep);
            updateAgentState(id, {
              currentStep: stepEvent.step_number,
              // Clear thinking buffer for new step
              thinkingBuffer: '',
              // Track live context usage from step_start event
              context_tokens: stepEvent.context_tokens,
              context_remaining: stepEvent.context_remaining,
            });
            break;
          }

          case 'thinking': {
            const thinkEvent = event as ThinkingEvent;
            thinkingBufferRef.current[id] = (thinkingBufferRef.current[id] || '') + thinkEvent.content;
            scheduleTokenFlush();
            break;
          }

          case 'tool_start': {
            const toolStartEvent = event as ToolStartEvent;
            addAgentToolCall(id, {
              id: toolStartEvent.tool_call_id,
              run_id: id,
              step_id: `step-${getCurrentStep()}`,
              tool_name: toolStartEvent.tool_name,
              arguments: toolStartEvent.arguments,
              status: 'running',
              created_at: toolStartEvent.timestamp,
              started_at: toolStartEvent.timestamp,
              idempotency_key: '',
              execution_attempt: 1,
            });
            break;
          }

          case 'tool_approval_required': {
            const approvalEvent = event as ToolApprovalRequiredEvent;
            const currentStep = getCurrentStep();
            const existing = useStore
              .getState()
              .agentRunState[id]
              ?.toolCalls.some((tc) => tc.id === approvalEvent.tool_call_id);

            if (!existing) {
              addAgentToolCall(id, {
                id: approvalEvent.tool_call_id,
                run_id: id,
                step_id: `step-${currentStep}`,
                tool_name: approvalEvent.tool_name,
                arguments: approvalEvent.arguments,
                status: 'pending',
                created_at: approvalEvent.timestamp,
                started_at: approvalEvent.timestamp,
                idempotency_key: '',
                execution_attempt: 1,
                approval_required: true,
                permission_level: approvalEvent.permission_level,
                diff_preview: approvalEvent.diff_preview,
              });
            } else {
              updateAgentToolCall(id, approvalEvent.tool_call_id, {
                status: 'pending',
                approval_required: true,
                permission_level: approvalEvent.permission_level,
                diff_preview: approvalEvent.diff_preview,
              });
            }
            break;
          }

          case 'tool_result': {
            const toolResultEvent = event as ToolResultEvent;
            updateAgentToolCall(id, toolResultEvent.tool_call_id, {
              status: toolResultEvent.success ? 'success' : 'error',
              result_summary: toolResultEvent.result_summary,
              result_data: toolResultEvent.result_data,
              bash_output: toolResultEvent.bash_output,
              duration_ms: toolResultEvent.duration_ms,
              completed_at: toolResultEvent.timestamp,
              approval_required: false,
            });
            break;
          }

          case 'answer': {
            const answerEvent = event as AnswerEvent;
            answerBufferRef.current[id] = (answerBufferRef.current[id] || '') + answerEvent.content;
            scheduleTokenFlush();
            break;
          }

          case 'usage_update': {
            const usageEvent = event as unknown as {
              usage?: TokenUsage;
              cost?: CostUsage | null;
            };
            updateAgentState(id, {
              usage: usageEvent.usage,
              total_tokens: usageEvent.usage?.total_tokens,
              cost: usageEvent.cost,
            });
            break;
          }

          case 'paused': {
            updateAgentState(id, {
              agentState: 'paused',
              // isActive stays true — run is alive, just waiting
            });
            break;
          }

          case 'resumed': {
            updateAgentState(id, {
              agentState: 'running',
            });
            break;
          }
        }
      };

      const handleComplete = (result: {
        run_id: string;
        success: boolean;
        final_answer?: string;
        citations?: AgentCitation[];
        total_steps: number;
        timing_ms: number;
        total_tokens?: number;
        usage?: TokenUsage;
        cost?: CostUsage | null;
        context_usage?: ContextUsage;
      }) => {
        if (myConnectionId !== connectionIdRef.current) return;
        flushBufferedTokens();
        // Save final step's thinking before marking complete
        const currentState = useStore.getState().agentRunState[id];
        if (currentState && currentState.currentStep > 0 && currentState.thinkingBuffer) {
          updateAgentStep(id, currentState.currentStep, {
            thinking_text: currentState.thinkingBuffer,
            state: 'complete',
          });
        }

        updateAgentState(id, {
          isActive: false,
          agentState: result.success ? 'complete' : 'error',
          timing_ms: result.timing_ms,
          total_tokens: result.total_tokens,
          usage: result.usage,
          cost: result.cost,
          context_usage: result.context_usage,
        });

        if (result.citations) {
          setAgentCitations(id, result.citations);
        }

        // Update the run in main store
        updateRun(id, {
          status: result.success ? 'succeeded' : 'failed',
          final_answer: result.final_answer,
        });

        // Clean up stored stream token
        localStorage.removeItem(`stream_token:${id}`);
      };

      const handleError = (error: string) => {
        if (myConnectionId !== connectionIdRef.current) return;
        flushBufferedTokens();
        updateAgentState(id, {
          isActive: false,
          agentState: 'error',
        });
        updateRun(id, {
          status: 'failed',
          error_detail: error,
        });

        // Clean up stored stream token
        localStorage.removeItem(`stream_token:${id}`);
      };

      const handleCancelled = () => {
        if (myConnectionId !== connectionIdRef.current) return;
        flushBufferedTokens();
        updateAgentState(id, {
          isActive: false,
          agentState: 'cancelled',
        });
        updateRun(id, {
          status: 'failed',
          error_detail: 'Cancelled by user',
        });
      };

      const handleDisconnect = () => {
        if (myConnectionId !== connectionIdRef.current) return;
        const currentState = useStore.getState().agentRunState[id];
        if (!currentState?.isActive) return;
        if (reconnectTimerRef.current) return;

        reconnectTimerRef.current = window.setTimeout(() => {
          reconnectTimerRef.current = null;
          if (myConnectionId !== connectionIdRef.current) return;
          const latestState = useStore.getState().agentRunState[id];
          if (!latestState?.isActive) return;
          subscribe(id, lastSeqRef.current, streamTokenRef.current);
        }, 750);
      };

      unsubscribeRef.current = subscribeToAgentRun(
        id,
        sinceSeq,
        handleEvent,
        handleComplete,
        handleError,
        handleCancelled,
        streamTokenRef.current,
        handleDisconnect
      );
    },
    [
      initAgentRun,
      updateAgentState,
      appendAgentThinking,
      appendAgentAnswer,
      addAgentStep,
      updateAgentStep,
      addAgentToolCall,
      updateAgentToolCall,
      setAgentCitations,
      updateRun,
      maxSteps,
    ]
  );

  const unsubscribe = useCallback(() => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
    connectionIdRef.current += 1;
    if (reconnectTimerRef.current) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    Object.values(flushTimerRef.current).forEach((timer) => window.clearTimeout(timer));
    flushTimerRef.current = {};
  }, []);

  const reconnect = useCallback(() => {
    if (runId) {
      subscribe(runId, lastSeqRef.current, streamTokenRef.current);
    }
  }, [runId, subscribe]);

  useEffect(() => {
    if (runId) {
      subscribe(runId, 0);
    }

    return () => {
      unsubscribe();
    };
  }, [runId, subscribe, unsubscribe]);

  return { subscribe, unsubscribe, reconnect };
}
