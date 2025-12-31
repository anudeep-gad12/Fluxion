// Detail panel - raw trace view for debugging (developer only)
// This shows ALL events including internal state, for debugging purposes

import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useRunEvents, useSelectedRun, useStore } from '@/hooks/useStore';
import { cn } from '@/lib/utils';
import { Braces, Copy, X, Bug, Eye, EyeOff } from 'lucide-react';
import { getRun, getRunTimeline, type TraceEvent } from '@/api/client';
import type { Event } from '@/types';

export function DetailPanel() {
  const detailPanelOpen = useStore((s) => s.detailPanelOpen);
  const selectedEventSeq = useStore((s) => s.selectedEventSeq);
  const selectedRunId = useStore((s) => s.selectedRunId);
  const setDetailPanelOpen = useStore((s) => s.setDetailPanelOpen);
  const selectEvent = useStore((s) => s.selectEvent);
  const setEvents = useStore((s) => s.setEvents);
  const setFetching = useStore((s) => s.setFetching);
  const isFetchingRun = useStore((s) => s.isFetchingRun);
  const updateRun = useStore((s) => s.updateRun);
  const events = useRunEvents(selectedRunId);
  const selectedRun = useSelectedRun();
  const selectedEvent = events.find((e) => e.seq === selectedEventSeq);
  const [viewMode, setViewMode] = useState<'trace' | 'event'>('trace');
  const [showInternal, setShowInternal] = useState(true); // Show all events by default in debug view

  // Track which runId we've loaded events for to prevent stale state
  const loadedRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedRunId) {
      loadedRunIdRef.current = null;
      return;
    }

    // Skip if already loaded for this run AND events exist
    if (loadedRunIdRef.current === selectedRunId && events.length > 0) {
      return;
    }

    // Skip if currently fetching this run
    if (isFetchingRun(selectedRunId)) {
      return;
    }

    async function loadEvents() {
      setFetching(selectedRunId!, true);
      try {
        // Use timeline endpoint for trace events (llm_request, llm_response, etc.)
        const timeline = await getRunTimeline(selectedRunId!);
        // Convert TraceEvent[] to Event[] for the store
        const events: Event[] = timeline.events.map((te: TraceEvent) => ({
          run_id: te.run_id,
          seq: te.seq,
          ts: te.created_at,
          type: te.event_type,
          display: {
            title: te.event_type,
            summary: te.error_message || `${te.actor} - ${te.event_status}`,
            status: te.event_status,
            result_preview: te.duration_ms ? `${te.duration_ms}ms` : undefined,
          },
          payload: {
            ...te.content,
            actor: te.actor,
            endpoint: te.endpoint,
            attempt: te.attempt,
            step_number: te.step_number,
            duration_ms: te.duration_ms,
            token_count: te.token_count,
            error_message: te.error_message,
          },
        }));
        setEvents(selectedRunId!, events);
        loadedRunIdRef.current = selectedRunId;
      } catch (error) {
        console.error('Failed to load trace events:', error);
      } finally {
        setFetching(selectedRunId!, false);
      }
    }
    loadEvents();
  }, [selectedRunId, setEvents, setFetching, isFetchingRun]);

  useEffect(() => {
    if (!selectedRunId) return;
    async function loadRun() {
      try {
        const run = await getRun(selectedRunId);
        updateRun(selectedRunId, run);
      } catch (error) {
        console.error('Failed to load run metadata:', error);
      }
    }
    loadRun();
  }, [selectedRunId, updateRun]);

  // Filter events based on showInternal toggle
  const filteredEvents = useMemo(() => {
    if (showInternal) return events;
    return events.filter((e: Event) => {
      const category = (e.display as Record<string, unknown>)?.category;
      return category !== 'internal';
    });
  }, [events, showInternal]);

  const traceJson = useMemo(() => JSON.stringify(filteredEvents, null, 2), [filteredEvents]);
  const eventJson = useMemo(
    () => JSON.stringify(selectedEvent, null, 2),
    [selectedEvent]
  );

  const stageSummary = useMemo(() => {
    const stages: string[] = [];
    for (const event of events) {
      if (event.type === 'STAGE_STARTED') {
        const stage = (event.payload as { stage?: string })?.stage;
        if (stage && stages[stages.length - 1] !== stage) {
          stages.push(stage);
        }
      }
    }
    return stages.length ? stages.join(' -> ') : '';
  }, [events]);

  const handleCopy = async (mode: 'trace' | 'event') => {
    const data = mode === 'trace' ? traceJson : eventJson;
    if (!data) return;
    await navigator.clipboard.writeText(data);
  };

  return (
    <>
      {!detailPanelOpen && (
        <button
          className="fixed right-4 top-1/2 -translate-y-1/2 bg-slate-900 text-white px-3 py-2 rounded-md shadow-lg text-sm"
          onClick={() => setDetailPanelOpen(true)}
          title="Show raw trace"
        >
          Trace
        </button>
      )}

      <div
        className={cn(
          "fixed right-0 top-0 h-full w-[420px] border-l bg-white shadow-xl transition-transform duration-300 z-50",
          detailPanelOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b bg-amber-50">
          <div>
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <Bug className="h-4 w-4 text-amber-600" />
              Debug Trace
              <span className="text-xs bg-amber-200 text-amber-800 px-1.5 py-0.5 rounded">
                Dev Only
              </span>
            </h3>
            {selectedRunId && (
              <p className="text-xs text-slate-500 mt-1">Run {selectedRunId}</p>
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={() => setDetailPanelOpen(false)}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="px-4 py-3 border-b space-y-2">
          <div className="flex gap-2">
            <Button
              size="sm"
              variant={viewMode === 'trace' ? 'default' : 'outline'}
              onClick={() => setViewMode('trace')}
            >
              Full Trace
            </Button>
            <Button
              size="sm"
              variant={viewMode === 'event' ? 'default' : 'outline'}
              onClick={() => setViewMode('event')}
              disabled={!selectedEvent}
            >
              Selected Event
            </Button>
          </div>
          {selectedRun && (
            <div className="text-xs text-slate-600 space-y-1">
              {selectedRun.user_message && (
                <div>
                  <span className="font-medium">User:</span> {selectedRun.user_message}
                </div>
              )}
              {selectedRun.conversation_summary && (
                <div>
                  <span className="font-medium">Summary:</span> {selectedRun.conversation_summary}
                </div>
              )}
            </div>
          )}
          {stageSummary && (
            <div className="text-xs text-slate-500">
              Stages: {stageSummary}
            </div>
          )}
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowInternal(!showInternal)}
              className="text-xs"
            >
              {showInternal ? (
                <>
                  <Eye className="h-3 w-3 mr-1" />
                  All Events ({events.length})
                </>
              ) : (
                <>
                  <EyeOff className="h-3 w-3 mr-1" />
                  User-Facing ({filteredEvents.length})
                </>
              )}
            </Button>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => handleCopy(viewMode)}
              disabled={viewMode === 'event' && !selectedEvent}
            >
              <Copy className="h-4 w-4" />
              Copy JSON
            </Button>
            {selectedEvent && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => selectEvent(null)}
              >
                Clear Selection
              </Button>
            )}
          </div>
        </div>

        <ScrollArea className="h-[calc(100%-200px)]">
          <div className="p-4">
            {selectedRunId ? (
              <pre className="text-xs whitespace-pre-wrap break-words bg-slate-50 border rounded-md p-3">
                {viewMode === 'trace' ? traceJson : eventJson || 'Select an event to view details.'}
              </pre>
            ) : (
              <div className="text-sm text-slate-500">
                Select a message to see raw trace data.
              </div>
            )}
          </div>
        </ScrollArea>
      </div>

      {detailPanelOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40"
          onClick={() => setDetailPanelOpen(false)}
        />
      )}
    </>
  );
}
