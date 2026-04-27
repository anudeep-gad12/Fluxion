// Zustand store for application state

import { create } from 'zustand';
import type { Run, Event, Conversation } from '@/types';
import type { AgentUIState, AgentStep, AgentToolCall, AgentCitation } from '@/types/agent';

interface AppState {
  // Conversations
  conversations: Conversation[];
  selectedConversationId: string | null;

  // Runs per conversation
  runsByConversation: Record<string, Run[]>;
  selectedRunId: string | null;

  // Events per run
  eventsByRun: Record<string, Event[]>;

  // Detail panel state
  detailPanelOpen: boolean;
  selectedEventSeq: number | null;

  // Streaming state
  streamingRunId: string | null;
  streamingText: Record<string, string>;  // runId -> partial response
  streamingThinking: Record<string, string>;  // runId -> partial thinking content

  // Connection state
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;

  // Fetch tracking to prevent duplicate requests
  fetchingRuns: Set<string>;

  // Agent run state (per run_id)
  agentRunState: Record<string, AgentUIState>;

  // Conversation actions
  setConversations: (conversations: Conversation[]) => void;
  addConversation: (conversation: Conversation) => void;
  updateConversation: (conversationId: string, updates: Partial<Conversation>) => void;
  removeConversation: (conversationId: string) => void;
  selectConversation: (conversationId: string | null) => void;

  // Run actions
  setRuns: (conversationId: string, runs: Run[]) => void;
  addRun: (conversationId: string, run: Run) => void;
  updateRun: (runId: string, updates: Partial<Run>) => void;
  removeRun: (runId: string) => void;
  selectRun: (runId: string | null) => void;

  // Event actions
  addEvent: (runId: string, event: Event) => void;
  setEvents: (runId: string, events: Event[]) => void;

  // Detail panel actions
  toggleDetailPanel: () => void;
  setDetailPanelOpen: (open: boolean) => void;
  selectEvent: (seq: number | null) => void;

  // Connection actions
  setConnected: (connected: boolean) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setStreamingRunId: (runId: string | null) => void;
  appendStreamingText: (runId: string, token: string) => void;
  clearStreamingText: (runId: string) => void;
  appendStreamingThinking: (runId: string, token: string) => void;
  clearStreamingThinking: (runId: string) => void;

  // Fetch tracking actions
  setFetching: (runId: string, fetching: boolean) => void;
  isFetchingRun: (runId: string) => boolean;

  // Agent run actions
  initAgentRun: (runId: string, maxSteps: number) => void;
  updateAgentState: (runId: string, updates: Partial<AgentUIState>) => void;
  appendAgentThinking: (runId: string, content: string) => void;
  appendAgentAnswer: (runId: string, content: string) => void;
  addAgentStep: (runId: string, step: AgentStep) => void;
  addAgentToolCall: (runId: string, toolCall: AgentToolCall) => void;
  updateAgentToolCall: (runId: string, toolCallId: string, updates: Partial<AgentToolCall>) => void;
  updateAgentStep: (runId: string, stepNumber: number, updates: Partial<AgentStep>) => void;
  setAgentCitations: (runId: string, citations: AgentCitation[]) => void;
  clearAgentRun: (runId: string) => void;
}

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  conversations: [],
  selectedConversationId: null,
  runsByConversation: {},
  selectedRunId: null,
  eventsByRun: {},
  detailPanelOpen: false,
  selectedEventSeq: null,
  streamingRunId: null,
  streamingText: {},
  streamingThinking: {},
  isConnected: false,
  isLoading: false,
  error: null,
  fetchingRuns: new Set<string>(),
  agentRunState: {},

  // Conversation actions
  setConversations: (conversations) => set({ conversations }),

  addConversation: (conversation) => set((state) => ({
    conversations: [conversation, ...state.conversations],
  })),

  updateConversation: (conversationId, updates) => set((state) => ({
    conversations: state.conversations.map((c) =>
      c.conversation_id === conversationId ? { ...c, ...updates } : c
    ),
  })),

  removeConversation: (conversationId) => set((state) => {
    const { [conversationId]: _removed, ...remainingRuns } = state.runsByConversation;
    return {
      conversations: state.conversations.filter((c) => c.conversation_id !== conversationId),
      runsByConversation: remainingRuns,
      selectedConversationId: state.selectedConversationId === conversationId ? null : state.selectedConversationId,
      selectedRunId: null,
    };
  }),

  selectConversation: (conversationId) => set({
    selectedConversationId: conversationId,
    selectedRunId: null,
    selectedEventSeq: null,
  }),

  // Run actions
  setRuns: (conversationId, runs) => set((state) => ({
    runsByConversation: {
      ...state.runsByConversation,
      [conversationId]: runs,
    },
  })),

  addRun: (conversationId, run) => set((state) => ({
    runsByConversation: {
      ...state.runsByConversation,
      [conversationId]: [...(state.runsByConversation[conversationId] || []), run],
    },
  })),

  updateRun: (runId, updates) => set((state) => {
    const runsByConversation: Record<string, Run[]> = {};
    for (const [conversationId, runs] of Object.entries(state.runsByConversation)) {
      runsByConversation[conversationId] = runs.map((run) =>
        run.run_id === runId ? { ...run, ...updates } : run
      );
    }
    return { runsByConversation };
  }),

  removeRun: (runId) => set((state) => {
    // Remove run from all conversations
    const runsByConversation: Record<string, Run[]> = {};
    for (const [conversationId, runs] of Object.entries(state.runsByConversation)) {
      runsByConversation[conversationId] = runs.filter((run) => run.run_id !== runId);
    }

    // Clean up streaming state for this run
    const { [runId]: _streamText, ...restStreamingText } = state.streamingText;
    const { [runId]: _streamThink, ...restStreamingThinking } = state.streamingThinking;
    const { [runId]: _events, ...restEventsByRun } = state.eventsByRun;

    return {
      runsByConversation,
      streamingText: restStreamingText,
      streamingThinking: restStreamingThinking,
      eventsByRun: restEventsByRun,
      selectedRunId: state.selectedRunId === runId ? null : state.selectedRunId,
      streamingRunId: state.streamingRunId === runId ? null : state.streamingRunId,
    };
  }),

  selectRun: (runId) => set({ selectedRunId: runId, selectedEventSeq: null }),

  // Event actions - with deduplication by seq
  addEvent: (runId, event) => set((state) => {
    const existing = state.eventsByRun[runId] || [];
    // Deduplicate by seq - skip if event with this seq already exists
    if (existing.some((e) => e.seq === event.seq)) {
      return state; // No change needed
    }
    // Insert and sort by seq to maintain order
    const updated = [...existing, event].sort((a, b) => a.seq - b.seq);
    return {
      eventsByRun: {
        ...state.eventsByRun,
        [runId]: updated,
      },
    };
  }),

  setEvents: (runId, events) => set((state) => {
    // Deduplicate by seq
    const seen = new Set<number>();
    const deduped = events.filter((e) => {
      if (seen.has(e.seq)) return false;
      seen.add(e.seq);
      return true;
    }).sort((a, b) => a.seq - b.seq);

    return {
      eventsByRun: {
        ...state.eventsByRun,
        [runId]: deduped,
      },
    };
  }),

  // Detail panel actions
  toggleDetailPanel: () => set((state) => ({ detailPanelOpen: !state.detailPanelOpen })),
  setDetailPanelOpen: (open) => set({ detailPanelOpen: open }),
  selectEvent: (seq) => set({ selectedEventSeq: seq, detailPanelOpen: seq !== null }),

  // Connection actions
  setConnected: (isConnected) => set({ isConnected }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),
  setStreamingRunId: (streamingRunId) => set({ streamingRunId }),

  // Streaming text actions
  appendStreamingText: (runId, token) => set((state) => ({
    streamingText: {
      ...state.streamingText,
      [runId]: (state.streamingText[runId] || '') + token,
    },
  })),
  clearStreamingText: (runId) => set((state) => {
    const { [runId]: _, ...rest } = state.streamingText;
    return { streamingText: rest };
  }),

  // Streaming thinking actions
  appendStreamingThinking: (runId, token) => set((state) => ({
    streamingThinking: {
      ...state.streamingThinking,
      [runId]: (state.streamingThinking[runId] || '') + token,
    },
  })),
  clearStreamingThinking: (runId) => set((state) => {
    const { [runId]: _, ...rest } = state.streamingThinking;
    return { streamingThinking: rest };
  }),

  // Fetch tracking actions
  setFetching: (runId, fetching) => set((state) => {
    const newSet = new Set(state.fetchingRuns);
    if (fetching) {
      newSet.add(runId);
    } else {
      newSet.delete(runId);
    }
    return { fetchingRuns: newSet };
  }),
  isFetchingRun: (runId) => get().fetchingRuns.has(runId),

  // Agent run actions
  initAgentRun: (runId, maxSteps) =>
    set((state) => ({
      agentRunState: {
        ...state.agentRunState,
        [runId]: {
          isActive: true,
          currentStep: 0,
          maxSteps,
          agentState: 'initializing',
          thinkingBuffer: '',
          answerBuffer: '',
          steps: [],
          toolCalls: [],
          citations: [],
          systemEvents: [],
          injectedSteers: [],
          lastSeq: 0,
        },
      },
    })),

  updateAgentState: (runId, updates) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: { ...current, ...updates },
        },
      };
    }),

  appendAgentThinking: (runId, content) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            thinkingBuffer: current.thinkingBuffer + content,
          },
        },
      };
    }),

  appendAgentAnswer: (runId, content) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            answerBuffer: current.answerBuffer + content,
          },
        },
      };
    }),

  addAgentStep: (runId, step) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      // Avoid duplicates by step_number
      const exists = current.steps.some((s) => s.step_number === step.step_number);
      if (exists) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            steps: [...current.steps, step],
            currentStep: step.step_number,
          },
        },
      };
    }),

  addAgentToolCall: (runId, toolCall) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      // Avoid duplicates by id
      const exists = current.toolCalls.some((tc) => tc.id === toolCall.id);
      if (exists) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            toolCalls: [...current.toolCalls, toolCall],
          },
        },
      };
    }),

  updateAgentToolCall: (runId, toolCallId, updates) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            toolCalls: current.toolCalls.map((tc) =>
              tc.id === toolCallId ? { ...tc, ...updates } : tc
            ),
          },
        },
      };
    }),

  updateAgentStep: (runId, stepNumber, updates) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: {
            ...current,
            steps: current.steps.map((s) =>
              s.step_number === stepNumber ? { ...s, ...updates } : s
            ),
          },
        },
      };
    }),

  setAgentCitations: (runId, citations) =>
    set((state) => {
      const current = state.agentRunState[runId];
      if (!current) return state;
      return {
        agentRunState: {
          ...state.agentRunState,
          [runId]: { ...current, citations },
        },
      };
    }),

  clearAgentRun: (runId) =>
    set((state) => {
      const { [runId]: _, ...rest } = state.agentRunState;
      return { agentRunState: rest };
    }),
}));

// Selectors
export const useSelectedConversation = () => {
  const conversations = useStore((s) => s.conversations);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  return conversations.find((c) => c.conversation_id === selectedConversationId);
};

export const useConversationRuns = (conversationId: string | null) => {
  const runsByConversation = useStore((s) => s.runsByConversation);
  return conversationId ? runsByConversation[conversationId] || [] : [];
};

export const useSelectedRun = () => {
  const runsByConversation = useStore((s) => s.runsByConversation);
  const selectedRunId = useStore((s) => s.selectedRunId);
  if (!selectedRunId) return undefined;
  for (const runs of Object.values(runsByConversation)) {
    const found = runs.find((r) => r.run_id === selectedRunId);
    if (found) return found;
  }
  return undefined;
};

export const useRunEvents = (runId: string | null) => {
  const eventsByRun = useStore((s) => s.eventsByRun);
  return runId ? eventsByRun[runId] || [] : [];
};

export const useAgentRunState = (runId: string | null) => {
  const agentRunState = useStore((s) => s.agentRunState);
  return runId ? agentRunState[runId] : undefined;
};

/** Check if any run is currently active (agent or chat streaming) */
export const useHasActiveRun = () => {
  const agentRunState = useStore((s) => s.agentRunState);
  const streamingRunId = useStore((s) => s.streamingRunId);
  const runsByConversation = useStore((s) => s.runsByConversation);

  // Check if any agent run is active (in-memory state)
  const hasActiveAgent = Object.values(agentRunState).some((state) => state.isActive);

  // Check if chat streaming is active (in-memory state)
  const hasActiveChat = streamingRunId !== null;

  // Check if any run has status 'running' in backend data (survives reload)
  const hasRunningBackendRun = Object.values(runsByConversation).some((runs) =>
    runs.some((run) => run.status === 'running')
  );

  return hasActiveAgent || hasActiveChat || hasRunningBackendRun;
};
