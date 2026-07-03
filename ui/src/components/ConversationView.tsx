// Conversation view - simple chat interface

import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from 'react';
import type { KeyboardEvent, ChangeEvent, ClipboardEvent, MouseEvent as ReactMouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { AgentRunMessage } from '@/components/AgentRunMessage';
import { ChatRunMessage } from '@/components/ChatRunMessage';
import { ImagePreviewStrip } from '@/components/ImagePreviewStrip';
import { MentionPicker, extractActiveMention } from '@/components/MentionPicker';
import { ModelPicker } from '@/components/ModelPicker';
import { ReasoningSettingsDialog } from '@/components/ReasoningSettingsDialog';
import { ScrollToBottom } from '@/components/ScrollToBottom';
import { WorkspacePickerDialog } from '@/components/WorkspacePickerDialog';
import { VirtualizedConversationRunList } from '@/components/VirtualizedConversationRunList';
import { DesktopChrome } from '@/components/desktop/DesktopChrome';
import { DesktopInputDock } from '@/components/desktop/DesktopInputDock';
import { DesktopComposerControls } from '@/components/desktop/DesktopComposerControls';
import { EmptyState } from '@/components/desktop/EmptyState';
import { AgentContextFooter } from '@/components/desktop/AgentComposerOptions';
import { isApplePlatform } from '@/lib/platform';
import { startWindowDrag } from '@/lib/windowDrag';
import {
  createConversation,
  patchConversation,
  createConversationRun,
  getConversation,
  abortRun,
  createAgentRun,
  cancelAgentRun,
  getAgentRunStatus,
  getModelStatus,
  getReasoningSettings,
  updateReasoningSettings,
  getUsage,
  steerAgentRun,
  searchWorkspaceFiles,
  listConversationRewindCheckpoints,
  rewindConversation,
  attachDraftTerminalSessions,
} from '@/api/client';
import type {
  ConversationRewindCheckpoint,
  ModelStatus,
  UsageInfo,
  WorkspaceFileEntry,
  ReasoningSettingsResponse,
  ReasoningSettings,
} from '@/api/client';
import type { ConversationModelSelection } from '@/types';
import {
  Dialog,
  DialogHeader,
  DialogTitle,
  DialogContent,
} from '@/components/ui/dialog';
import { DRAFT_TERMINAL_CONVERSATION_ID, useConversationRuns, useSelectedConversation, useStore, useHasActiveRun, useConversationTerminal } from '@/hooks/useStore';
import { openNativeWorkspacePicker } from '@/lib/platform';
import { formatContextTokens } from '@/lib/runFormat';
import { useSSE } from '@/hooks/useSSE';
import { useAgentSSE } from '@/hooks/useAgentSSE';
import { useAgentRunDetails } from '@/hooks/useAgentRunDetails';
import { formatAgentCost } from '@/lib/agentLiveState';
import { inputCostTotal, normalizeTokenUsage, outputCostTotal } from '@/lib/usageMetrics';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { Run, Conversation, ImageAttachment } from '@/types';

/** Maximum characters allowed in the input textarea (~2000 tokens) */
const MAX_INPUT_CHARS = 8000;
const MENTION_RESULT_LIMIT = 20;

const MAX_IMAGE_ATTACHMENTS = 20;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** Mode: 'chat' for regular conversation, 'agent' for agent */
type ChatMode = 'chat' | 'agent';

function getLineStart(text: string, position: number): number {
  return text.lastIndexOf('\n', Math.max(0, position) - 1) + 1;
}

function getLineEnd(text: string, position: number): number {
  const nextBreak = text.indexOf('\n', position);
  return nextBreak === -1 ? text.length : nextBreak;
}

function classifyWordCharacter(char: string): 'space' | 'word' | 'punctuation' {
  if (/\s/.test(char)) return 'space';
  if (/[A-Za-z0-9_]/.test(char)) return 'word';
  return 'punctuation';
}

function moveWordLeft(text: string, position: number): number {
  let nextPosition = position;
  while (nextPosition > 0 && /\s/.test(text[nextPosition - 1])) {
    nextPosition -= 1;
  }
  if (nextPosition === 0) return 0;
  const kind = classifyWordCharacter(text[nextPosition - 1]);
  while (nextPosition > 0 && classifyWordCharacter(text[nextPosition - 1]) === kind) {
    nextPosition -= 1;
  }
  return nextPosition;
}

function moveWordRight(text: string, position: number): number {
  let nextPosition = position;
  while (nextPosition < text.length && /\s/.test(text[nextPosition])) {
    nextPosition += 1;
  }
  if (nextPosition >= text.length) return text.length;
  const kind = classifyWordCharacter(text[nextPosition]);
  while (nextPosition < text.length && classifyWordCharacter(text[nextPosition]) === kind) {
    nextPosition += 1;
  }
  return nextPosition;
}

function moveVertical(text: string, position: number, direction: -1 | 1, preferredColumn?: number | null): number {
  const currentLineStart = getLineStart(text, position);
  const currentColumn = preferredColumn ?? (position - currentLineStart);
  if (direction < 0) {
    if (currentLineStart === 0) return 0;
    const previousLineEnd = currentLineStart - 1;
    const previousLineStart = getLineStart(text, previousLineEnd);
    return Math.min(previousLineStart + currentColumn, previousLineEnd);
  }

  const currentLineEnd = getLineEnd(text, position);
  if (currentLineEnd >= text.length) return text.length;
  const nextLineStart = currentLineEnd + 1;
  const nextLineEnd = getLineEnd(text, nextLineStart);
  return Math.min(nextLineStart + currentColumn, nextLineEnd);
}

function hasTextSelection(textarea: HTMLTextAreaElement): boolean {
  return textarea.selectionStart !== textarea.selectionEnd;
}

function replaceTextareaRange(
  textarea: HTMLTextAreaElement,
  replacement: string,
  start: number,
  end: number,
  selectMode: SelectionMode = 'end',
): void {
  const scrollTop = textarea.scrollTop;
  const scrollLeft = textarea.scrollLeft;
  textarea.setRangeText(replacement, start, end, selectMode);
  textarea.scrollTop = scrollTop;
  textarea.scrollLeft = scrollLeft;
}

function isTextInputElement(element: EventTarget | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  const tagName = element.tagName.toLowerCase();
  if (tagName === 'input' || tagName === 'textarea' || tagName === 'select') {
    return true;
  }
  if (element.isContentEditable) {
    return true;
  }
  return !!element.closest('[contenteditable="true"], [role="textbox"]');
}

const CONVERSATION_MODEL_METADATA_KEY = 'model_selection';

function getConversationModelSelection(conversation?: Conversation | null): ConversationModelSelection | null {
  const value = conversation?.metadata?.[CONVERSATION_MODEL_METADATA_KEY];
  if (!value || typeof value !== 'object') return null;
  const selection = value as Partial<ConversationModelSelection>;
  if (!selection.provider || !selection.model_id || !selection.display_name) return null;
  return selection as ConversationModelSelection;
}

function modelStatusFromSelection(
  selection: ConversationModelSelection,
  previous: ModelStatus | null,
): ModelStatus {
  return {
    provider: selection.provider,
    model_name: selection.display_name,
    base_url: previous?.provider === selection.provider ? previous.base_url : null,
    local_running: selection.provider === 'local' ? (previous?.local_running ?? false) : false,
    context_window: Number(selection.context_window || previous?.context_window || 0),
    max_output_tokens: Number(selection.max_output_tokens || previous?.max_output_tokens || 0),
    effective_input_budget: Number(selection.effective_input_budget || previous?.effective_input_budget || 0),
    supports_tools: selection.supports_tools ?? previous?.supports_tools ?? true,
    supports_reasoning: selection.supports_reasoning ?? previous?.supports_reasoning ?? false,
    supports_vision: selection.supports_vision ?? previous?.supports_vision ?? false,
    provider_family: selection.provider,
    reasoning_capabilities: previous?.provider === selection.provider ? previous.reasoning_capabilities : null,
    source: selection.source || 'registry',
  };
}

const missingConversationIds = new Set<string>();

export function markConversationMissing(conversationId: string) {
  missingConversationIds.add(conversationId);
}

export function isConversationMissing(conversationId: string): boolean {
  return missingConversationIds.has(conversationId);
}

function conversationTitleFromMessage(message: string, maxLen = 64): string {
  const cleaned = message.trim().replace(/\s+/g, ' ');
  if (!cleaned) return 'New conversation';

  let normalized = cleaned.toLowerCase();
  const fillerPatterns = [
    /^(?:hey|hi|hello|yo|yoo|yup|okay|ok|alright|please)\s+/,
    /^(?:can|could|would|will)\s+you\s+/,
    /^i\s+need\s+you\s+to\s+/,
    /^help\s+me\s+(?:with\s+)?/,
  ];
  for (const pattern of fillerPatterns) {
    normalized = normalized.replace(pattern, '');
  }
  normalized = normalized.replace(/^[ .!?,;:-]+|[ .!?,;:-]+$/g, '');

  const issuePhrase = (value: string) => {
    let next = value.replace(/\bstill\b\s*/g, '').trim();
    next = next.replace(/\b(?:look|looks|feel|feels)\s+/, '');
    if (/\bcramped\b/.test(next)) {
      next = next.replace(/\bcramped\b/, 'too cramped');
    }
    return next;
  };

  const smartTitleFromNormalized = (value: string): string => {
    const patterns: Array<[RegExp, string]> = [
      [/^(?:explain\s+why|why\s+(?:is|are|does|do|did))\s+/, 'Issue: '],
      [/^how\s+(?:do|can|should|would)\s+i\s+/, 'How to '],
      [/^how\s+to\s+/, 'How to '],
      [/^what\s+(?:is|are)\s+/, 'About '],
      [/^explain\s+/, 'About '],
      [/^tell\s+me\s+(?:about\s+)?/, 'About '],
    ];
    for (const [pattern, prefix] of patterns) {
      const match = value.match(pattern);
      if (!match) continue;
      const body = value.slice(match[0].length).trim();
      if (!body) break;
      const content = prefix === 'Issue: ' ? issuePhrase(body) : body;
      return `${prefix}${content ? `${content[0].toUpperCase()}${content.slice(1)}` : content}`;
    }
    return value;
  };

  const smart = smartTitleFromNormalized(normalized) || cleaned;
  const title = smart.replace(/^[ .!?,;:-]+|[ .!?,;:-]+$/g, '');
  const sentenceCased = title ? `${title[0].toUpperCase()}${title.slice(1)}` : 'New conversation';
  if (sentenceCased.length <= maxLen) {
    return sentenceCased;
  }
  return `${sentenceCased.slice(0, maxLen - 3).trim()}...`;
}

export function ConversationView() {
  const navigate = useNavigate();
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  const selectConversation = useStore((s) => s.selectConversation);
  const setRuns = useStore((s) => s.setRuns);
  const updateConversation = useStore((s) => s.updateConversation);
  const addConversation = useStore((s) => s.addConversation);
  const addRun = useStore((s) => s.addRun);
  const updateRun = useStore((s) => s.updateRun);
  const removeRun = useStore((s) => s.removeRun);
  const clearAgentRun = useStore((s) => s.clearAgentRun);
  const setEvents = useStore((s) => s.setEvents);
  const conversation = useSelectedConversation();
  const runs = useConversationRuns(selectedConversationId);
  const terminalState = useConversationTerminal(selectedConversationId);
  const draftTerminalState = useConversationTerminal(DRAFT_TERMINAL_CONVERSATION_ID);
  const initTerminalState = useStore((s) => s.initTerminalState);
  const hasActiveRun = useHasActiveRun();
  const setConversationMode = useStore((s) => s.setConversationMode);
  const updateTerminalState = useStore((s) => s.updateTerminalState);
  const setDesktopOverlayOpen = useStore((s) => s.setDesktopOverlayOpen);
  const draftWorkspacePath = useStore((s) => s.draftWorkspacePath);
  const draftConversationNonce = useStore((s) => s.draftConversationNonce);
  const setDraftWorkspacePath = useStore((s) => s.setDraftWorkspacePath);
  const rememberWorkspacePath = useStore((s) => s.rememberWorkspacePath);
  const beginWorkspaceDraft = useStore((s) => s.beginWorkspaceDraft);
  const [message, setMessage] = useState('');
  const [imageAttachments, setImageAttachments] = useState<ImageAttachment[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [mode, setMode] = useState<ChatMode>('agent');
  const [workspacePickerOpen, setWorkspacePickerOpen] = useState(false);
  const [mentionResults, setMentionResults] = useState<WorkspaceFileEntry[]>([]);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [mentionError, setMentionError] = useState<string | null>(null);
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0);
  const [activeMention, setActiveMention] = useState<{ start: number; end: number; query: string } | null>(null);
  const [permissionPolicy, setPermissionPolicy] = useState<'strict' | 'relaxed' | 'yolo'>(
    () => (localStorage.getItem('reasoner_permission_policy') as 'strict' | 'relaxed' | 'yolo') || 'strict'
  );
  const [collaborationMode, setCollaborationMode] = useState<'default' | 'plan'>(
    () => (localStorage.getItem('reasoner_collaboration_mode') as 'default' | 'plan') || 'default'
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const verticalMoveColumnRef = useRef<number | null>(null);
  const composerFocusRafRef = useRef<number | null>(null);
  const bottomScrollRafRef = useRef<number | null>(null);
  const pendingWorkspaceShortcutRef = useRef<'workspace-new' | 'workspace-picker' | null>(null);
  const pendingWorkspaceShortcutTimeoutRef = useRef<number | null>(null);
  const lastEscapeAtRef = useRef(0);

  // Model picker state
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [draftModelSelection, setDraftModelSelection] = useState<ConversationModelSelection | null>(null);
  const defaultModelStatusRef = useRef<ModelStatus | null>(null);
  const [reasoningSettingsOpen, setReasoningSettingsOpen] = useState(false);
  const [reasoningSettings, setReasoningSettings] = useState<ReasoningSettingsResponse | null>(null);
  const [reasoningDraft, setReasoningDraft] = useState<ReasoningSettings | null>(null);
  const [reasoningSaving, setReasoningSaving] = useState(false);

  // Usage limits state
  const [usage, setUsage] = useState<UsageInfo>({ limit: -1, used: 0, remaining: -1 });
  const hasLimit = usage.limit > 0;
  const atLimit = hasLimit && usage.remaining <= 0;

  const refreshUsage = useCallback(() => {
    getUsage().then(setUsage).catch(() => {});
  }, []);

  const refreshReasoningSettings = useCallback(() => {
    getReasoningSettings()
      .then((data) => {
        setReasoningSettings(data);
        setReasoningDraft(data.settings);
      })
      .catch(() => {});
  }, []);

  const clearMentionState = useCallback(() => {
    setActiveMention(null);
    setMentionOpen(false);
    setMentionLoading(false);
    setMentionError(null);
    setMentionResults([]);
    setMentionSelectedIndex(0);
  }, []);

  useEffect(() => {
    if (selectedConversationId) return;
    setMessage('');
    setImageAttachments([]);
    clearMentionState();
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  }, [clearMentionState, draftConversationNonce, selectedConversationId]);

  useEffect(() => {
    localStorage.setItem('reasoner_permission_policy', permissionPolicy);
  }, [permissionPolicy]);

  useEffect(() => {
    localStorage.setItem('reasoner_collaboration_mode', collaborationMode);
  }, [collaborationMode]);

  useEffect(() => {
    const conversationId = conversation?.conversation_id;
    const workspacePath = conversation?.workspace_path?.trim();
    if (!conversationId || !workspacePath) return;

    // This effect is only allowed to mirror the workspace for the conversation
    // that is still selected *at effect time*. Passive effects from the previous
    // conversation can otherwise run after New Workspace clears the selection and
    // overwrite the just-picked draft workspace with the old conversation folder.
    if (useStore.getState().selectedConversationId !== conversationId) return;

    setDraftWorkspacePath(workspacePath);
  }, [conversation?.conversation_id, conversation?.workspace_path, setDraftWorkspacePath]);

  useEffect(() => {
    if (!selectedConversationId) {
      return;
    }

    let savedState: Partial<{
      isOpen: boolean;
      dock: 'bottom' | 'right';
      height: number;
      width: number;
    }> = {};

    try {
      savedState = JSON.parse(localStorage.getItem(`reasoner_terminal_state:${selectedConversationId}`) || '{}');
    } catch {
      savedState = {};
    }

    const existingState = useStore.getState().terminalByConversation[selectedConversationId];
    initTerminalState(selectedConversationId, {
      isOpen: existingState?.isOpen ?? savedState.isOpen ?? false,
      dock: 'right',
      height: Number(existingState?.height || savedState.height || 260),
      width: Number(existingState?.width || savedState.width || 420),
    });
  }, [initTerminalState, selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId || !terminalState) {
      return;
    }

    localStorage.setItem(
      `reasoner_terminal_state:${selectedConversationId}`,
      JSON.stringify({
        isOpen: terminalState.isOpen,
        dock: terminalState.dock,
        height: terminalState.height,
        width: terminalState.width,
      })
    );
  }, [selectedConversationId, terminalState]);

  useEffect(() => {
    setConversationMode(mode);
  }, [mode, setConversationMode]);

  // Fetch model status and usage on mount
  useEffect(() => {
    getModelStatus().then((status) => {
      if (!defaultModelStatusRef.current) defaultModelStatusRef.current = status;
      setModelStatus(status);
    }).catch(() => {});
    refreshUsage();
    refreshReasoningSettings();
  }, [refreshUsage, refreshReasoningSettings]);

  useEffect(() => {
    const selection = getConversationModelSelection(conversation);
    if (selection) {
      setModelStatus((current) => modelStatusFromSelection(selection, current));
      return;
    }
    if (!selectedConversationId && draftModelSelection) {
      setModelStatus((current) => modelStatusFromSelection(draftModelSelection, current));
      return;
    }
    if (defaultModelStatusRef.current) {
      setModelStatus(defaultModelStatusRef.current);
      return;
    }
    void getModelStatus().then((status) => {
      if (!defaultModelStatusRef.current) defaultModelStatusRef.current = status;
      setModelStatus(status);
    }).catch(() => {});
  }, [conversation?.conversation_id, conversation?.metadata, draftModelSelection, selectedConversationId]);

  useEffect(() => {
    if (!modelStatus) return;
    refreshReasoningSettings();
  }, [modelStatus?.provider, modelStatus?.model_name, refreshReasoningSettings]);

  // Stop generation state
  const [pendingMessage, setPendingMessage] = useState('');
  // Track run IDs we already subscribed to in handleSubmit, so
  // loadConversation doesn't open a second EventSource for the same run.
  const subscribedRunRef = useRef<string | null>(null);
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [pendingIsAgent, setPendingIsAgent] = useState(false);
  const [stoppingRunId, setStoppingRunId] = useState<string | null>(null);
  const [queuedSteers, setQueuedSteers] = useState<string[]>([]);
  const [rewindOpen, setRewindOpen] = useState(false);
  const [rewindLoading, setRewindLoading] = useState(false);
  const [rewindSubmitting, setRewindSubmitting] = useState(false);
  const [rewindCheckpoints, setRewindCheckpoints] = useState<ConversationRewindCheckpoint[]>([]);
  const [rewindSelectedRunId, setRewindSelectedRunId] = useState<string | null>(null);
  const rewindLoadInFlightRef = useRef(false);
  const rewindRestoreInFlightRef = useRef(false);

  // Track any active run (chat or agent) for UI purposes (auto-scroll, completion detection)
  const activeRun = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running') {
        return runs[i];
      }
    }
    return null;
  }, [runs]);
  const activeRunId = activeRun?.run_id ?? null;
  const activeAgentRun = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running' && runs[i].mode === 'agent') {
        return runs[i];
      }
    }
    return null;
  }, [runs]);
  const activeAgentHudState = useAgentRunDetails(activeAgentRun?.run_id ?? null, !!activeAgentRun);
  const activeModelSelection = getConversationModelSelection(conversation) || draftModelSelection;

  // Clear queued steers when agent confirms injection via SSE.
  // Delay the clear so the chip is visible briefly before disappearing.
  const activeAgentState = useStore((s) => activeRunId ? s.agentRunState[activeRunId] : undefined);
  const latestContextRun = useMemo(
    () => [...runs].reverse().find((run) => (
      run.mode === 'agent'
      || !!run.context_usage
      || !!run.context_profile
      || !!run.stored_context
    )),
    [runs],
  );
  const lockedWorkspacePath = (conversation?.workspace_path || '').trim();
  const hasConversationWorkspace = lockedWorkspacePath.length > 0;
  const isWorkspaceLocked = selectedConversationId !== null && !!conversation;
  const effectiveWorkspacePath = isWorkspaceLocked ? lockedWorkspacePath : draftWorkspacePath.trim();
  const anyDialogOpen = (
    workspacePickerOpen
    || modelPickerOpen
    || reasoningSettingsOpen
    || rewindOpen
  );
  useEffect(() => {
    setDesktopOverlayOpen(anyDialogOpen);
    return () => setDesktopOverlayOpen(false);
  }, [anyDialogOpen, setDesktopOverlayOpen]);
  const latestRunContextUsage = latestContextRun?.context_usage;
  const footerContextUsage = useMemo(() => (
    activeAgentState?.context_usage
    ?? latestRunContextUsage
    ?? undefined
  ), [activeAgentState?.context_usage, latestRunContextUsage]);
  const conversationTokenAndCostTotals = useMemo(() => {
    return runs.reduce(
      (totals, run) => {
        const usage = normalizeTokenUsage(
          run.run_id === activeRunId && activeAgentState?.usage
            ? activeAgentState.usage
            : run.usage
        );
        const cost = run.run_id === activeRunId && activeAgentState?.cost
          ? activeAgentState.cost
          : run.cost;

        totals.inputTokens += usage?.input_tokens ?? 0;
        totals.outputTokens += usage?.output_tokens ?? 0;
        totals.inputCost += inputCostTotal(cost);
        totals.outputCost += outputCostTotal(cost);
        return totals;
      },
      { inputTokens: 0, outputTokens: 0, inputCost: 0, outputCost: 0 },
    );
  }, [runs, activeRunId, activeAgentState?.usage, activeAgentState?.cost]);
  const composerContextWindow = (
    activeAgentState?.context_profile?.context_window
    ?? modelStatus?.context_window
    ?? (latestContextRun?.context_profile as { context_window?: number } | undefined)?.context_window
    ?? footerContextUsage?.context_window
  );
  const composerPromptTokens = footerContextUsage?.prompt_tokens_current_call;
  const composerContextUtilizationPct = (
    typeof composerPromptTokens === 'number'
    && typeof composerContextWindow === 'number'
    && composerContextWindow > 0
      ? (composerPromptTokens / composerContextWindow) * 100
      : null
  );
  const showComposerContextStats = mode === 'agent' && !!composerContextWindow && (
    !!footerContextUsage
    || conversationTokenAndCostTotals.inputTokens + conversationTokenAndCostTotals.outputTokens > 0
    || conversationTokenAndCostTotals.inputCost + conversationTokenAndCostTotals.outputCost > 0
  );
  const injectedSteerCount = activeAgentState?.injectedSteers?.length ?? 0;

  const openRewindPicker = useCallback(async () => {
    if (
      !selectedConversationId
      || hasActiveRun
      || !lockedWorkspacePath
      || rewindLoadInFlightRef.current
      || rewindRestoreInFlightRef.current
    ) {
      return;
    }
    rewindLoadInFlightRef.current = true;
    setRewindLoading(true);
    setRewindSubmitting(false);
    setRewindOpen(true);
    try {
      const response = await listConversationRewindCheckpoints(selectedConversationId);
      setRewindCheckpoints(response.checkpoints);
      setRewindSelectedRunId(response.checkpoints[0]?.run_id ?? null);
    } catch {
      setRewindOpen(false);
      toast.error('Failed to load rewind history');
    } finally {
      setRewindLoading(false);
      rewindLoadInFlightRef.current = false;
    }
  }, [hasActiveRun, lockedWorkspacePath, selectedConversationId]);

  const handleRewindRestore = useCallback(async () => {
    if (
      !selectedConversationId
      || !rewindSelectedRunId
      || rewindSubmitting
      || rewindRestoreInFlightRef.current
    ) {
      return;
    }
    rewindRestoreInFlightRef.current = true;
    setRewindSubmitting(true);
    try {
      const response = await rewindConversation(selectedConversationId, {
        run_id: rewindSelectedRunId,
      });
      for (const rewoundRunId of response.rewound_run_ids) {
        clearAgentRun(rewoundRunId);
        removeRun(rewoundRunId);
      }
      updateConversation(selectedConversationId, response.conversation);
      setRuns(selectedConversationId, response.runs);
      setMessage(response.restored_prompt);
      setImageAttachments([]);
      clearMentionState();
      setQueuedSteers([]);
      setRewindOpen(false);
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea || textarea.disabled) return;
        textarea.focus();
        const end = textarea.value.length;
        textarea.setSelectionRange(end, end);
      });
    } catch (error: unknown) {
      const message = (error as { message?: string })?.message || 'Failed to rewind conversation';
      toast.error(message);
    } finally {
      setRewindSubmitting(false);
      rewindRestoreInFlightRef.current = false;
    }
  }, [
    clearAgentRun,
    clearMentionState,
    removeRun,
    rewindSelectedRunId,
    rewindSubmitting,
    selectedConversationId,
    setRuns,
    updateConversation,
  ]);

  const handleRewindOpenChange = useCallback((open: boolean) => {
    setRewindOpen(open);
    if (!open && !rewindRestoreInFlightRef.current) {
      rewindLoadInFlightRef.current = false;
      setRewindLoading(false);
      setRewindCheckpoints([]);
      setRewindSelectedRunId(null);
      lastEscapeAtRef.current = 0;
    }
  }, []);

  useEffect(() => {
    rewindLoadInFlightRef.current = false;
    rewindRestoreInFlightRef.current = false;
    setRewindOpen(false);
    setRewindLoading(false);
    setRewindSubmitting(false);
    setRewindCheckpoints([]);
    setRewindSelectedRunId(null);
    lastEscapeAtRef.current = 0;
  }, [selectedConversationId]);
  useEffect(() => {
    if (injectedSteerCount > 0 && queuedSteers.length > 0) {
      const timer = setTimeout(() => setQueuedSteers([]), 1500);
      return () => clearTimeout(timer);
    }
  }, [injectedSteerCount, queuedSteers.length]);

  // Only track chat (non-agent) runs for useSSE auto-subscribe.
  // Agent runs are managed manually via useAgentSSE.
  const activeChatRunId = useMemo(() => {
    for (let i = runs.length - 1; i >= 0; i -= 1) {
      if (runs[i].status === 'running' && runs[i].mode !== 'agent') {
        return runs[i].run_id;
      }
    }
    return null;
  }, [runs]);

  // Get subscribe/unsubscribe functions from useSSE (chat mode)
  const { subscribe, unsubscribe } = useSSE(activeChatRunId);

  // Get subscribe/unsubscribe functions from useAgentSSE (agent mode)
  const { subscribe: subscribeAgent } = useAgentSSE(null); // Manual subscription, not auto

  const scrollConversationToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, []);

  const scheduleConversationBottomScroll = useCallback((frames = 18) => {
    if (typeof window === 'undefined') return;
    if (bottomScrollRafRef.current !== null) {
      window.cancelAnimationFrame(bottomScrollRafRef.current);
      bottomScrollRafRef.current = null;
    }

    let framesRemaining = frames;
    const tick = () => {
      scrollConversationToBottom();
      framesRemaining -= 1;
      if (framesRemaining > 0) {
        bottomScrollRafRef.current = window.requestAnimationFrame(tick);
      } else {
        bottomScrollRafRef.current = null;
      }
    };

    bottomScrollRafRef.current = window.requestAnimationFrame(tick);
  }, [scrollConversationToBottom]);

  useEffect(() => () => {
    if (bottomScrollRafRef.current !== null) {
      window.cancelAnimationFrame(bottomScrollRafRef.current);
      bottomScrollRafRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!selectedConversationId) {
      setLoadingConversationId(null);
      return;
    }

    setLoadingConversationId(selectedConversationId);
    let cancelled = false;

    async function loadConversation() {
      try {
        const data = await getConversation(selectedConversationId!);
        if (cancelled) return;
        updateConversation(selectedConversationId!, data.conversation);
        setRuns(selectedConversationId!, data.runs);

        // Auto-reconnect to any active runs after page reload.
        // Skip if we already subscribed in handleSubmit (prevents double EventSource).
        for (const run of data.runs) {
          if (run.status === 'running') {
            if (run.mode === 'agent') {
              if (subscribedRunRef.current === run.run_id) {
                // Already subscribed from handleSubmit — don't open a second connection
                continue;
              }
              // Reconnect to agent SSE stream with stored token (e.g. after page reload)
              const streamToken = localStorage.getItem(`stream_token:${run.run_id}`) || undefined;
              subscribeAgent(run.run_id, 0, streamToken);
            } else {
              // Reconnect to chat SSE stream
              subscribe(run.run_id);
            }
          }
        }
      } catch (error: unknown) {
        if (cancelled) return;
        // Conversation might not exist anymore after deletes or stale URLs.
        // Clear the stale selected id so draft workspace state keeps working,
        // including @ file mentions in the composer.
        console.error('Failed to load conversation:', error);
        if ((error as { status?: number })?.status === 404) {
          markConversationMissing(selectedConversationId!);
          selectConversation(null);
          setRuns(selectedConversationId!, []);
          navigate('/conversations', { replace: true });
        }
      } finally {
        if (!cancelled) {
          setLoadingConversationId((current) => (
            current === selectedConversationId ? null : current
          ));
        }
      }
    }

    loadConversation();
    return () => {
      cancelled = true;
    };
  }, [navigate, selectConversation, selectedConversationId, setRuns, updateConversation, subscribe, subscribeAgent]);

  const runListKey = useMemo(
    () => runs.map((run) => run.run_id).join('|'),
    [runs],
  );
  const isLoadingSelectedConversation = loadingConversationId === selectedConversationId;

  // Opening a conversation should land on the latest exchange. For long chats
  // the virtualized list first renders from estimated row heights, then corrects
  // height measurements over the next few frames; keep pinning to bottom during
  // that initial measurement window so the scrollbar does not settle mid-thread.
  useLayoutEffect(() => {
    scheduleConversationBottomScroll();
  }, [runListKey, scheduleConversationBottomScroll, selectedConversationId]);

  // Auto-scroll during streaming - watch streaming text length for active run
  const lastStreamLen = useStore((s) => {
    if (!activeRunId) return 0;
    const text = s.streamingText[activeRunId] ?? '';
    const thinking = s.streamingThinking[activeRunId] ?? '';
    return text.length + thinking.length;
  });
  const activeAgentScrollSignal = useStore((s) => {
    if (!activeRunId) return '';
    const agentState = s.agentRunState[activeRunId];
    if (!agentState) return '';
    return [
      agentState.currentStep,
      agentState.steps.length,
      agentState.toolCalls.length,
      agentState.thinkingBuffer.length,
      agentState.answerBuffer.length,
      agentState.agentState,
    ].join(':');
  });

  useEffect(() => {
    if (!scrollRef.current || !activeRunId || !activeAgentRun) return;
    const el = scrollRef.current;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [activeAgentScrollSignal, activeRunId, activeAgentRun]);

  useEffect(() => {
    if (!scrollRef.current || !activeRunId || activeAgentRun) return;
    const el = scrollRef.current;
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 150;
    if (isNearBottom) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [lastStreamLen, activeRunId, activeAgentRun]);

  const focusComposer = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea || textarea.disabled) return;
    textarea.focus();
    const end = textarea.value.length;
    textarea.setSelectionRange(end, end);
  }, []);

  const scheduleComposerFocus = useCallback(() => {
    if (composerFocusRafRef.current !== null) {
      cancelAnimationFrame(composerFocusRafRef.current);
    }
    composerFocusRafRef.current = requestAnimationFrame(() => {
      composerFocusRafRef.current = requestAnimationFrame(() => {
        focusComposer();
        composerFocusRafRef.current = null;
      });
    });
  }, [focusComposer]);

  /** Retry a message: pre-fill the input with the original user message */
  const handleRetry = useCallback((userMessage: string) => {
    if (hasActiveRun) return;
    clearMentionState();
    setMessage(userMessage);
    requestAnimationFrame(focusComposer);
  }, [clearMentionState, focusComposer, hasActiveRun]);

  const renderRunCard = useCallback((run: Run) => (
    run.mode === 'agent' ? (
      <AgentRunMessage
        key={run.run_id}
        run={run}
        onRetry={handleRetry}
        canRetry={!hasActiveRun}
      />
    ) : (
      <ChatRunMessage
        key={run.run_id}
        run={run}
        onRetry={handleRetry}
        canRetry={!hasActiveRun}
      />
    )
  ), [handleRetry, hasActiveRun]);

  const handleSaveReasoningSettings = useCallback(async () => {
    if (!reasoningDraft) return;
    setReasoningSaving(true);
    try {
      const updated = await updateReasoningSettings(reasoningDraft);
      setReasoningSettings(updated);
      setReasoningDraft(updated.settings);
      setReasoningSettingsOpen(false);
      const status = await getModelStatus();
      setModelStatus(status);
      toast.success('Reasoning settings updated');
    } catch (error: unknown) {
      const message = (error as { message?: string })?.message || 'Failed to update reasoning settings';
      toast.error(message);
    } finally {
      setReasoningSaving(false);
    }
  }, [reasoningDraft]);

  const handleModelStatusChange = useCallback((status: ModelStatus, selection?: ConversationModelSelection | null) => {
    setModelStatus(status);
    if (!selection) return;
    if (!selectedConversationId) {
      setDraftModelSelection(selection);
      return;
    }
    const nextMetadata = {
      ...(conversation?.metadata || {}),
      [CONVERSATION_MODEL_METADATA_KEY]: selection,
    };
    setDraftModelSelection(null);
    updateConversation(selectedConversationId, { metadata: nextMetadata });
    void patchConversation(selectedConversationId, {
      metadata: { [CONVERSATION_MODEL_METADATA_KEY]: selection },
    }).catch(() => {
      toast.error('Failed to save conversation model');
    });
  }, [conversation?.metadata, selectedConversationId, updateConversation]);

  const handleOpenWorkspacePicker = useCallback(async () => {
    if (isWorkspaceLocked) {
      toast.error(
        hasConversationWorkspace
          ? 'This conversation is already bound to its workspace'
          : 'This conversation has no workspace. Create a new workspace thread from the sidebar.'
      );
      return;
    }
    const selectedPath = await openNativeWorkspacePicker();
    if (selectedPath) {
      rememberWorkspacePath(selectedPath);
      setDraftWorkspacePath(selectedPath);
    }
  }, [
    hasConversationWorkspace,
    isWorkspaceLocked,
    rememberWorkspacePath,
    setDraftWorkspacePath,
  ]);

  const handleSubmit = async () => {
    if ((!message.trim() && imageAttachments.length === 0) || isSubmitting) return;
    if (imageAttachments.length > 0 && !modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }

    // If an agent run is active, steer it instead of creating a new run
    if (canSteerActiveRun && activeRunId) {
      if (imageAttachments.length > 0) {
        toast.error('Image paste is only available before starting a run.');
        return;
      }
      const steerMsg = message.trim();
      console.log(`[Steer] Attempting to steer run ${activeRunId}, message: "${steerMsg.substring(0, 50)}..."`);
      setMessage('');
      clearMentionState();
      try {
        await steerAgentRun(activeRunId, steerMsg);
        setQueuedSteers((prev) => [...prev, steerMsg]);
        scheduleComposerFocus();
      } catch (error: unknown) {
        console.error('Steer API failed:', error);
        const errMsg = error instanceof Error ? error.message : String(error);
        const apiError = error as { status?: number; message?: string };
        toast.error(`Steer failed: ${apiError.status || 'N/A'} - ${errMsg}`);
        setMessage(steerMsg);
        scheduleComposerFocus();
      }
      return;
    }

    if (hasActiveRun) return; // Non-agent active run, block

    let conversationId = selectedConversationId;

    if (!conversationId && !effectiveWorkspacePath) {
      toast.error('Choose a workspace first');
      setWorkspacePickerOpen(true);
      return;
    }

    const attachmentsToSend = imageAttachments.map(({ name, mime_type, data_url }) => ({
      name,
      mime_type,
      data_url,
    }));
    const messageToSend = message.trim() || 'Please analyze the attached image.';
    setIsSubmitting(true);
    setPendingMessage(messageToSend);
    setMessage('');
    setImageAttachments([]);
    clearMentionState();
    setPendingIsAgent(mode === 'agent');

    // Track whether we need to navigate after setup (deferred to prevent
    // useEffect from re-subscribing while handleSubmit is still in flight)
    let needsNavigate = false;

    try {
      // Create conversation if needed
      if (!conversationId) {
        const response = await createConversation({
          workspace_path: effectiveWorkspacePath,
          metadata: activeModelSelection
            ? { [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : undefined,
        });
        conversationId = response.conversation_id;
        rememberWorkspacePath(effectiveWorkspacePath);
        const newConversation: Conversation = {
          conversation_id: conversationId,
          created_at: new Date().toISOString(),
          title: conversationTitleFromMessage(messageToSend),
          summary: '',
          workspace_path: effectiveWorkspacePath,
          status: 'active',
          metadata: activeModelSelection
            ? { [CONVERSATION_MODEL_METADATA_KEY]: activeModelSelection }
            : {},
        };
        addConversation(newConversation);
        setRuns(conversationId, []);
        if (draftTerminalState?.isOpen) {
          let attachedSessions = draftTerminalState.sessions ?? [];
          try {
            const attached = await attachDraftTerminalSessions(conversationId, {
              workspace_path: effectiveWorkspacePath,
            });
            attachedSessions = attached.sessions;
          } catch {
            toast.error('Draft terminal could not attach to the new conversation');
          }
          const bufferBySessionId = Object.fromEntries(
            attachedSessions.map((session) => [
              session.session_id,
              session.replay_buffer || draftTerminalState.bufferBySessionId[session.session_id] || '',
            ]),
          );
          const activeSessionId = attachedSessions.find(
            (item) => item.session_id === draftTerminalState.activeSessionId
          )?.session_id ?? attachedSessions[0]?.session_id ?? null;
          const activeSession = activeSessionId
            ? attachedSessions.find((item) => item.session_id === activeSessionId) ?? null
            : null;
          initTerminalState(conversationId, {
            isOpen: true,
            dock: draftTerminalState.dock,
            width: draftTerminalState.width,
            height: draftTerminalState.height,
            activeToolTabId: draftTerminalState.activeToolTabId,
            browserTabs: draftTerminalState.browserTabs,
            sessions: attachedSessions,
            activeSessionId,
            session: activeSession,
            bufferBySessionId,
            buffer: activeSessionId ? (bufferBySessionId[activeSessionId] ?? '') : '',
            connected: false,
            status: attachedSessions.length > 0 ? 'running' : 'idle',
          });
          localStorage.setItem(
            `reasoner_terminal_state:${conversationId}`,
            JSON.stringify({
              isOpen: true,
              dock: draftTerminalState.dock,
              height: draftTerminalState.height,
              width: draftTerminalState.width,
            })
          );
          selectConversation(conversationId);
          updateTerminalState(DRAFT_TERMINAL_CONVERSATION_ID, {
            isOpen: false,
            sessions: [],
            activeSessionId: null,
            activeToolTabId: null,
            browserTabs: [],
            session: null,
            buffer: '',
            bufferBySessionId: {},
            connected: false,
            status: 'idle',
          });
        }
        needsNavigate = true;
      } else if (!conversation?.title || conversation.title === 'New conversation') {
        updateConversation(conversationId, {
          title: conversationTitleFromMessage(messageToSend),
        });
      }

      if (mode === 'agent') {
        // Agent mode: use agent API
        const response = await createAgentRun(
          {
            query: messageToSend,
            image_attachments: attachmentsToSend,
            conversation_id: conversationId!,
            max_steps: 1000,
            workspace_path: effectiveWorkspacePath || undefined,
            filesystem_enabled: !!effectiveWorkspacePath,
            permission_policy: permissionPolicy,
            collaboration_mode: collaborationMode,
            capabilities: {
              web: true,
              filesystem: !!effectiveWorkspacePath,
              command: !!effectiveWorkspacePath,
              python: false,
            },
          },
          activeModelSelection,
        );

        setPendingRunId(response.run_id);

        // Store stream token for reconnection after page refresh
        localStorage.setItem(`stream_token:${response.run_id}`, response.stream_token);

        // Subscribe to agent SSE stream with auth token BEFORE navigate
        // to prevent loadConversation from opening a duplicate connection
        subscribedRunRef.current = response.run_id;
        subscribeAgent(response.run_id, 0, response.stream_token);

        const run: Run = {
          run_id: response.run_id,
          created_at: new Date().toISOString(),
          status: 'running',
          mode: 'agent',
          profile: 'agent',
          prompt: messageToSend,
          user_message: messageToSend,
          conversation_id: conversationId!,
          conversation_summary: conversation?.summary || '',
          image_attachments: attachmentsToSend,
        };

        addRun(conversationId!, run);
        setEvents(response.run_id, []);
        setIsSubmitting(false);

        // Navigate AFTER subscription so the useEffect guard works
        if (needsNavigate) {
          navigate(`/conversations/${conversationId}`);
        }
      } else {
        // Chat mode: use regular conversation API
        const response = await createConversationRun(
          conversationId!,
          {
            message: messageToSend,
            image_attachments: attachmentsToSend,
          },
          activeModelSelection,
        );

        setPendingRunId(response.run_id);

        // CRITICAL: Subscribe to SSE IMMEDIATELY after getting run_id
        // This prevents race condition where events are emitted before frontend subscribes
        subscribe(response.run_id);

        const run: Run = {
          run_id: response.run_id,
          created_at: new Date().toISOString(),
          status: 'running',
          mode: 'system',
          profile: 'lmstudio',
          prompt: messageToSend,
          user_message: messageToSend,
          conversation_id: conversationId!,
          conversation_summary: conversation?.summary || '',
          image_attachments: attachmentsToSend,
        };

        addRun(conversationId!, run);
        setEvents(response.run_id, []);
        setIsSubmitting(false);

        // Navigate AFTER subscription for chat mode too
        if (needsNavigate) {
          navigate(`/conversations/${conversationId}`);
        }
      }
    } catch (error: unknown) {
      console.error('Failed to create run:', error);
      const apiError = error as { status?: number; message?: string };
      const errMsg = error instanceof Error ? error.message : String(error);
      if (apiError.status === 429) {
        toast.error('Message limit reached. You\'ve used all your free messages.');
        refreshUsage();
      } else {
        toast.error(`Send failed: ${apiError.status || 'N/A'} - ${errMsg}`);
      }
      // Restore message on error
      setMessage(messageToSend);
      setImageAttachments(attachmentsToSend.map((attachment, index) => ({
        ...attachment,
        id: `${Date.now()}-${index}`,
      })));
      clearMentionState();
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      scheduleComposerFocus();
      return;
    }

    scheduleComposerFocus();

    // Refresh usage after successful send
    refreshUsage();
  };

  const handlePlanImplementationStarted = useCallback((implementation: {
    run_id: string;
    stream_token?: string;
  }) => {
    if (!selectedConversationId) return;
    setCollaborationMode('default');
    setPendingRunId(implementation.run_id);
    if (implementation.stream_token) {
      localStorage.setItem(`stream_token:${implementation.run_id}`, implementation.stream_token);
    }
    subscribedRunRef.current = implementation.run_id;
    subscribeAgent(implementation.run_id, 0, implementation.stream_token);
    const run: Run = {
      run_id: implementation.run_id,
      created_at: new Date().toISOString(),
      status: 'running',
      mode: 'agent',
      profile: 'agent',
      prompt: 'Implement approved plan',
      user_message: 'Implement approved plan',
      conversation_id: selectedConversationId,
      conversation_summary: conversation?.summary || '',
    };
    addRun(selectedConversationId, run);
    setEvents(implementation.run_id, []);
  }, [addRun, conversation?.summary, selectedConversationId, setEvents, subscribeAgent]);

  // Handle stream completion - clear pending state.
  // Guard: only fire when we have a selected conversation (prevents false
  // triggers when selectedConversationId is still null during new-convo creation,
  // which causes activeRunId to be null → premature clear of isSubmitting).
  useEffect(() => {
    if (!selectedConversationId || !pendingRunId) return;
    if (activeRunId !== pendingRunId) {
      // The run we started is no longer active (completed or failed)
      setPendingMessage('');
      setPendingRunId(null);
      setPendingIsAgent(false);
      setIsSubmitting(false);
      setStoppingRunId(null);
      clearMentionState();
      setQueuedSteers([]);
      subscribedRunRef.current = null;
    }
  }, [clearMentionState, selectedConversationId, activeRunId, pendingRunId]);

  useEffect(() => {
    if (!stoppingRunId) return;
    const timeout = window.setTimeout(() => {
      void getAgentRunStatus(stoppingRunId)
        .then((status) => {
          if (!['cancelled', 'succeeded', 'failed', 'interrupted'].includes(status.status)) return;
          const terminalStatus = status.status as 'cancelled' | 'succeeded' | 'failed' | 'interrupted';
          updateRun(stoppingRunId, {
            status: terminalStatus,
            error_detail:
              terminalStatus === 'cancelled'
                ? 'Stopped by user'
                : terminalStatus === 'interrupted'
                  ? status.error_message || 'Run interrupted by server restart'
                  : undefined,
          });
          useStore.getState().updateAgentState(stoppingRunId, {
            isActive: false,
            agentState:
              terminalStatus === 'cancelled'
                ? 'cancelled'
                : terminalStatus === 'interrupted'
                  ? 'interrupted'
                : terminalStatus === 'succeeded'
                  ? 'complete'
                  : 'error',
          });
          localStorage.removeItem(`stream_token:${stoppingRunId}`);
          setStoppingRunId(null);
        })
        .catch(() => {
          setStoppingRunId(null);
        });
    }, 5000);
    return () => window.clearTimeout(timeout);
  }, [stoppingRunId, updateRun]);

  const handleStop = async () => {
    const runIdToStop = pendingRunId ?? activeRunId;
    if (!runIdToStop || stoppingRunId === runIdToStop) return;

    const runToStop = runs.find((run) => run.run_id === runIdToStop);
    const isAgentRun = pendingIsAgent || runToStop?.mode === 'agent';
    setStoppingRunId(runIdToStop);

    try {
      if (isAgentRun) {
        await cancelAgentRun(runIdToStop);
        updateRun(runIdToStop, {
          status: 'cancelled',
          error_detail: 'Stopped by user',
        });
        useStore.getState().updateAgentState(runIdToStop, {
          isActive: false,
          agentState: 'cancelled',
        });
        localStorage.removeItem(`stream_token:${runIdToStop}`);
      } else {
        await abortRun(runIdToStop);
        unsubscribe();
      }

      if (!isAgentRun && pendingMessage) {
        setMessage(pendingMessage);
      }
      if (pendingRunId === runIdToStop) {
        setPendingRunId(null);
        setPendingMessage('');
        setPendingIsAgent(false);
        setIsSubmitting(false);
      }
      clearMentionState();
      scheduleComposerFocus();
    } catch (error) {
      console.error('Failed to abort run:', error);
      toast.error('Failed to stop generation.');
    } finally {
      setStoppingRunId((current) => (current === runIdToStop ? null : current));
    }
  };

  const isGenerating = !!pendingRunId || !!activeRunId;
  const canSteerActiveRun = !!activeRunId && activeRun?.mode === 'agent';
  // Auto-resize textarea
  const resizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px';
  }, []);

  const handleMentionSelect = useCallback((entry: WorkspaceFileEntry) => {
    const mention = activeMention;
    if (!mention) return;
    const nextMessage = `${message.slice(0, mention.start)}${entry.path}${message.slice(mention.end)}`;
    const nextCursor = mention.start + entry.path.length;
    setMessage(nextMessage);
    setMentionOpen(false);
    setMentionError(null);
    setMentionResults([]);
    setActiveMention(null);
    requestAnimationFrame(() => {
      resizeTextarea();
      const textarea = textareaRef.current;
      if (!textarea) return;
      textarea.focus();
      textarea.setSelectionRange(nextCursor, nextCursor);
    });
  }, [activeMention, message, resizeTextarea]);

  const syncMentionState = useCallback((value: string, selectionStart: number | null) => {
    if (mode !== 'agent' || !effectiveWorkspacePath) {
      setActiveMention(null);
      setMentionOpen(false);
      setMentionError(null);
      return;
    }
    const mention = extractActiveMention(value, selectionStart ?? value.length);
    const mentionChanged = Boolean(
      mention
      && (
        !activeMention
        || mention.query !== activeMention.query
        || mention.start !== activeMention.start
        || mention.end !== activeMention.end
      )
    );
    setActiveMention((prev) => {
      if (!mention && !prev) return prev;
      if (!mention || !prev) return mention;
      if (mention.query === prev.query && mention.start === prev.start && mention.end === prev.end) return prev;
      return mention;
    });
    if (!mention) {
      setMentionOpen(false);
      setMentionLoading(false);
      setMentionError(null);
      return;
    }
    setMentionOpen(true);
    if (mentionChanged) {
      setMentionSelectedIndex(0);
      setMentionLoading(true);
      setMentionError(null);
    }
  }, [activeMention, effectiveWorkspacePath, mode]);

  const handleMessageChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    verticalMoveColumnRef.current = null;
    // Enforce character limit
    if (value.length <= MAX_INPUT_CHARS) {
      setMessage(value);
      syncMentionState(value, e.target.selectionStart);
    }
    // Resize on next frame after state update
    requestAnimationFrame(resizeTextarea);
  }, [resizeTextarea, syncMentionState]);

  const removeImageAttachment = useCallback((id?: string) => {
    setImageAttachments((prev) => prev.filter((attachment) => attachment.id !== id));
  }, []);

  const handlePaste = useCallback((e: ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(e.clipboardData.files).filter((file) => (
      file.type === 'image/png' || file.type === 'image/jpeg' || file.type === 'image/webp'
    ));
    if (!files.length) return;

    e.preventDefault();
    if (hasActiveRun) {
      toast.error('Image paste is only available before starting a run.');
      return;
    }
    if (!modelStatus?.supports_vision) {
      toast.error('Active model does not support images. Select a vision model.');
      return;
    }

    const remaining = MAX_IMAGE_ATTACHMENTS - imageAttachments.length;
    if (remaining <= 0) {
      toast.error(`You can attach up to ${MAX_IMAGE_ATTACHMENTS} images.`);
      return;
    }

    files.slice(0, remaining).forEach((file) => {
      if (file.size > MAX_IMAGE_BYTES) {
        toast.error(`${file.name || 'image'} is larger than 20MB.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || '');
        setImageAttachments((prev) => [
          ...prev,
          {
            id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
            name: file.name || `screenshot-${prev.length + 1}.${file.type.split('/')[1] || 'png'}`,
            mime_type: file.type,
            data_url: dataUrl,
          },
        ].slice(0, MAX_IMAGE_ATTACHMENTS));
      };
      reader.readAsDataURL(file);
    });
  }, [hasActiveRun, imageAttachments.length, modelStatus?.supports_vision]);

  const handleTextareaSelection = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    verticalMoveColumnRef.current = null;
    syncMentionState(textarea.value, textarea.selectionStart);
  }, [syncMentionState]);

  const syncTextareaState = useCallback((textarea: HTMLTextAreaElement) => {
    setMessage(textarea.value);
    syncMentionState(textarea.value, textarea.selectionStart);
    requestAnimationFrame(resizeTextarea);
  }, [resizeTextarea, syncMentionState]);

  const handleMentionKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (mentionOpen) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev + 1) % mentionResults.length : 0
        ));
        return true;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (
          mentionResults.length ? (prev - 1 + mentionResults.length) % mentionResults.length : 0
        ));
        return true;
      }
      if (e.key === 'Enter' && !e.metaKey && !e.ctrlKey) {
        const entry = mentionResults[mentionSelectedIndex];
        if (entry) {
          e.preventDefault();
          handleMentionSelect(entry);
          return true;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMentionOpen(false);
        return true;
      }
    }
    return false;
  }, [handleMentionSelect, mentionOpen, mentionResults, mentionSelectedIndex]);

  const handleComposerCommandKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      handleSubmit();
      return true;
    }
    if (e.key === '1' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('agent');
      return true;
    }
    if (e.key === '2' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      setMode('chat');
      return true;
    }
    return false;
  }, [handleSubmit]);

  const handleComposerEditingShortcut = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    const textarea = e.currentTarget;
    if (textarea.disabled || e.nativeEvent.isComposing) return false;

    const isMac = isApplePlatform();
    const key = e.key;
    const normalizedKey = key.length === 1 ? key.toLowerCase() : key;
    const hasModifiers = e.metaKey || e.altKey || e.shiftKey || e.ctrlKey;
    if (!hasModifiers) {
      verticalMoveColumnRef.current = null;
      return false;
    }

    const text = textarea.value;
    const selectionStart = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    const selectionCollapsed = selectionStart === selectionEnd;
    const collapseTo = (position: number) => {
      textarea.setSelectionRange(position, position);
      verticalMoveColumnRef.current = null;
      syncMentionState(textarea.value, textarea.selectionStart);
    };

    if (e.ctrlKey && !e.metaKey && !e.altKey && !e.shiftKey) {
      if (!isMac && normalizedKey === 'f') {
        return false;
      }

      switch (normalizedKey) {
        case 'a':
          e.preventDefault();
          collapseTo(getLineStart(text, selectionStart));
          return true;
        case 'e':
          e.preventDefault();
          collapseTo(getLineEnd(text, selectionEnd));
          return true;
        case 'b':
          e.preventDefault();
          collapseTo(selectionCollapsed ? Math.max(0, selectionStart - 1) : selectionStart);
          return true;
        case 'f':
          e.preventDefault();
          collapseTo(selectionCollapsed ? Math.min(text.length, selectionEnd + 1) : selectionEnd);
          return true;
        case 'p': {
          e.preventDefault();
          const nextPosition = moveVertical(text, selectionStart, -1, verticalMoveColumnRef.current);
          verticalMoveColumnRef.current = selectionStart - getLineStart(text, selectionStart);
          textarea.setSelectionRange(nextPosition, nextPosition);
          syncMentionState(textarea.value, textarea.selectionStart);
          return true;
        }
        case 'n': {
          e.preventDefault();
          const nextPosition = moveVertical(text, selectionEnd, 1, verticalMoveColumnRef.current);
          verticalMoveColumnRef.current = selectionEnd - getLineStart(text, selectionEnd);
          textarea.setSelectionRange(nextPosition, nextPosition);
          syncMentionState(textarea.value, textarea.selectionStart);
          return true;
        }
        case 'k':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', selectionStart, getLineEnd(text, selectionStart), 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        case 'u':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', getLineStart(text, selectionStart), selectionStart, 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        case 'w':
          e.preventDefault();
          if (hasTextSelection(textarea)) {
            replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
          } else {
            replaceTextareaRange(textarea, '', moveWordLeft(text, selectionStart), selectionStart, 'start');
          }
          verticalMoveColumnRef.current = null;
          syncTextareaState(textarea);
          return true;
        default:
          verticalMoveColumnRef.current = null;
          return false;
      }
    }

    if (isMac && e.altKey && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
      if (normalizedKey === 'b') {
        e.preventDefault();
        collapseTo(moveWordLeft(text, selectionStart));
        return true;
      }
      if (normalizedKey === 'f') {
        e.preventDefault();
        collapseTo(moveWordRight(text, selectionEnd));
        return true;
      }
      if (normalizedKey === 'Backspace') {
        e.preventDefault();
        if (hasTextSelection(textarea)) {
          replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
        } else {
          replaceTextareaRange(textarea, '', moveWordLeft(text, selectionStart), selectionStart, 'start');
        }
        verticalMoveColumnRef.current = null;
        syncTextareaState(textarea);
        return true;
      }
    }

    if (isMac && e.metaKey && !e.ctrlKey && !e.altKey && !e.shiftKey && normalizedKey === 'Backspace') {
      e.preventDefault();
      if (hasTextSelection(textarea)) {
        replaceTextareaRange(textarea, '', selectionStart, selectionEnd, 'start');
      } else {
        replaceTextareaRange(textarea, '', getLineStart(text, selectionStart), selectionStart, 'start');
      }
      verticalMoveColumnRef.current = null;
      syncTextareaState(textarea);
      return true;
    }

    verticalMoveColumnRef.current = null;
    return false;
  }, [syncMentionState, syncTextareaState]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (handleMentionKeyDown(e)) return;
    if (handleComposerCommandKeyDown(e)) return;
    handleComposerEditingShortcut(e);
  };

  const openWorkspacePickerForNewConversation = useCallback(async () => {
    if (hasActiveRun) return;
    const selectedPath = await openNativeWorkspacePicker();
    const normalized = selectedPath?.trim();
    if (normalized) {
      beginWorkspaceDraft(normalized);
      navigate('/conversations', { replace: true });
    }
  }, [
    beginWorkspaceDraft,
    hasActiveRun,
    navigate,
  ]);

  const startWorkspaceDraftConversation = useCallback((workspacePath: string) => {
    if (hasActiveRun) return;
    const normalized = workspacePath.trim();
    if (!normalized) {
      openWorkspacePickerForNewConversation();
      return;
    }
    beginWorkspaceDraft(normalized);
    navigate('/conversations', { replace: true });
  }, [
    beginWorkspaceDraft,
    hasActiveRun,
    navigate,
    openWorkspacePickerForNewConversation,
  ]);

  const clearPendingWorkspaceShortcut = useCallback(() => {
    pendingWorkspaceShortcutRef.current = null;
    if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
      window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
      pendingWorkspaceShortcutTimeoutRef.current = null;
    }
  }, []);

  const armPendingWorkspaceShortcut = useCallback((action: 'workspace-new' | 'workspace-picker') => {
    pendingWorkspaceShortcutRef.current = action;
    if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
      window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
    }
    pendingWorkspaceShortcutTimeoutRef.current = window.setTimeout(() => {
      pendingWorkspaceShortcutRef.current = null;
      pendingWorkspaceShortcutTimeoutRef.current = null;
    }, 1500);
  }, []);

  useEffect(() => {
    const handleWindowKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing) return;
      const lowerKey = event.key.toLowerCase();

      if (
        lowerKey === 'escape'
        && !event.metaKey
        && !event.ctrlKey
        && !event.altKey
        && !event.shiftKey
        && !event.repeat
      ) {
        if (
          !mentionOpen
          && !anyDialogOpen
          && !hasActiveRun
          && !!selectedConversationId
          && !!lockedWorkspacePath
        ) {
          const now = Date.now();
          if (now - lastEscapeAtRef.current <= 800) {
            event.preventDefault();
            lastEscapeAtRef.current = 0;
            void openRewindPicker();
            return;
          }
          lastEscapeAtRef.current = now;
        } else {
          lastEscapeAtRef.current = 0;
        }
      } else if (lastEscapeAtRef.current !== 0) {
        lastEscapeAtRef.current = 0;
      }

      const pendingWorkspaceShortcut = pendingWorkspaceShortcutRef.current;
      if (pendingWorkspaceShortcut) {
        if (event.metaKey || event.ctrlKey || event.altKey) {
          clearPendingWorkspaceShortcut();
          return;
        }
        if (lowerKey === 'escape') {
          clearPendingWorkspaceShortcut();
          return;
        }
        if (lowerKey === 'n') {
          event.preventDefault();
          clearPendingWorkspaceShortcut();
          if (hasActiveRun) return;
          if (effectiveWorkspacePath) {
            startWorkspaceDraftConversation(effectiveWorkspacePath);
          } else {
            openWorkspacePickerForNewConversation();
          }
          return;
        }
        if (lowerKey === 'w') {
          event.preventDefault();
          clearPendingWorkspaceShortcut();
          openWorkspacePickerForNewConversation();
          return;
        }
        clearPendingWorkspaceShortcut();
      }

      if ((event.metaKey || event.ctrlKey) && !event.shiftKey && !event.altKey && lowerKey === 'k') {
        if (isTextInputElement(event.target)) return;
        event.preventDefault();
        armPendingWorkspaceShortcut('workspace-new');
        return;
      }

      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (isTextInputElement(event.target)) return;
      const textarea = textareaRef.current;
      if (!textarea || textarea.disabled) return;
      event.preventDefault();
      focusComposer();
    };

    window.addEventListener('keydown', handleWindowKeyDown);
    return () => window.removeEventListener('keydown', handleWindowKeyDown);
  }, [
    anyDialogOpen,
    armPendingWorkspaceShortcut,
    clearPendingWorkspaceShortcut,
    effectiveWorkspacePath,
    focusComposer,
    hasActiveRun,
    lockedWorkspacePath,
    mentionOpen,
    openRewindPicker,
    selectedConversationId,
    openWorkspacePickerForNewConversation,
    startWorkspaceDraftConversation,
  ]);

  useEffect(() => {
    return () => {
      if (composerFocusRafRef.current !== null) {
        cancelAnimationFrame(composerFocusRafRef.current);
      }
      if (pendingWorkspaceShortcutTimeoutRef.current !== null) {
        window.clearTimeout(pendingWorkspaceShortcutTimeoutRef.current);
      }
      lastEscapeAtRef.current = 0;
    };
  }, []);

  // Reset textarea height when message is cleared (after submit)
  useEffect(() => {
    if (!message && textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [message]);

  useEffect(() => {
    if (mode !== 'agent' || !effectiveWorkspacePath || !activeMention) {
      clearMentionState();
      return;
    }

    let cancelled = false;
    setMentionLoading(true);
    const timer = window.setTimeout(() => {
      searchWorkspaceFiles(effectiveWorkspacePath, activeMention.query, MENTION_RESULT_LIMIT)
        .then((response) => {
          if (cancelled) return;
          setMentionResults(response.entries);
          setMentionSelectedIndex(0);
          setMentionError(null);
          setMentionOpen(true);
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          setMentionResults([]);
          setMentionError((error as { message?: string })?.message || 'file search failed');
          setMentionOpen(true);
        })
        .finally(() => {
          if (!cancelled) {
            setMentionLoading(false);
          }
        });
    }, 120);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [activeMention, clearMentionState, effectiveWorkspacePath, mode]);

  const rewindDialog = (
    <Dialog open={rewindOpen} onOpenChange={handleRewindOpenChange}>
      <DialogContent className="max-w-xl border-zinc-800 bg-zinc-950 text-zinc-100">
        <DialogHeader>
          <DialogTitle className="font-mono text-sm text-zinc-100">rewind conversation</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <p className="font-mono text-[12px] leading-6 text-zinc-500">
            Rewind the active branch to before a prior prompt, then restore that prompt into the composer.
          </p>
          <div className="max-h-[22rem] space-y-2 overflow-y-auto pr-1">
            {rewindLoading ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-3 font-mono text-[12px] text-zinc-500">
                loading…
              </div>
            ) : rewindCheckpoints.length === 0 ? (
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-3 py-3 font-mono text-[12px] text-zinc-500">
                No rewind points available for this conversation yet.
              </div>
            ) : (
              rewindCheckpoints.map((checkpoint) => {
                const selected = checkpoint.run_id === rewindSelectedRunId;
                return (
                  <button
                    key={checkpoint.run_id}
                    type="button"
                    onClick={() => setRewindSelectedRunId(checkpoint.run_id)}
                    className={cn(
                      'w-full rounded-xl border px-3 py-3 text-left ui-transition',
                      selected
                        ? 'border-cyan-500/35 bg-cyan-500/[0.08] text-zinc-100'
                        : 'border-zinc-800 bg-zinc-900/60 text-zinc-300 hover:border-zinc-700 hover:bg-zinc-900'
                    )}
                  >
                    <div className="truncate font-mono text-[12px] leading-6">
                      {checkpoint.user_message}
                    </div>
                    <div className="mt-1 font-mono text-[11px] text-zinc-500">
                      {formatRelativeTime(checkpoint.created_at)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
          <div className="flex items-center justify-end gap-2 font-mono text-[12px]">
            <button
              type="button"
              onClick={() => setRewindOpen(false)}
              className="rounded-lg border border-zinc-800 px-3 py-2 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200"
              disabled={rewindSubmitting}
            >
              cancel
            </button>
            <button
              type="button"
              onClick={() => void handleRewindRestore()}
              disabled={!rewindSelectedRunId || rewindLoading || rewindSubmitting}
              className={cn(
                'rounded-lg border px-3 py-2 ui-transition',
                !rewindSelectedRunId || rewindLoading || rewindSubmitting
                  ? 'cursor-not-allowed border-zinc-800 text-zinc-600'
                  : 'border-cyan-500/35 text-cyan-100 hover:bg-cyan-500/[0.08]'
              )}
            >
              {rewindSubmitting ? 'rewinding…' : 'rewind'}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );

  const imageAttachmentsRow =
    imageAttachments.length > 0 ? (
      <ImagePreviewStrip
        images={imageAttachments}
        onRemove={removeImageAttachment}
        className="px-1"
        thumbnailClassName="h-14 w-14"
      />
    ) : null;

  const terminalAvailable = mode === 'agent';
  const activeTerminalState = selectedConversationId ? terminalState : draftTerminalState;
  const terminalOpen = terminalAvailable && !!activeTerminalState?.isOpen;

  const handleTerminalToggle = useCallback(() => {
    if (mode !== 'agent') return;
    if (!effectiveWorkspacePath) {
      toast.error(
        selectedConversationId
          ? 'Create or open a workspace conversation first'
          : 'Select a workspace first'
      );
      if (!selectedConversationId) {
        setWorkspacePickerOpen(true);
      }
      return;
    }
    const terminalKey = selectedConversationId || DRAFT_TERMINAL_CONVERSATION_ID;
    updateTerminalState(terminalKey, {
      isOpen: !activeTerminalState?.isOpen,
    });
  }, [
    activeTerminalState?.isOpen,
    effectiveWorkspacePath,
    mode,
    selectedConversationId,
    updateTerminalState,
  ]);

  const desktopWorkspaceLabel = useMemo(() => {
    if (mode !== 'agent') return null;
    const path = isWorkspaceLocked ? effectiveWorkspacePath : draftWorkspacePath;
    const trimmed = path.trim();
    if (!trimmed) return 'No folder';
    return trimmed.split('/').filter(Boolean).pop() || trimmed;
  }, [mode, isWorkspaceLocked, effectiveWorkspacePath, draftWorkspacePath]);

  const desktopWorkspaceTitle = useMemo(() => {
    if (mode !== 'agent') return undefined;
    const path = isWorkspaceLocked ? effectiveWorkspacePath : draftWorkspacePath;
    return path.trim() || undefined;
  }, [mode, isWorkspaceLocked, effectiveWorkspacePath, draftWorkspacePath]);

  const desktopComposerControls = (
    <DesktopComposerControls
      mode={mode}
      modelStatus={modelStatus}
      onModelClick={() => setModelPickerOpen(true)}
      onReasoningClick={() => setReasoningSettingsOpen(true)}
      showTerminal={terminalAvailable}
      terminalOpen={terminalOpen}
      onTerminalClick={handleTerminalToggle}
      isWorkspaceLocked={isWorkspaceLocked}
      hasConversationWorkspace={hasConversationWorkspace}
      effectiveWorkspacePath={effectiveWorkspacePath}
      draftWorkspacePath={draftWorkspacePath}
      onDraftWorkspacePathChange={setDraftWorkspacePath}
      onBrowseWorkspace={() => {
        void handleOpenWorkspacePicker();
      }}
      permissionPolicy={permissionPolicy}
      onPermissionPolicyChange={setPermissionPolicy}
      collaborationMode={collaborationMode}
      onCollaborationModeChange={setCollaborationMode}
    />
  );

  const agentContextStatsRow = (
    <AgentContextFooter
      show={showComposerContextStats}
      composerContextUtilizationPct={composerContextUtilizationPct ?? null}
      composerPromptTokens={composerPromptTokens ?? null}
      composerContextWindow={composerContextWindow ?? null}
      conversationInputTokens={conversationTokenAndCostTotals.inputTokens}
      conversationOutputTokens={conversationTokenAndCostTotals.outputTokens}
      conversationInputCost={conversationTokenAndCostTotals.inputCost}
      conversationOutputCost={conversationTokenAndCostTotals.outputCost}
      formatContextTokens={formatContextTokens}
      formatCost={formatAgentCost}
    />
  );

  const mentionPickerNode = (
    <MentionPicker
      open={mentionOpen}
      loading={mentionLoading}
      error={mentionError}
      entries={mentionResults}
      selectedIndex={mentionSelectedIndex}
      onSelect={handleMentionSelect}
      desktop
    />
  );

  const limitHintNode = hasLimit ? (
    <p
      className={cn(
        'text-[11px]',
        atLimit ? 'text-red-400/80' : usage.remaining <= 3 ? 'text-amber-400' : 'text-zinc-600'
      )}
    >
      {atLimit ? 'No messages left' : `${usage.remaining} messages left`}
    </p>
  ) : null;

  const sharedComposerProps = {
    textareaRef,
    message,
    atLimit,
    isSubmitting,
    isGenerating,
    canSteerActiveRun,
    hasActiveRun,
    stoppingRunId,
    messageLength: message.length,
    maxLength: MAX_INPUT_CHARS,
    onChange: handleMessageChange,
    onPaste: handlePaste,
    onKeyDown: handleKeyDown,
    onSelect: handleTextareaSelection,
    onClick: handleTextareaSelection,
    onSubmit: handleSubmit,
    onStop: handleStop,
    mentionPicker: mentionPickerNode,
    attachmentsRow: imageAttachmentsRow,
  };
  const handleEmptyDesktopDrag = (event: ReactMouseEvent<HTMLDivElement>) => {
    void startWindowDrag(event);
  };

  if (!conversation && runs.length === 0) {
    return (
      <div className="flex h-full flex-col">
        <DesktopChrome title="New conversation" mergeTitlebar />
        <ModelPicker
          open={modelPickerOpen}
          onOpenChange={setModelPickerOpen}
          modelStatus={modelStatus}
          onModelStatusChange={handleModelStatusChange}
          activeSelection={activeModelSelection}
        />
        <ReasoningSettingsDialog
          open={reasoningSettingsOpen}
          onOpenChange={setReasoningSettingsOpen}
          settingsResponse={reasoningSettings}
          draft={reasoningDraft}
          onDraftChange={setReasoningDraft}
          onSave={handleSaveReasoningSettings}
          saving={reasoningSaving}
        />
        <WorkspacePickerDialog
          open={workspacePickerOpen}
          onOpenChange={setWorkspacePickerOpen}
          onSelect={(workspacePath) => {
            rememberWorkspacePath(workspacePath);
            setDraftWorkspacePath(workspacePath);
          }}
        />
        <div
          data-tauri-drag-region
          onMouseDown={handleEmptyDesktopDrag}
          className={cn(
            'flex min-h-0 flex-1 flex-col overflow-y-auto',
            'desktop-empty-drag-surface'
          )}
        >
          <EmptyState
            mode={mode}
            workspacePath={effectiveWorkspacePath}
            modelStatus={modelStatus}
            onSuggestionClick={(text) => setMessage(text)}
          />
        </div>
        <DesktopInputDock
          mode={mode}
          onModeChange={setMode}
          workspaceLabel={desktopWorkspaceLabel}
          workspaceTitle={desktopWorkspaceTitle}
          queuedSteers={[]}
          activeAgentRun={null}
          activeAgentHudState={null}
          showAgentHud={false}
          controlsRow={desktopComposerControls}
          placeholder={
            mode === 'agent' ? 'Ask the agent…' : 'Ask a question…'
          }
          {...sharedComposerProps}
          metaRow={agentContextStatsRow}
          limitHint={limitHintNode}
          disabled={isSubmitting || atLimit || (hasActiveRun && !canSteerActiveRun)}
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <DesktopChrome
        title={conversation?.title || 'Conversation'}
        mergeTitlebar
      />
      <ModelPicker
        open={modelPickerOpen}
        onOpenChange={setModelPickerOpen}
        modelStatus={modelStatus}
        onModelStatusChange={handleModelStatusChange}
        activeSelection={activeModelSelection}
      />
      <ReasoningSettingsDialog
        open={reasoningSettingsOpen}
        onOpenChange={setReasoningSettingsOpen}
        settingsResponse={reasoningSettings}
        draft={reasoningDraft}
        onDraftChange={setReasoningDraft}
        onSave={handleSaveReasoningSettings}
        saving={reasoningSaving}
      />
      <WorkspacePickerDialog
        open={workspacePickerOpen}
        onOpenChange={setWorkspacePickerOpen}
        onSelect={(workspacePath) => {
          rememberWorkspacePath(workspacePath);
          setDraftWorkspacePath(workspacePath);
        }}
      />
      {rewindDialog}

      <div className="relative flex min-h-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-4 py-6" ref={scrollRef}>
          <div className="desktop-thread-column w-full">
            {isLoadingSelectedConversation && runs.length === 0 ? (
              <div className="flex min-h-[45vh] items-center justify-center">
                <div className="flex items-center gap-3 rounded-full border border-white/[0.08] bg-white/[0.035] px-4 py-2 text-[13px] text-zinc-400">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-cyan-300/80" />
                  Loading conversation…
                </div>
              </div>
            ) : runs.length === 0 ? (
              <div className="flex min-h-[45vh] items-center justify-center text-[13px] text-zinc-500">
                No messages in this conversation.
              </div>
            ) : (
              <VirtualizedConversationRunList
                runs={runs}
                scrollContainerRef={scrollRef}
                renderRun={renderRunCard}
              />
            )}
          </div>
        </div>

        <ScrollToBottom
          scrollRef={scrollRef}
          isStreaming={!!activeRunId}
          className="left-1/2 -translate-x-1/2 bottom-[calc(var(--desktop-dock-height)+1rem)]"
        />

        <div className="flex-shrink-0">
          <DesktopInputDock
            mode={mode}
            onModeChange={setMode}
            workspaceLabel={desktopWorkspaceLabel}
            workspaceTitle={desktopWorkspaceTitle}
            queuedSteers={queuedSteers}
            activeAgentRun={activeAgentRun}
            activeAgentHudState={activeAgentHudState ?? null}
            showAgentHud={!!activeAgentHudState?.isActive}
            onImplementationStarted={handlePlanImplementationStarted}
            controlsRow={desktopComposerControls}
            placeholder={
              atLimit
                ? 'Message limit reached'
                : hasActiveRun
                  ? 'Steer the agent…'
                  : mode === 'agent'
                    ? 'Ask the agent…'
                    : 'Ask a follow-up question…'
            }
            {...sharedComposerProps}
            metaRow={agentContextStatsRow}
            limitHint={limitHintNode}
            disabled={isSubmitting || atLimit}
          />
        </div>
      </div>
    </div>
  );
}
