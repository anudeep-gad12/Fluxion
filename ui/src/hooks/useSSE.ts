// SSE hook for streaming run events

import { useEffect, useRef, useCallback } from 'react';
import { subscribeToRun } from '@/api/client';
import { useStore } from './useStore';
import type { Event } from '@/types';

export function useSSE(runId: string | null) {
  const unsubscribeRef = useRef<(() => void) | null>(null);
  // Buffer for early events that arrive before store is ready
  const eventBufferRef = useRef<Event[]>([]);

  const addEvent = useStore((s) => s.addEvent);
  const setEvents = useStore((s) => s.setEvents);
  const updateRun = useStore((s) => s.updateRun);
  const setConnected = useStore((s) => s.setConnected);
  const setError = useStore((s) => s.setError);
  const setStreamingRunId = useStore((s) => s.setStreamingRunId);
  const appendStreamingText = useStore((s) => s.appendStreamingText);
  const clearStreamingText = useStore((s) => s.clearStreamingText);
  const appendStreamingThinking = useStore((s) => s.appendStreamingThinking);
  const clearStreamingThinking = useStore((s) => s.clearStreamingThinking);

  const subscribe = useCallback((id: string) => {
    // Unsubscribe from previous
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
    }

    // Clear buffer for new subscription
    eventBufferRef.current = [];

    // Clear any previous streaming text and thinking for this run
    clearStreamingText(id);
    clearStreamingThinking(id);

    setConnected(true);
    setError(null);
    setStreamingRunId(id);

    const handleEvent = (event: Event) => {
      // Handle TOKEN events for streaming text
      // TOKEN events have content directly on the event object
      const rawEvent = event as unknown as { type: string; content?: string };

      if (rawEvent.type === 'TOKEN' && rawEvent.content) {
        appendStreamingText(id, rawEvent.content);
        return; // Don't add TOKEN events to event list
      }

      // Handle THINKING_TOKEN events for streaming thinking content
      if (rawEvent.type === 'THINKING_TOKEN' && rawEvent.content) {
        appendStreamingThinking(id, rawEvent.content);
        return; // Don't add THINKING_TOKEN events to event list
      }

      // Check if store has this run's events initialized
      const currentEvents = useStore.getState().eventsByRun[id];
      if (currentEvents === undefined) {
        // Buffer event until store is ready
        eventBufferRef.current.push(event);
      } else {
        // Flush buffer first if any
        if (eventBufferRef.current.length > 0) {
          const allEvents = [...eventBufferRef.current, event];
          setEvents(id, allEvents);
          eventBufferRef.current = [];
        } else {
          addEvent(id, event);
        }
      }
    };

    const handleComplete = (result: {
      run_id: string;
      status: string;
      final_answer?: string;
      thinking_summary?: string;
      error_message?: string;
    }) => {
      // Flush any remaining buffered events
      if (eventBufferRef.current.length > 0) {
        setEvents(id, eventBufferRef.current);
        eventBufferRef.current = [];
      }

      // Clear streaming text and thinking now that we have final answer
      clearStreamingText(id);
      clearStreamingThinking(id);

      updateRun(result.run_id, {
        status: result.status as 'succeeded' | 'failed' | 'cancelled' | 'interrupted',
        final_answer: result.final_answer,
        thinking_summary: result.thinking_summary,
        error_detail:
          result.status === 'interrupted'
            ? result.error_message || 'Run interrupted by server restart'
            : result.status === 'failed'
              ? result.error_message
              : undefined,
      });
      setConnected(false);
      setStreamingRunId(null);
    };

    const handleError = (error: string) => {
      // Flush any remaining buffered events even on error
      if (eventBufferRef.current.length > 0) {
        setEvents(id, eventBufferRef.current);
        eventBufferRef.current = [];
      }

      // Clear streaming text and thinking on error
      clearStreamingText(id);
      clearStreamingThinking(id);

      setError(error);
      setConnected(false);
      setStreamingRunId(null);
    };

    unsubscribeRef.current = subscribeToRun(
      id,
      handleEvent,
      handleComplete,
      handleError
    );
  }, [addEvent, setEvents, updateRun, setConnected, setError, setStreamingRunId, appendStreamingText, clearStreamingText, appendStreamingThinking, clearStreamingThinking]);

  const unsubscribe = useCallback(() => {
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
      unsubscribeRef.current = null;
    }
    setConnected(false);
    setStreamingRunId(null);
  }, [setConnected, setStreamingRunId]);

  useEffect(() => {
    if (runId) {
      subscribe(runId);
    }

    return () => {
      unsubscribe();
    };
  }, [runId, subscribe, unsubscribe]);

  return { subscribe, unsubscribe };
}
