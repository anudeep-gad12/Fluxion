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
  StepStartEvent,
  ThinkingEvent,
  ToolStartEvent,
  ToolResultEvent,
  AnswerEvent,
} from '@/types/agent';

export function useAgentSSE(runId: string | null, maxSteps: number = 10) {
  const unsubscribeRef = useRef<(() => void) | null>(null);
  const lastSeqRef = useRef<number>(0);

  // Store actions
  const initAgentRun = useStore((s) => s.initAgentRun);
  const updateAgentState = useStore((s) => s.updateAgentState);
  const appendAgentThinking = useStore((s) => s.appendAgentThinking);
  const appendAgentAnswer = useStore((s) => s.appendAgentAnswer);
  const addAgentStep = useStore((s) => s.addAgentStep);
  const addAgentToolCall = useStore((s) => s.addAgentToolCall);
  const updateAgentToolCall = useStore((s) => s.updateAgentToolCall);
  const setAgentCitations = useStore((s) => s.setAgentCitations);
  const updateRun = useStore((s) => s.updateRun);

  const subscribe = useCallback(
    (id: string, sinceSeq: number = 0) => {
      // Unsubscribe from previous
      if (unsubscribeRef.current) {
        unsubscribeRef.current();
      }

      // Initialize agent state in store
      initAgentRun(id, maxSteps);
      lastSeqRef.current = sinceSeq;

      const handleEvent = (event: AgentSSEEvent) => {
        // Track sequence for resumption
        if (event.seq > lastSeqRef.current) {
          lastSeqRef.current = event.seq;
        }

        // Get current step from store
        const getCurrentStep = () => {
          const state = useStore.getState().agentRunState[id];
          return state?.currentStep || 0;
        };

        switch (event.type) {
          case 'agent_state':
            updateAgentState(id, {
              agentState: 'query' in event ? 'running' : 'synthesizing',
            });
            break;

          case 'step_start': {
            const stepEvent = event as StepStartEvent;
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
            });
            break;
          }

          case 'thinking': {
            const thinkEvent = event as ThinkingEvent;
            appendAgentThinking(id, thinkEvent.content);
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

          case 'tool_result': {
            const toolResultEvent = event as ToolResultEvent;
            updateAgentToolCall(id, toolResultEvent.tool_call_id, {
              status: toolResultEvent.success ? 'success' : 'error',
              result_summary: toolResultEvent.result_summary,
              duration_ms: toolResultEvent.duration_ms,
              completed_at: toolResultEvent.timestamp,
            });
            break;
          }

          case 'answer': {
            const answerEvent = event as AnswerEvent;
            appendAgentAnswer(id, answerEvent.content);
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
      }) => {
        updateAgentState(id, {
          isActive: false,
          agentState: result.success ? 'complete' : 'error',
        });

        if (result.citations) {
          setAgentCitations(id, result.citations);
        }

        // Update the run in main store
        updateRun(id, {
          status: result.success ? 'succeeded' : 'failed',
          final_answer: result.final_answer,
        });
      };

      const handleError = (error: string) => {
        updateAgentState(id, {
          isActive: false,
          agentState: 'error',
        });
        updateRun(id, {
          status: 'failed',
          error_detail: error,
        });
      };

      const handleCancelled = () => {
        updateAgentState(id, {
          isActive: false,
          agentState: 'cancelled',
        });
        updateRun(id, {
          status: 'failed',
          error_detail: 'Cancelled by user',
        });
      };

      unsubscribeRef.current = subscribeToAgentRun(
        id,
        sinceSeq,
        handleEvent,
        handleComplete,
        handleError,
        handleCancelled
      );
    },
    [
      initAgentRun,
      updateAgentState,
      appendAgentThinking,
      appendAgentAnswer,
      addAgentStep,
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
  }, []);

  const reconnect = useCallback(() => {
    if (runId) {
      subscribe(runId, lastSeqRef.current);
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
