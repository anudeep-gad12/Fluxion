// Zustand store for application state

import { create } from 'zustand';
import type { Run, Event, Conversation } from '@/types';

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

  // Connection state
  isConnected: boolean;
  isLoading: boolean;
  error: string | null;

  // Fetch tracking to prevent duplicate requests
  fetchingRuns: Set<string>;

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

  // Fetch tracking actions
  setFetching: (runId: string, fetching: boolean) => void;
  isFetchingRun: (runId: string) => boolean;
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
  isConnected: false,
  isLoading: false,
  error: null,
  fetchingRuns: new Set<string>(),

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
