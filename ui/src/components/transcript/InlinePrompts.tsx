/**
 * Blocking agent prompts (tool approval / plan review / user input) rendered
 * flat, Claude-Code style — a kind-colored left rule, marker lines, and plain
 * text action buttons. Decision handlers moved verbatim from AgentLiveHUD
 * (they mutate the store optimistically on 404/409 — do not rewrite).
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  answerAgentUserInput,
  approveAgentPlan,
  approveAgentToolCall,
  denyAgentToolCall,
  rejectAgentPlan,
} from '@/api/client';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import { formatArguments, UnifiedDiffView } from '@/components/transcript/toolFormat';
import { useStore } from '@/hooks/useStore';
import { cn } from '@/lib/utils';
import type { AgentUIState } from '@/types/agent';

interface InlinePromptsProps {
  agentState: AgentUIState;
  onImplementationStarted?: (run: {
    run_id: string;
    stream_token?: string;
    stream_url?: string;
  }) => void;
}

export function InlinePrompts({ agentState, onImplementationStarted }: InlinePromptsProps) {
  const [deciding, setDeciding] = useState<'approve' | 'deny' | null>(null);
  const [planDecision, setPlanDecision] = useState<'approve' | 'reject' | null>(null);
  const [rejectFeedback, setRejectFeedback] = useState('');
  const [userInputSubmitting, setUserInputSubmitting] = useState<string | null>(null);
  const [userInputAnswers, setUserInputAnswers] = useState<Record<string, string>>({});
  const decidingRef = useRef(false);
  const pendingApproval = useMemo(
    () =>
      [...agentState.toolCalls]
        .reverse()
        .find((toolCall) => toolCall.status === 'pending' && toolCall.approval_required),
    [agentState.toolCalls]
  );

  useEffect(() => {
    if (!pendingApproval) {
      setDeciding(null);
      decidingRef.current = false;
    }
  }, [pendingApproval]);

  useEffect(() => {
    setUserInputAnswers({});
  }, [agentState.pendingUserInput?.request_id]);

  const decide = async (decision: 'approve' | 'deny') => {
    if (!pendingApproval || decidingRef.current) return;
    decidingRef.current = true;
    setDeciding(decision);
    try {
      const response = await (decision === 'approve'
        ? approveAgentToolCall(pendingApproval.run_id, pendingApproval.id)
        : denyAgentToolCall(pendingApproval.run_id, pendingApproval.id));
      const resolvedDecision =
        response.status === 'approved' || response.status === 'denied' ? response.status : undefined;
      useStore.getState().updateAgentToolCall(pendingApproval.run_id, pendingApproval.id, {
        approval_required: false,
        approval_decision: resolvedDecision,
        status: response.status === 'approved' ? 'running' : 'error',
        ...(response.status !== 'approved' ? { completed_at: new Date().toISOString() } : {}),
      });
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : String(error);
      const apiError = error as { status?: number };
      console.error(`[Approval] ${decision} failed for ${pendingApproval.run_id}/${pendingApproval.id}:`, error);
      // 404/409 means the approval was already processed or the run moved on.
      // Clear the stale pending state so the UI unblocks.
      useStore.getState().updateAgentToolCall(pendingApproval.run_id, pendingApproval.id, {
        approval_required: false,
        status: decision === 'approve' ? 'running' : 'error',
      });
      toast.error(`${decision} failed: ${apiError.status || 'N/A'} - ${errMsg}`);
    } finally {
      decidingRef.current = false;
      setDeciding(null);
    }
  };

  const decidePlan = async (decision: 'approve' | 'reject') => {
    const pendingPlan = agentState.pendingPlanApproval;
    if (!pendingPlan || planDecision) return;
    setPlanDecision(decision);
    try {
      if (decision === 'approve') {
        const response = await approveAgentPlan(pendingPlan.run_id, pendingPlan.plan_id);
        const store = useStore.getState();
        store.updateAgentState(pendingPlan.run_id, {
          isActive: false,
          agentState: 'complete',
          pendingPlanApproval: { ...pendingPlan, status: 'approved' },
        });
        store.updateRun(pendingPlan.run_id, { status: 'succeeded' });
        localStorage.removeItem(`stream_token:${pendingPlan.run_id}`);
        if (response.implementation_run_id) {
          onImplementationStarted?.({
            run_id: response.implementation_run_id,
            stream_token: response.implementation_stream_token,
            stream_url: response.implementation_stream_url,
          });
        }
      } else {
        await rejectAgentPlan(pendingPlan.run_id, pendingPlan.plan_id, rejectFeedback);
        useStore.getState().updateAgentState(pendingPlan.run_id, {
          pendingPlanApproval: { ...pendingPlan, status: 'rejected' },
          agentState: 'running',
        });
        setRejectFeedback('');
      }
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : String(error);
      toast.error(`plan ${decision} failed: ${errMsg}`);
    } finally {
      setPlanDecision(null);
    }
  };

  const copyPlanPath = async () => {
    const path = agentState.pendingPlanApproval?.plan_doc_path || agentState.planDoc?.file_path;
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      toast.success('plan path copied');
    } catch {
      toast.error('copy failed');
    }
  };

  const submitUserInput = async () => {
    const pendingInput = agentState.pendingUserInput;
    if (!pendingInput || userInputSubmitting) return;
    setUserInputSubmitting(pendingInput.request_id);
    try {
      await answerAgentUserInput(pendingInput.run_id, pendingInput.request_id, userInputAnswers);
      useStore.getState().updateAgentState(pendingInput.run_id, {
        pendingUserInput: undefined,
        agentState: 'running',
      });
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : String(error);
      toast.error(`answer failed: ${errMsg}`);
    } finally {
      setUserInputSubmitting(null);
    }
  };

  if (agentState.pendingPlanApproval?.status === 'pending') {
    const pendingPlan = agentState.pendingPlanApproval;
    const planPath = pendingPlan.plan_doc_path || agentState.planDoc?.file_path;
    return (
      <div className="tr-prompt" data-kind="plan">
        <div className="tr-line">
          <span className="tr-marker" data-tone="system" aria-hidden>⏺</span>
          <div className="tr-body tr-mono">
            <span className="tr-tool-name">Plan ready for review</span>
            <span className="tr-tool-meta"> · approve to implement, reject to keep planning</span>
          </div>
        </div>

        <div className="tr-prompt-doc">
          {pendingPlan.markdown.includes('\n+++ ') ? (
            <UnifiedDiffView diff={pendingPlan.markdown} />
          ) : (
            <AnswerMarkdown content={pendingPlan.markdown} />
          )}
        </div>

        {planPath ? (
          <div className="tr-result">
            <span className="tr-result-marker" aria-hidden>⎿</span>
            <div className="tr-result-body">
              {planPath}{' '}
              <button type="button" onClick={copyPlanPath} className="tr-more">
                copy path
              </button>
            </div>
          </div>
        ) : null}

        <textarea
          value={rejectFeedback}
          onChange={(event) => setRejectFeedback(event.target.value)}
          placeholder="Optional reject feedback"
          className="tr-prompt-input"
        />

        <div className="tr-prompt-actions">
          <button
            type="button"
            onClick={() => decidePlan('approve')}
            disabled={planDecision !== null}
            className="tr-prompt-btn"
            data-action="approve"
          >
            {planDecision === 'approve' ? 'approving…' : 'approve'}
          </button>
          <button
            type="button"
            onClick={() => decidePlan('reject')}
            disabled={planDecision !== null}
            className="tr-prompt-btn"
            data-action="deny"
          >
            {planDecision === 'reject' ? 'rejecting…' : 'reject'}
          </button>
        </div>
      </div>
    );
  }

  if (agentState.pendingUserInput) {
    const pendingInput = agentState.pendingUserInput;
    return (
      <div className="tr-prompt" data-kind="input">
        <div className="tr-line">
          <span className="tr-marker" data-tone="system" aria-hidden>⏺</span>
          <div className="tr-body tr-mono">
            <span className="tr-tool-name">Question from the agent</span>
          </div>
        </div>

        {pendingInput.questions.map((question) => (
          <div key={question.id} className="tr-prompt-question">
            <div className="tr-prompt-question-header">{question.header}</div>
            <div className="tr-prompt-question-text">{question.question}</div>
            <div className="tr-prompt-options">
              {question.options.map((option) => (
                <button
                  key={option.label}
                  type="button"
                  onClick={() => setUserInputAnswers((current) => ({
                    ...current,
                    [question.id]: option.label,
                  }))}
                  disabled={userInputSubmitting !== null}
                  data-selected={userInputAnswers[question.id] === option.label ? 'true' : 'false'}
                  className="tr-prompt-option"
                  title={option.description}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="tr-prompt-actions">
          <button
            type="button"
            onClick={submitUserInput}
            disabled={
              userInputSubmitting !== null
              || pendingInput.questions.some((question) => !userInputAnswers[question.id])
            }
            className="tr-prompt-btn"
            data-action="approve"
          >
            {userInputSubmitting ? 'sending…' : 'send'}
          </button>
        </div>
      </div>
    );
  }

  if (pendingApproval) {
    const argPreview = formatArguments(pendingApproval.tool_name, pendingApproval.arguments);
    const diffPreview =
      typeof pendingApproval.diff_preview === 'string' && pendingApproval.diff_preview.trim()
        ? pendingApproval.diff_preview
        : null;
    return (
      <div className="tr-prompt" data-kind="permission">
        <div className="tr-line">
          <span className="tr-marker" data-tone="steer" aria-hidden>⏺</span>
          <div className="tr-body tr-mono">
            <span className="tr-tool-name">Permission required</span>
            <span className="tr-tool-args"> · {pendingApproval.tool_name.replace(/_/g, ' ')}</span>
            {pendingApproval.permission_level ? (
              <span className="tr-tool-meta"> ({pendingApproval.permission_level})</span>
            ) : null}
          </div>
        </div>

        {argPreview ? (
          <div className="tr-result">
            <span className="tr-result-marker" aria-hidden>⎿</span>
            <div className="tr-result-body">
              <pre className="tr-pre">{argPreview}</pre>
            </div>
          </div>
        ) : null}

        {diffPreview ? (
          diffPreview.includes('\n+++ ') ? (
            <UnifiedDiffView diff={diffPreview} compact />
          ) : (
            <div className="tr-result">
              <span className="tr-result-marker" aria-hidden>⎿</span>
              <div className="tr-result-body">
                <pre className={cn('tr-pre', 'max-h-48 overflow-auto')}>{diffPreview}</pre>
              </div>
            </div>
          )
        ) : null}

        <div className="tr-prompt-actions">
          <button
            type="button"
            onClick={() => decide('approve')}
            disabled={deciding !== null}
            className="tr-prompt-btn"
            data-action="approve"
          >
            {deciding === 'approve' ? 'approving…' : 'approve'}
          </button>
          <button
            type="button"
            onClick={() => decide('deny')}
            disabled={deciding !== null}
            className="tr-prompt-btn"
            data-action="deny"
          >
            {deciding === 'deny' ? 'denying…' : 'deny'}
          </button>
        </div>
      </div>
    );
  }

  return null;
}
