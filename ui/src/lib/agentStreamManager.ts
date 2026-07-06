/**
 * Module-level manager for agent run SSE streams.
 *
 * Unlike the old useAgentSSE hook (one connection slot per hook instance),
 * this keeps one live EventSource per active run for the whole window, so
 * multiple conversations can run agents concurrently and backgrounded runs
 * keep updating the store. Connections belong to the window, not to any
 * mounted view: switching conversations must NOT tear a stream down, and
 * ensureAgentStream is idempotent so loadConversation re-runs and StrictMode
 * double-effects are safe.
 *
 * Note: WebKit caps HTTP/1.1 connections per host (~6), so the practical
 * ceiling is a handful of concurrent live runs; terminal runs close their
 * stream promptly to free slots.
 */

import { getAgentRunStatus, subscribeToAgentRun } from '@/api/client';
import { useStore } from '@/hooks/useStore';
import type {
  AgentSSEEvent,
  AgentStep,
  AgentCitation,
  ContextUsage,
  StoredContextUsage,
  ModelContextProfile,
  StepStartEvent,
  ThinkingEvent,
  ToolStartEvent,
  ToolApprovalRequiredEvent,
  ToolApprovalDecidedEvent,
  PlanApprovalRequiredEvent,
  PlanApprovedEvent,
  PlanDocUpdatedEvent,
  UserInputRequiredEvent,
  ToolResultEvent,
  AssistantUpdateEvent,
  RunCancelledEvent,
  AnswerEvent,
  TokenUsage,
  CostUsage,
} from '@/types/agent';

interface ManagedStream {
  runId: string;
  /** Bumped on every (re)connect; handlers drop callbacks from stale epochs. */
  epoch: number;
  lastSeq: number;
  streamToken?: string;
  thinkingBuffer: string;
  answerBuffer: string;
  flushTimer: number | null;
  reconnectTimer: number | null;
  close: (() => void) | null;
}

const streams = new Map<string, ManagedStream>();

export function activeAgentStreamCount(): number {
  return streams.size;
}

export function hasAgentStream(runId: string): boolean {
  return streams.has(runId);
}

/**
 * Open a live SSE stream for a run if one is not already open. Idempotent:
 * callers (send paths, loadConversation) can invoke it unconditionally.
 */
export function ensureAgentStream(
  runId: string,
  opts?: { sinceSeq?: number; streamToken?: string },
): void {
  if (streams.has(runId)) return;
  const entry: ManagedStream = {
    runId,
    epoch: 0,
    lastSeq: opts?.sinceSeq ?? 0,
    streamToken: opts?.streamToken,
    thinkingBuffer: '',
    answerBuffer: '',
    flushTimer: null,
    reconnectTimer: null,
    close: null,
  };
  streams.set(runId, entry);
  connect(entry, entry.lastSeq);
}

/** Tear down a run's stream and forget it (terminal events do this themselves). */
export function closeAgentStream(runId: string): void {
  const entry = streams.get(runId);
  if (!entry) return;
  cleanupEntry(entry);
}

function cleanupEntry(entry: ManagedStream): void {
  entry.epoch += 1; // invalidate any in-flight callbacks
  if (entry.reconnectTimer !== null) {
    window.clearTimeout(entry.reconnectTimer);
    entry.reconnectTimer = null;
  }
  if (entry.flushTimer !== null) {
    window.clearTimeout(entry.flushTimer);
    entry.flushTimer = null;
  }
  entry.close?.();
  entry.close = null;
  streams.delete(entry.runId);
}

function connect(entry: ManagedStream, sinceSeq: number): void {
  const id = entry.runId;
  const myEpoch = ++entry.epoch;
  const isStale = () => streams.get(id) !== entry || entry.epoch !== myEpoch;
  const store = () => useStore.getState();

  // Fresh subscriptions replay from seq 0 into a clean slate. Mid-run
  // reconnects resume from lastSeq and must keep the accumulated state.
  if (sinceSeq === 0 || !store().agentRunState[id]) {
    store().initAgentRun(id, 0);
  }
  entry.lastSeq = sinceSeq;

  void getAgentRunStatus(id)
    .then((status) => {
      if (isStale()) return;
      store().updateAgentState(id, {
        currentStep: status.current_step,
        maxSteps: status.max_steps,
        collaboration_mode: status.collaboration_mode,
      });
    })
    .catch(() => {});

  const flushBufferedTokens = () => {
    if (entry.thinkingBuffer) {
      store().appendAgentThinking(id, entry.thinkingBuffer);
      entry.thinkingBuffer = '';
    }
    if (entry.answerBuffer) {
      store().appendAgentAnswer(id, entry.answerBuffer);
      entry.answerBuffer = '';
    }
    if (entry.flushTimer !== null) {
      window.clearTimeout(entry.flushTimer);
      entry.flushTimer = null;
    }
  };

  const scheduleTokenFlush = () => {
    if (entry.flushTimer !== null) return;
    entry.flushTimer = window.setTimeout(flushBufferedTokens, 100);
  };

  const handleEvent = (event: AgentSSEEvent) => {
    if (isStale()) return;

    // Drop replayed/duplicated events after reconnect. Reconnects resume
    // from lastSeq, but defensive de-duping prevents repeated streamed text.
    if (event.seq <= entry.lastSeq) return;
    entry.lastSeq = event.seq;

    const getCurrentStep = () => store().agentRunState[id]?.currentStep || 0;

    // Handle steer events (not in the typed union)
    const rawEvent = event as unknown as Record<string, unknown>;
    if (rawEvent.type === 'steer') {
      const currentState = store().agentRunState[id];
      if (currentState) {
        store().updateAgentState(id, {
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
        store().updateAgentState(id, {
          agentState: 'query' in event ? 'running' : 'synthesizing',
        });
        break;

      case 'step_start': {
        const stepEvent = event as StepStartEvent;
        flushBufferedTokens();
        const currentState = store().agentRunState[id];

        // Save current thinking to previous step before starting new step
        if (currentState && currentState.currentStep > 0 && currentState.thinkingBuffer) {
          store().updateAgentStep(id, currentState.currentStep, {
            thinking_text: currentState.thinkingBuffer,
            state: 'complete',
          });
        }

        store().addAgentStep(id, {
          id: `step-${stepEvent.step_number}`,
          run_id: id,
          step_number: stepEvent.step_number,
          state: 'planning',
          created_at: stepEvent.timestamp,
        } as AgentStep);
        store().updateAgentState(id, {
          currentStep: stepEvent.step_number,
          // Clear thinking buffer for new step
          thinkingBuffer: '',
          // Track live context usage from step_start event
          context_tokens: stepEvent.context_tokens,
          context_remaining: stepEvent.context_remaining,
          context_usage: stepEvent.context_usage,
          stored_context: stepEvent.stored_context,
          context_profile: stepEvent.context_profile,
          compaction_count: stepEvent.compaction_count,
          last_compacted_at_step: stepEvent.last_compacted_at_step,
        });
        break;
      }

      case 'thinking': {
        const thinkEvent = event as ThinkingEvent;
        entry.thinkingBuffer += thinkEvent.content;
        scheduleTokenFlush();
        break;
      }

      case 'tool_start': {
        const toolStartEvent = event as ToolStartEvent;
        store().addAgentToolCall(id, {
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
        const existing = store()
          .agentRunState[id]
          ?.toolCalls.some((tc) => tc.id === approvalEvent.tool_call_id);

        if (!existing) {
          store().addAgentToolCall(id, {
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
          store().updateAgentToolCall(id, approvalEvent.tool_call_id, {
            status: 'pending',
            approval_required: true,
            permission_level: approvalEvent.permission_level,
            diff_preview: approvalEvent.diff_preview,
          });
        }
        break;
      }

      case 'tool_approval_decided': {
        const decidedEvent = event as ToolApprovalDecidedEvent;
        const denied = decidedEvent.decision === 'denied';
        const approvalDecision =
          decidedEvent.decision === 'approved' || decidedEvent.decision === 'denied'
            ? decidedEvent.decision
            : undefined;
        store().updateAgentToolCall(id, decidedEvent.tool_call_id, {
          approval_required: false,
          approval_decision: approvalDecision,
          status: denied ? 'error' : 'running',
          ...(denied ? { completed_at: decidedEvent.timestamp } : {}),
        });
        break;
      }

      case 'plan_approval_required': {
        const planEvent = event as PlanApprovalRequiredEvent;
        store().updateAgentState(id, {
          agentState: 'awaiting_plan_approval',
          pendingPlanApproval: {
            plan_id: planEvent.plan_id,
            run_id: id,
            markdown: planEvent.markdown,
            visible_answer: planEvent.visible_answer,
            plan_doc_path: planEvent.plan_doc_path,
            created_at: planEvent.timestamp,
            status: 'pending',
          },
        });
        break;
      }

      case 'plan_approved': {
        const planEvent = event as PlanApprovedEvent;
        const currentState = store().agentRunState[id];
        store().updateAgentState(id, {
          pendingPlanApproval: currentState?.pendingPlanApproval
            ? { ...currentState.pendingPlanApproval, status: 'approved' }
            : undefined,
          isActive: false,
          agentState: 'complete',
        });
        store().updateRun(id, { status: 'succeeded' });
        localStorage.removeItem(`stream_token:${id}`);
        if (planEvent.implementation_stream_token && planEvent.implementation_run_id) {
          localStorage.setItem(
            `stream_token:${planEvent.implementation_run_id}`,
            planEvent.implementation_stream_token,
          );
        }
        break;
      }

      case 'plan_doc_updated': {
        const planDocEvent = event as PlanDocUpdatedEvent;
        const currentState = store().agentRunState[id];
        store().updateAgentState(id, {
          planDoc: {
            file_path: planDocEvent.file_path,
            action: planDocEvent.action,
            bytes: planDocEvent.bytes,
            summary: planDocEvent.summary,
            updated_at: planDocEvent.timestamp,
          },
          pendingPlanApproval: currentState?.pendingPlanApproval
            ? {
                ...currentState.pendingPlanApproval,
                plan_doc_path:
                  currentState.pendingPlanApproval.plan_doc_path || planDocEvent.file_path,
              }
            : currentState?.pendingPlanApproval,
        });
        break;
      }

      case 'user_input_required': {
        const inputEvent = event as UserInputRequiredEvent;
        store().updateAgentState(id, {
          agentState: 'awaiting_user_input',
          pendingUserInput: {
            request_id: inputEvent.request_id,
            run_id: id,
            questions: inputEvent.questions,
            created_at: inputEvent.timestamp,
          },
        });
        break;
      }

      case 'tool_result': {
        const toolResultEvent = event as ToolResultEvent;
        store().updateAgentToolCall(id, toolResultEvent.tool_call_id, {
          status: toolResultEvent.success ? 'success' : 'error',
          result_summary: toolResultEvent.result_summary,
          result_data: toolResultEvent.result_data,
          bash_output: toolResultEvent.bash_output,
          artifacts: toolResultEvent.artifacts,
          images: toolResultEvent.images,
          duration_ms: toolResultEvent.duration_ms,
          completed_at: toolResultEvent.timestamp,
          approval_required: false,
        });
        break;
      }

      case 'assistant_update': {
        const updateEvent = event as AssistantUpdateEvent;
        store().addAgentAssistantUpdate(id, {
          content: updateEvent.content,
          step_number: updateEvent.step_number,
          seq: updateEvent.seq,
          created_at: updateEvent.timestamp,
        });
        break;
      }

      case 'answer': {
        const answerEvent = event as AnswerEvent;
        entry.answerBuffer += answerEvent.content;
        scheduleTokenFlush();
        break;
      }

      case 'usage_update': {
        const usageEvent = event as unknown as {
          usage?: TokenUsage;
          cost?: CostUsage | null;
          context_usage?: ContextUsage;
          stored_context?: StoredContextUsage;
          context_profile?: ModelContextProfile;
          compaction_count?: number;
          last_compacted_at_step?: number;
        };
        store().updateAgentState(id, {
          usage: usageEvent.usage,
          total_tokens: usageEvent.usage?.total_tokens,
          cost: usageEvent.cost,
          context_usage: usageEvent.context_usage,
          stored_context: usageEvent.stored_context,
          context_profile: usageEvent.context_profile,
          compaction_count: usageEvent.compaction_count,
          last_compacted_at_step: usageEvent.last_compacted_at_step,
        });
        break;
      }

      case 'conversation_compacted': {
        const compactedEvent = event as unknown as {
          message: string;
          step_number?: number;
          context_usage?: ContextUsage;
          stored_context?: StoredContextUsage;
          context_profile?: ModelContextProfile;
          compaction_count?: number;
        };
        const currentState = store().agentRunState[id];
        store().updateAgentState(id, {
          systemEvents: [
            ...(currentState?.systemEvents || []),
            {
              event_type: 'conversation_compacted',
              message: compactedEvent.message,
              step_number: compactedEvent.step_number,
              seq: event.seq,
              created_at: event.timestamp,
            },
          ],
          context_usage: compactedEvent.context_usage,
          stored_context: compactedEvent.stored_context,
          context_profile: compactedEvent.context_profile,
          compaction_count: compactedEvent.compaction_count,
        });
        break;
      }

      case 'run_cancelled': {
        const cancelledEvent = event as RunCancelledEvent;
        flushBufferedTokens();
        store().updateAgentState(id, {
          isActive: false,
          agentState: 'cancelled',
        });
        store().updateRun(id, {
          status: 'cancelled',
          error_detail: cancelledEvent.reason || 'Stopped by user',
        });
        localStorage.removeItem(`stream_token:${id}`);
        break;
      }

      case 'paused': {
        store().updateAgentState(id, {
          agentState: 'paused',
          // isActive stays true — run is alive, just waiting
        });
        break;
      }

      case 'resumed': {
        store().updateAgentState(id, {
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
    error_message?: string;
    citations?: AgentCitation[];
    total_steps: number;
    timing_ms: number;
    total_tokens?: number;
    status?: string;
    usage?: TokenUsage;
    cost?: CostUsage | null;
    context_usage?: ContextUsage;
    stored_context?: StoredContextUsage;
    context_profile?: ModelContextProfile;
    compaction_count?: number;
    last_compacted_at_step?: number;
  }) => {
    if (isStale()) return;
    flushBufferedTokens();
    // Save final step's thinking before marking complete
    const currentState = store().agentRunState[id];
    if (currentState && currentState.currentStep > 0 && currentState.thinkingBuffer) {
      store().updateAgentStep(id, currentState.currentStep, {
        thinking_text: currentState.thinkingBuffer,
        state: 'complete',
      });
    }

    const wasCancelled = result.status === 'cancelled';
    const wasInterrupted = result.status === 'interrupted';

    store().updateAgentState(id, {
      isActive: false,
      agentState: wasInterrupted
        ? 'interrupted'
        : wasCancelled
          ? 'cancelled'
          : result.success
            ? 'complete'
            : 'error',
      timing_ms: result.timing_ms,
      total_tokens: result.total_tokens,
      usage: result.usage,
      cost: result.cost,
      context_usage: result.context_usage,
      stored_context: result.stored_context,
      context_profile: result.context_profile,
      compaction_count: result.compaction_count,
      last_compacted_at_step: result.last_compacted_at_step,
    });

    if (result.citations) {
      store().setAgentCitations(id, result.citations);
    }

    // Update the run in main store
    store().updateRun(id, {
      status: wasInterrupted
        ? 'interrupted'
        : wasCancelled
          ? 'cancelled'
          : result.success
            ? 'succeeded'
            : 'failed',
      final_answer: result.final_answer,
      error_detail: wasInterrupted
        ? result.error_message || 'Run interrupted by server restart'
        : wasCancelled
          ? 'Stopped by user'
          : result.success
            ? undefined
            : result.error_message,
      usage: result.usage,
      cost: result.cost,
      context_usage: result.context_usage,
      stored_context: result.stored_context,
      context_profile: result.context_profile,
    });

    localStorage.removeItem(`stream_token:${id}`);
    cleanupEntry(entry);
  };

  const handleError = (error: string) => {
    if (isStale()) return;
    flushBufferedTokens();
    store().updateAgentState(id, {
      isActive: false,
      agentState: 'error',
    });
    store().updateRun(id, {
      status: 'failed',
      error_detail: error,
    });
    localStorage.removeItem(`stream_token:${id}`);
    cleanupEntry(entry);
  };

  const handleCancelled = () => {
    if (isStale()) return;
    flushBufferedTokens();
    store().updateAgentState(id, {
      isActive: false,
      agentState: 'cancelled',
    });
    store().updateRun(id, {
      status: 'cancelled',
      error_detail: 'Stopped by user',
    });
    localStorage.removeItem(`stream_token:${id}`);
    cleanupEntry(entry);
  };

  const handleDisconnect = () => {
    if (isStale()) return;
    if (!store().agentRunState[id]?.isActive) {
      // Terminal run whose stream dropped (e.g. after plan_approved):
      // nothing to resume, free the connection slot.
      cleanupEntry(entry);
      return;
    }
    if (entry.reconnectTimer !== null) return;
    entry.reconnectTimer = window.setTimeout(() => {
      entry.reconnectTimer = null;
      if (isStale()) return;
      if (!store().agentRunState[id]?.isActive) {
        cleanupEntry(entry);
        return;
      }
      entry.close?.();
      entry.close = null;
      connect(entry, entry.lastSeq);
    }, 750);
  };

  entry.close = subscribeToAgentRun(
    id,
    sinceSeq,
    handleEvent,
    handleComplete,
    handleError,
    handleCancelled,
    entry.streamToken,
    handleDisconnect,
  );
}
