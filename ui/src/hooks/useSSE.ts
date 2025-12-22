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

  const subscribe = useCallback((id: string) => {
    // Unsubscribe from previous
    if (unsubscribeRef.current) {
      unsubscribeRef.current();
    }

    // Clear buffer for new subscription
    eventBufferRef.current = [];

    // Clear any previous streaming text for this run
    clearStreamingText(id);

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

    const handleComplete = (result: { run_id: string; status: string; final_answer?: string }) => {
      // Flush any remaining buffered events
      if (eventBufferRef.current.length > 0) {
        setEvents(id, eventBufferRef.current);
        eventBufferRef.current = [];
      }

      // Clear streaming text now that we have final answer
      clearStreamingText(id);

      updateRun(result.run_id, {
        status: result.status as 'succeeded' | 'failed',
        final_answer: result.final_answer,
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

      // Clear streaming text on error
      clearStreamingText(id);

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
  }, [addEvent, setEvents, updateRun, setConnected, setError, setStreamingRunId, appendStreamingText, clearStreamingText]);

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
