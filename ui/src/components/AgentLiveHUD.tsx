import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  answerAgentUserInput,
  approveAgentPlan,
  approveAgentToolCall,
  denyAgentToolCall,
  rejectAgentPlan,
} from '@/api/client';
import { cn } from '@/lib/utils';
import { AnswerMarkdown } from '@/components/AnswerMarkdown';
import { formatArguments, UnifiedDiffView } from '@/components/ToolCallCard';
import { formatAgentCost, formatAgentTokens, useDerivedAgentPhase } from '@/lib/agentLiveState';
import { useStore } from '@/hooks/useStore';
import type { AgentToolCall } from '@/types/agent';
import type { AgentUIState } from '@/types/agent';

function formatElapsedSeconds(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;
}

function ElapsedClock({ startedAt }: { startedAt: string }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const startRef = useRef(new Date(startedAt).getTime());

  useEffect(() => {
    startRef.current = new Date(startedAt).getTime();
    setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
  }, [startedAt]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setElapsedSeconds(Math.max(0, Math.floor((Date.now() - startRef.current) / 1000)));
    }, 1000);
    return () => window.clearInterval(interval);
  }, []);

  return <span>{formatElapsedSeconds(elapsedSeconds)}</span>;
}

function MetricPill({
  label,
  value,
  highlighted = false,
  caution = false,
}: {
  label: string;
  value: string | number | JSX.Element;
  highlighted?: boolean;
  caution?: boolean;
}) {
  return (
    <div
      className={cn(
        'ui-transition inline-flex items-center gap-2 rounded-md border px-2 py-1',
        caution
          ? 'border-amber-500/20 bg-amber-500/8 text-amber-200'
          : 'border-white/8 bg-white/[0.04] text-zinc-300'
      )}
    >
      <span className="text-[11px] text-zinc-500">{label}</span>
      <span className={cn('tabular-nums text-[12px]', highlighted ? 'text-zinc-50' : 'text-current')}>
        {value}
      </span>
    </div>
  );
}

const WEB_APPROVE_BTN =
  'ui-transition rounded-full border border-emerald-500/20 bg-emerald-500/[0.08] px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-emerald-100 hover:border-emerald-400/30 hover:text-white disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-500';

const WEB_DENY_BTN =
  'ui-transition rounded-full border border-red-500/20 bg-red-500/[0.08] px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-red-100 hover:border-red-400/30 hover:text-white disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-500';

function formatApprovalArguments(toolCall: AgentToolCall): string {
  return formatArguments(toolCall.tool_name, toolCall.arguments);
}

interface AgentLiveHUDProps {
  runId: string;
  runCreatedAt: string;
  agentState: AgentUIState;
  variant?: 'default' | 'desktop';
  onImplementationStarted?: (run: {
    run_id: string;
    stream_token?: string;
    stream_url?: string;
  }) => void;
}

export const AgentLiveHUD = memo(function AgentLiveHUD({
  runId,
  runCreatedAt,
  agentState,
  variant = 'default',
  onImplementationStarted,
}: AgentLiveHUDProps) {
  const phase = useDerivedAgentPhase(agentState, runId);
  const startedAt = agentState.steps[0]?.created_at || runCreatedAt;
  const currentContextPct = agentState.context_usage
    ? `${Math.round(agentState.context_usage.utilization_pct_effective)}%`
    : '—';
  const compactionCount = (agentState.compaction_count ?? agentState.context_usage?.compactions_so_far) ?? 0;
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

  const isDesktop = variant === 'desktop';
  const hasBlockingState =
    agentState.pendingPlanApproval?.status === 'pending'
    || !!agentState.pendingUserInput
    || !!pendingApproval;

  const panelKind: 'plan' | 'input' | 'permission' = agentState.pendingPlanApproval?.status === 'pending'
    ? 'plan'
    : agentState.pendingUserInput
      ? 'input'
      : 'permission';

  const metricsLine = isDesktop ? (
    <span className="desktop-hud-stats">
      <span className="desktop-hud-stat" data-warn={phase.isContextWarning ? 'true' : 'false'}>
        {currentContextPct} ctx
      </span>
      <span className="desktop-hud-stat">
        <ElapsedClock startedAt={startedAt} />
      </span>
      {agentState.total_tokens ? (
        <span className="desktop-hud-stat">{formatAgentTokens(agentState.total_tokens)} tok</span>
      ) : null}
    </span>
  ) : (
    <>
      <span className={cn(phase.isContextWarning && 'text-amber-300/90')}>
        {currentContextPct} ctx
      </span>
      <span className="text-zinc-700"> · </span>
      <ElapsedClock startedAt={startedAt} />
      {agentState.total_tokens ? (
        <>
          <span className="text-zinc-700"> · </span>
          <span>{formatAgentTokens(agentState.total_tokens)} tok</span>
        </>
      ) : null}
    </>
  );

  const approveBtnClass = isDesktop ? 'desktop-hud-btn-approve' : WEB_APPROVE_BTN;
  const denyBtnClass = isDesktop ? 'desktop-hud-btn-deny' : WEB_DENY_BTN;

  if (isDesktop && !hasBlockingState) {
    const isActive = agentState.isActive;
    return (
      <div className="desktop-hud-live mb-2" data-active={isActive ? 'true' : 'false'}>
        <div className="desktop-hud-live-row">
          <div className="flex min-w-0 flex-1 items-center gap-2">
            <span
              className="desktop-hud-dot desktop-hud-dot-live shrink-0"
              data-active={isActive ? 'true' : 'false'}
            />
            <span key={phase.activeWord} className="desktop-hud-phase-word desktop-hud-word-anim shrink-0">
              {phase.activeWord}
            </span>
            <span className="desktop-hud-phase-summary min-w-0 truncate">{phase.detail.summary}</span>
            {phase.detail.toolName ? (
              <span className="desktop-hud-phase-extra">· {phase.detail.toolName}</span>
            ) : null}
          </div>
          <div className="shrink-0">{metricsLine}</div>
        </div>
      </div>
    );
  }

  const shellClassName = isDesktop
    ? 'desktop-approval-panel mb-2 text-[12px]'
    : 'animate-in fade-in slide-in-from-bottom-2 ui-transition rounded-xl border border-white/10 bg-[#18181b] px-3.5 py-3 text-[13px] shadow-lg shadow-black/20 duration-200';

  const labelClass = isDesktop
    ? 'text-[12px] font-medium text-zinc-300'
    : 'text-[11px] uppercase tracking-[0.18em]';

  return (
    <div className={cn('desktop-thread-column flex-shrink-0', isDesktop ? 'px-0 pb-0' : 'px-4 pb-2')}>
      <div className={shellClassName} data-kind={isDesktop ? panelKind : undefined}>
        {agentState.pendingPlanApproval?.status === 'pending' ? (
          <div className="space-y-3">
            <div className={isDesktop ? 'desktop-hud-header' : 'flex flex-wrap items-start justify-between gap-3'}>
              <div className={isDesktop ? 'desktop-hud-header-title' : 'min-w-0 flex-1'}>
                <div className={isDesktop ? 'desktop-hud-header-title' : 'flex min-w-0 flex-wrap items-center gap-2'}>
                  <span className={isDesktop ? 'desktop-hud-dot' : 'h-2 w-2 rounded-full bg-violet-300/90'} data-kind={isDesktop ? 'plan' : undefined} />
                  <span className={isDesktop ? 'desktop-hud-label' : cn(labelClass, 'text-violet-200')} data-kind={isDesktop ? 'plan' : undefined}>
                    Plan
                  </span>
                  <span className={isDesktop ? 'desktop-hud-sep' : 'text-zinc-600'}>/</span>
                  <span className={isDesktop ? 'desktop-hud-subtitle truncate' : 'truncate text-[12px] text-zinc-100'}>
                    approval required
                  </span>
                </div>
                <div className={isDesktop ? 'desktop-hud-body' : 'mt-1.5 text-[11px] text-zinc-500'}>
                  Review the proposed plan. Reject keeps planning; approve starts implementation.
                </div>
              </div>
              <div className={isDesktop ? 'desktop-hud-waiting' : 'rounded-full border border-violet-500/24 bg-violet-500/[0.09] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-violet-100'}>
                waiting
              </div>
            </div>

            {agentState.pendingPlanApproval.markdown.includes('\n+++ ') ? (
              <UnifiedDiffView diff={agentState.pendingPlanApproval.markdown} />
            ) : (
              <div className={isDesktop ? 'desktop-hud-doc' : 'max-h-[min(58vh,42rem)] overflow-auto rounded-[1rem] border border-zinc-800/90 bg-zinc-950/92 px-4 py-3'}>
                <AnswerMarkdown content={agentState.pendingPlanApproval.markdown} />
              </div>
            )}

            {(agentState.pendingPlanApproval.plan_doc_path || agentState.planDoc?.file_path) ? (
              <div className={isDesktop ? 'desktop-hud-body flex items-center gap-2' : 'flex items-center gap-2 rounded-[0.75rem] border border-zinc-800/80 bg-zinc-950/60 px-3 py-2 text-[11px] text-zinc-400'}>
                <span>Plan file: {agentState.pendingPlanApproval.plan_doc_path || agentState.planDoc?.file_path}</span>
                <button
                  type="button"
                  onClick={copyPlanPath}
                  className={isDesktop ? 'desktop-hud-btn-secondary' : 'rounded-md border border-zinc-700 px-2 py-1 text-zinc-200 hover:border-zinc-500'}
                >
                  copy path
                </button>
              </div>
            ) : null}

            <textarea
              value={rejectFeedback}
              onChange={(event) => setRejectFeedback(event.target.value)}
              placeholder="Optional reject feedback"
              className={isDesktop ? 'desktop-hud-field' : 'min-h-16 w-full resize-none rounded-[1rem] border border-zinc-800/90 bg-zinc-950/80 px-3 py-2 text-[11px] leading-5 text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-violet-500/30'}
            />

            <div className={isDesktop ? 'desktop-hud-actions' : 'flex flex-wrap items-center gap-2 border-t border-white/10 pt-3'}>
              <button
                type="button"
                onClick={() => decidePlan('approve')}
                disabled={planDecision !== null}
                className={approveBtnClass}
              >
                {planDecision === 'approve' ? 'approving…' : 'approve'}
              </button>
              <button
                type="button"
                onClick={() => decidePlan('reject')}
                disabled={planDecision !== null}
                className={denyBtnClass}
              >
                {planDecision === 'reject' ? 'rejecting…' : 'reject'}
              </button>
              {!isDesktop ? <MetricPill label="mode" value="plan" caution /> : null}
              {!isDesktop ? (
                <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
              ) : (
                metricsLine
              )}
            </div>
          </div>
        ) : agentState.pendingUserInput ? (
          <div className="space-y-3">
            <div className={isDesktop ? 'desktop-hud-header-title' : 'flex flex-wrap items-center gap-2'}>
              <span className={isDesktop ? 'desktop-hud-dot' : 'h-2 w-2 rounded-full bg-violet-300/90'} data-kind={isDesktop ? 'plan' : undefined} />
              <span className={isDesktop ? 'desktop-hud-label' : cn(labelClass, 'text-violet-200')} data-kind={isDesktop ? 'plan' : undefined}>
                Input
              </span>
              <span className={isDesktop ? 'desktop-hud-sep' : 'text-zinc-600'}>/</span>
              <span className={isDesktop ? 'desktop-hud-subtitle' : 'text-[12px] text-zinc-100'}>planning question</span>
            </div>
            {agentState.pendingUserInput.questions.map((question) => (
              <div key={question.id} className={isDesktop ? 'desktop-hud-question' : 'rounded-[1rem] border border-zinc-800/90 bg-zinc-950/70 p-3'}>
                <div className={isDesktop ? 'desktop-hud-question-header' : 'text-[10px] uppercase tracking-[0.18em] text-zinc-500'}>
                  {question.header}
                </div>
                <div className={isDesktop ? 'desktop-hud-question-text' : 'mt-1 text-[12px] text-zinc-100'}>{question.question}</div>
                <div className={isDesktop ? 'desktop-hud-options' : 'mt-3 flex flex-wrap gap-2'}>
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
                      className={cn(
                        isDesktop
                          ? 'desktop-hud-option'
                          : cn(
                              'ui-transition rounded-full border px-3 py-1.5 text-left text-[11px] hover:border-violet-400/30 hover:text-white disabled:cursor-not-allowed disabled:border-zinc-800 disabled:bg-zinc-900 disabled:text-zinc-500',
                              userInputAnswers[question.id] === option.label
                                ? 'border-violet-400/40 bg-violet-500/18 text-white'
                                : 'border-violet-500/20 bg-violet-500/[0.08] text-violet-100'
                            )
                      )}
                      title={option.description}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            <div className={isDesktop ? 'desktop-hud-actions' : 'flex items-center gap-2 border-t border-white/10 pt-3'}>
              <button
                type="button"
                onClick={submitUserInput}
                disabled={
                  userInputSubmitting !== null
                  || agentState.pendingUserInput.questions.some((question) => !userInputAnswers[question.id])
                }
                className={approveBtnClass}
              >
                {userInputSubmitting ? 'sending…' : 'send'}
              </button>
              {!isDesktop ? <MetricPill label="mode" value="plan" caution /> : null}
            </div>
          </div>
        ) : pendingApproval ? (
          <div className="space-y-3">
            <div className={isDesktop ? 'desktop-hud-header' : 'flex flex-wrap items-start justify-between gap-3'}>
              <div className={isDesktop ? 'desktop-hud-header-title' : 'min-w-0 flex-1'}>
                <div className={isDesktop ? 'desktop-hud-header-title' : 'flex min-w-0 flex-wrap items-center gap-2'}>
                  <span className={isDesktop ? 'desktop-hud-dot' : 'h-2 w-2 rounded-full bg-amber-300/90'} data-kind={isDesktop ? 'permission' : undefined} />
                  <span className={isDesktop ? 'desktop-hud-label' : cn(labelClass, 'text-amber-200')} data-kind={isDesktop ? 'permission' : undefined}>
                    Permission
                  </span>
                  <span className={isDesktop ? 'desktop-hud-sep' : 'text-zinc-600'}>/</span>
                  <span className={isDesktop ? 'desktop-hud-subtitle truncate' : 'truncate text-[12px] text-zinc-100'}>
                    {pendingApproval.tool_name.replace(/_/g, ' ')}
                  </span>
                </div>
                <div className={isDesktop ? 'desktop-hud-meta' : 'mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-zinc-500'}>
                  {pendingApproval.permission_level ? (
                    <span className={isDesktop ? 'desktop-hud-level-chip' : 'rounded-full border border-amber-500/18 bg-amber-500/[0.08] px-2 py-0.5 uppercase tracking-[0.14em] text-amber-100'}>
                      {pendingApproval.permission_level}
                    </span>
                  ) : null}
                  {formatApprovalArguments(pendingApproval) ? (
                    <span className={isDesktop ? 'desktop-hud-meta-detail truncate' : 'truncate text-zinc-300'}>
                      {formatApprovalArguments(pendingApproval)}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className={isDesktop ? 'desktop-hud-waiting' : 'rounded-full border border-amber-500/24 bg-amber-500/[0.09] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-amber-100'} data-kind={isDesktop ? 'permission' : undefined}>
                waiting
              </div>
            </div>

            {typeof pendingApproval.diff_preview === 'string' && pendingApproval.diff_preview.trim() ? (
              pendingApproval.diff_preview.includes('\n+++ ') ? (
                <UnifiedDiffView diff={pendingApproval.diff_preview} compact />
              ) : (
                <pre className={isDesktop ? 'desktop-hud-pre desktop-hud-pre-compact' : 'max-h-48 overflow-auto rounded-[1rem] border border-zinc-800/90 bg-zinc-950/92 px-3 py-3 whitespace-pre-wrap text-[11px] leading-6 text-zinc-300'}>
                  {pendingApproval.diff_preview}
                </pre>
              )
            ) : null}

            <div className={isDesktop ? 'desktop-hud-actions' : 'flex flex-wrap items-center gap-2 border-t border-white/10 pt-3'}>
              <button
                type="button"
                onClick={() => decide('approve')}
                disabled={deciding !== null}
                className={approveBtnClass}
              >
                {deciding === 'approve' ? 'approving…' : 'approve'}
              </button>
              <button
                type="button"
                onClick={() => decide('deny')}
                disabled={deciding !== null}
                className={denyBtnClass}
              >
                {deciding === 'deny' ? 'denying…' : 'deny'}
              </button>
              {!isDesktop ? (
                <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
              ) : (
                metricsLine
              )}
            </div>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className={cn('h-2 w-2 rounded-full', phase.indicatorClassName, agentState.isActive && 'animate-pulse')} />
                  <span className={cn('text-[11px] uppercase tracking-[0.18em]', phase.accentClassName)}>
                    {phase.activeWord}
                  </span>
                  <span className="text-zinc-600">/</span>
                  <span className="truncate text-[12px] text-zinc-100">{phase.detail.summary}</span>
                </div>
                <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                  {phase.detail.target ? (
                    <span className="truncate text-zinc-300">{phase.detail.target}</span>
                  ) : null}
                  {phase.detail.toolName ? (
                    <span className="rounded-full border border-cyan-500/20 bg-cyan-500/[0.07] px-2 py-0.5 text-[11px] text-cyan-100">
                      {phase.detail.toolName}
                    </span>
                  ) : null}
                </div>
              </div>

              <div className="rounded-full border border-cyan-500/24 bg-cyan-500/[0.09] px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] text-cyan-100">
                live
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-white/10 pt-3">
              <MetricPill label="ctx" value={currentContextPct} caution={phase.isContextWarning} />
              <MetricPill label="compact" value={String(compactionCount)} caution={phase.isCompactionWarning} />
              <MetricPill label="elapsed" value={<ElapsedClock startedAt={startedAt} />} />
              {agentState.total_tokens ? (
                <MetricPill label="tok" value={formatAgentTokens(agentState.total_tokens)} />
              ) : null}
              {agentState.cost && agentState.usage?.total_tokens ? (
                <MetricPill label="est" value={formatAgentCost(agentState.cost.total_cost)} />
              ) : null}
            </div>
          </>
        )}
      </div>
    </div>
  );
});
