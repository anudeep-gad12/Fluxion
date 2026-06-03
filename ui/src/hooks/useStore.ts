// Zustand store for application state

import { create } from 'zustand';
import type { Run, Event, Conversation } from '@/types';
import type { AgentUIState, AgentStep, AgentToolCall, AgentCitation } from '@/types/agent';
import {
  ensureWorkspaceFluxionGitignore,
  type TerminalSessionResponse,
} from '@/api/client';

const WORKSPACE_STORAGE_KEY = 'reasoner_workspace_path';
const WORKSPACE_LIST_STORAGE_KEY = 'reasoner_workspace_paths';
const EMPTY_RUNS: Run[] = [];
const EMPTY_EVENTS: Event[] = [];

function dedupeRuns(runs: Run[]): Run[] {
  const seen = new Set<string>();
  return runs.filter((run) => {
    if (seen.has(run.run_id)) return false;
    seen.add(run.run_id);
    return true;
  });
}

export interface TerminalUIState {
  isOpen: boolean;
  dock: 'bottom' | 'right';
  height: number;
  width: number;
  activeToolTabId: string | null;
  browserTabs: BrowserTabState[];
  sessions: TerminalSessionResponse[];
  activeSessionId: string | null;
  maxSessionsPerConversation: number;
  maxBrowserTabsPerConversation: number;
  bufferBySessionId: Record<string, string>;
  session: TerminalSessionResponse | null;
  buffer: string;
  connected: boolean;
  status: 'idle' | 'connecting' | 'running' | 'closed' | 'stale' | 'error';
}

export interface BrowserTabState {
  id: string;
  url: string;
  title: string;
  status: 'idle' | 'loading' | 'ready' | 'error';
  error?: string | null;
}

interface AppState {
  // Conversations
  conversations: Conversation[];
  selectedConversationId: string | null;
  draftWorkspacePath: string;
  draftConversationNonce: number;
  workspacePaths: string[];

  // Runs per conversation
  runsByConversation: Record<string, Run[]>;

  // Events per run
  eventsByRun: Record<string, Event[]>;

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
  terminalByConversation: Record<string, TerminalUIState>;

  /** Active conversation UI mode (synced from ConversationView for shell panels). */
  conversationMode: 'chat' | 'agent';

  // Conversation actions
  setConversations: (conversations: Conversation[]) => void;
  addConversation: (conversation: Conversation) => void;
  updateConversation: (conversationId: string, updates: Partial<Conversation>) => void;
  removeConversation: (conversationId: string) => void;
  selectConversation: (conversationId: string | null) => void;
  setDraftWorkspacePath: (workspacePath: string) => void;
  bumpDraftConversation: () => void;
  rememberWorkspacePath: (workspacePath: string) => void;

  // Run actions
  setRuns: (conversationId: string, runs: Run[]) => void;
  addRun: (conversationId: string, run: Run) => void;
  updateRun: (runId: string, updates: Partial<Run>) => void;
  removeRun: (runId: string) => void;

  // Event actions
  addEvent: (runId: string, event: Event) => void;
  setEvents: (runId: string, events: Event[]) => void;

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

  // Terminal UI actions
  initTerminalState: (conversationId: string, defaults?: Partial<TerminalUIState>) => void;
  updateTerminalState: (conversationId: string, updates: Partial<TerminalUIState>) => void;
  appendTerminalBuffer: (conversationId: string, sessionId: string, chunk: string) => void;
  clearTerminalBuffer: (conversationId: string, sessionId?: string) => void;
  setActiveTerminalSession: (conversationId: string, sessionId: string) => void;
  setConversationMode: (mode: 'chat' | 'agent') => void;
}

export const useStore = create<AppState>((set, get) => ({
  // Initial state
  conversations: [],
  selectedConversationId: null,
  draftWorkspacePath: typeof window !== 'undefined' ? (localStorage.getItem(WORKSPACE_STORAGE_KEY) || '') : '',
  draftConversationNonce: 0,
  workspacePaths: typeof window !== 'undefined'
    ? JSON.parse(localStorage.getItem(WORKSPACE_LIST_STORAGE_KEY) || '[]')
    : [],
  runsByConversation: {},
  eventsByRun: {},
  streamingRunId: null,
  streamingText: {},
  streamingThinking: {},
  isConnected: false,
  isLoading: false,
  error: null,
  fetchingRuns: new Set<string>(),
  agentRunState: {},
  terminalByConversation: {},
  conversationMode: 'agent',

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
    };
  }),

  selectConversation: (conversationId) => set({
    selectedConversationId: conversationId,
  }),

  setDraftWorkspacePath: (workspacePath) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(WORKSPACE_STORAGE_KEY, workspacePath);
    }
    set({ draftWorkspacePath: workspacePath });
  },

  bumpDraftConversation: () => set((state) => ({
    draftConversationNonce: state.draftConversationNonce + 1,
  })),

  rememberWorkspacePath: (workspacePath) => {
    const normalized = workspacePath.trim();
    if (!normalized) return;
    void ensureWorkspaceFluxionGitignore(normalized).catch(() => undefined);
    set((state) => {
      const next = [normalized, ...state.workspacePaths.filter((path) => path !== normalized)];
      if (typeof window !== 'undefined') {
        localStorage.setItem(WORKSPACE_LIST_STORAGE_KEY, JSON.stringify(next));
      }
      return { workspacePaths: next };
    });
  },

  // Run actions
  setRuns: (conversationId, runs) => set((state) => ({
    runsByConversation: {
      ...state.runsByConversation,
      [conversationId]: dedupeRuns(runs),
    },
  })),

  addRun: (conversationId, run) => set((state) => {
    const currentRuns = state.runsByConversation[conversationId] || [];
    if (currentRuns.some((existingRun) => existingRun.run_id === run.run_id)) {
      return state;
    }
    return {
      runsByConversation: {
        ...state.runsByConversation,
        [conversationId]: [...currentRuns, run],
      },
    };
  }),

  updateRun: (runId, updates) => set((state) => {
    for (const [conversationId, runs] of Object.entries(state.runsByConversation)) {
      if (!runs.some((run) => run.run_id === runId)) continue;

      const nextRuns = runs.map((run) => (
        run.run_id === runId ? { ...run, ...updates } : run
      ));
      return {
        runsByConversation: {
          ...state.runsByConversation,
          [conversationId]: dedupeRuns(nextRuns),
        },
      };
    }

    return state;
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
      streamingRunId: state.streamingRunId === runId ? null : state.streamingRunId,
    };
  }),

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

  initTerminalState: (conversationId, defaults) =>
    set((state) => {
      const base: TerminalUIState = {
        isOpen: false,
        dock: 'right',
        height: 260,
        width: 420,
        activeToolTabId: null,
        browserTabs: [],
        sessions: [],
        activeSessionId: null,
        maxSessionsPerConversation: 10,
        maxBrowserTabsPerConversation: 10,
        bufferBySessionId: {},
        session: null,
        buffer: '',
        connected: false,
        status: 'idle',
      };
      return {
        terminalByConversation: {
          ...state.terminalByConversation,
          [conversationId]: {
            ...base,
            ...(state.terminalByConversation[conversationId] ?? {}),
            ...(defaults ?? {}),
          },
        },
      };
    }),

  updateTerminalState: (conversationId, updates) =>
    set((state) => {
      const current = state.terminalByConversation[conversationId] ?? {
        isOpen: false,
        dock: 'right' as const,
        height: 260,
        width: 420,
        activeToolTabId: null,
        browserTabs: [],
        sessions: [],
        activeSessionId: null,
        maxSessionsPerConversation: 10,
        maxBrowserTabsPerConversation: 10,
        bufferBySessionId: {},
        session: null,
        buffer: '',
        connected: false,
        status: 'idle' as const,
      };
      const merged = { ...current, ...updates };
      if (updates.activeSessionId !== undefined || updates.sessions !== undefined) {
        const activeId = merged.activeSessionId;
        const activeSession = activeId
          ? merged.sessions.find((item) => item.session_id === activeId) ?? null
          : null;
        merged.session = activeSession;
        merged.buffer = activeId ? (merged.bufferBySessionId[activeId] ?? '') : '';
      }
      return {
        terminalByConversation: {
          ...state.terminalByConversation,
          [conversationId]: merged,
        },
      };
    }),

  setActiveTerminalSession: (conversationId, sessionId) =>
    set((state) => {
      const current = state.terminalByConversation[conversationId];
      if (!current) return state;
      const activeSession = current.sessions.find((item) => item.session_id === sessionId) ?? null;
      return {
        terminalByConversation: {
          ...state.terminalByConversation,
          [conversationId]: {
            ...current,
            activeSessionId: sessionId,
            session: activeSession,
            buffer: current.bufferBySessionId[sessionId] ?? '',
            connected: false,
            status: 'idle',
          },
        },
      };
    }),

  appendTerminalBuffer: (conversationId, sessionId, chunk) =>
    set((state) => {
      const current = state.terminalByConversation[conversationId];
      if (!current) return state;
      const prev = current.bufferBySessionId[sessionId] ?? '';
      const nextSessionBuffer = (prev + chunk).slice(-120000);
      const bufferBySessionId = {
        ...current.bufferBySessionId,
        [sessionId]: nextSessionBuffer,
      };
      const buffer =
        current.activeSessionId === sessionId ? nextSessionBuffer : current.buffer;
      return {
        terminalByConversation: {
          ...state.terminalByConversation,
          [conversationId]: { ...current, bufferBySessionId, buffer },
        },
      };
    }),

  clearTerminalBuffer: (conversationId, sessionId) =>
    set((state) => {
      const current = state.terminalByConversation[conversationId];
      if (!current) return state;
      const targetId = sessionId ?? current.activeSessionId;
      if (!targetId) {
        return {
          terminalByConversation: {
            ...state.terminalByConversation,
            [conversationId]: { ...current, buffer: '', bufferBySessionId: {} },
          },
        };
      }
      const bufferBySessionId = { ...current.bufferBySessionId, [targetId]: '' };
      const buffer = current.activeSessionId === targetId ? '' : current.buffer;
      return {
        terminalByConversation: {
          ...state.terminalByConversation,
          [conversationId]: { ...current, bufferBySessionId, buffer },
        },
      };
    }),

  setConversationMode: (mode) => set({ conversationMode: mode }),
}));

// Selectors
export const useSelectedConversation = () => {
  const conversations = useStore((s) => s.conversations);
  const selectedConversationId = useStore((s) => s.selectedConversationId);
  return conversations.find((c) => c.conversation_id === selectedConversationId);
};

export const useConversationRuns = (conversationId: string | null) => {
  return useStore((s) => (
    conversationId ? s.runsByConversation[conversationId] ?? EMPTY_RUNS : EMPTY_RUNS
  ));
};

export const useRunEvents = (runId: string | null) => {
  return useStore((s) => (
    runId ? s.eventsByRun[runId] ?? EMPTY_EVENTS : EMPTY_EVENTS
  ));
};

export const useAgentRunState = (runId: string | null) => {
  return useStore((s) => (runId ? s.agentRunState[runId] : undefined));
};

export const useConversationTerminal = (conversationId: string | null) => {
  return useStore((s) => (conversationId ? s.terminalByConversation[conversationId] : undefined));
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
