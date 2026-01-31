// Modal for viewing GAIA benchmark evaluation traces

import { useState, useEffect } from 'react';
import { Dialog, DialogHeader, DialogTitle, DialogDescription, DialogContent } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { X, FileText, Target, CheckCircle } from 'lucide-react';

interface TraceMetadata {
  filename: string;
  timestamp: string;
  level: number;
  model: string;
  total_questions: number;
  correct: number;
  accuracy: number;
}

interface TraceResult {
  task_id: string;
  question: string;
  expected: string;
  agent_answer: string;
  agent_correct: boolean;
  agent_steps: number;
  agent_time_ms: number;
  error: string | null;
}

interface TraceDetail {
  metadata: {
    timestamp: string;
    level: number;
    model_name: string;
  };
  summary: {
    total_questions: number;
    agent_correct: number;
    agent_accuracy: number;
    agent_avg_steps: number;
    agent_avg_time_ms: number;
  };
  results: TraceResult[];
}

interface TracesModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TracesModal({ open, onOpenChange }: TracesModalProps) {
  const [traces, setTraces] = useState<TraceMetadata[]>([]);
  const [selectedTrace, setSelectedTrace] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch traces list when modal opens
  useEffect(() => {
    if (open && traces.length === 0) {
      fetchTraces();
    }
  }, [open]);

  const fetchTraces = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/benchmarks/traces');
      if (!response.ok) throw new Error('Failed to fetch traces');
      const data = await response.json();

      // Filter to show only full evaluation runs (>= 19 questions)
      // Then select the best (highest accuracy) for each model+level combination
      const fullRuns = data.filter((trace: TraceMetadata) => trace.total_questions >= 19);

      const bestByModelLevel = new Map<string, TraceMetadata>();
      fullRuns.forEach((trace: TraceMetadata) => {
        const key = `${trace.model}__${trace.level}`;
        const existing = bestByModelLevel.get(key);
        if (!existing || trace.accuracy > existing.accuracy) {
          bestByModelLevel.set(key, trace);
        }
      });

      // Convert to array and sort by model (GPT-5-mini first) then level
      const bestTraces = Array.from(bestByModelLevel.values()).sort((a, b) => {
        // GPT-5-mini first, then gpt-oss-120b
        if (a.model !== b.model) {
          return a.model?.includes('5-mini') ? -1 : 1;
        }
        return a.level - b.level;
      });
      setTraces(bestTraces);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load traces');
    } finally {
      setLoading(false);
    }
  };

  const fetchTraceDetail = async (filename: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/benchmarks/traces/${filename}`);
      if (!response.ok) throw new Error('Failed to fetch trace details');
      const data = await response.json();
      setSelectedTrace(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trace details');
    } finally {
      setLoading(false);
    }
  };

  const handleTraceClick = (trace: TraceMetadata) => {
    fetchTraceDetail(trace.filename);
  };

  const handleBack = () => {
    setSelectedTrace(null);
  };

  const formatDate = (timestamp: string) => {
    return new Date(timestamp).toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <div className="relative bg-white rounded-lg shadow-xl max-w-5xl w-full mx-4 max-h-[85vh] flex flex-col animate-in fade-in zoom-in-95">
        <DialogHeader className="border-b flex-shrink-0">
          <div className="flex items-center justify-between">
            <div>
              <DialogTitle>
                {selectedTrace ? `Evaluation Trace - Level ${selectedTrace.metadata.level}` : 'Evaluation Traces'}
              </DialogTitle>
              <DialogDescription>
                {selectedTrace
                  ? `${selectedTrace.summary.total_questions} questions · ${formatDate(selectedTrace.metadata.timestamp)}`
                  : 'Full evaluation runs for each difficulty level with aggregate statistics'}
              </DialogDescription>
            </div>
            <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </DialogHeader>

        <DialogContent className="flex-1 overflow-y-auto">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-md p-4 text-sm text-red-800">
              {error}
            </div>
          )}

          {loading && !selectedTrace && (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          )}

          {/* Traces List View */}
          {!selectedTrace && !loading && traces.length > 0 && (
            <div className="space-y-4">
              {/* Group traces by model */}
              {(() => {
                const models = [...new Set(traces.map(t => t.model))];
                return models.map((model) => (
                  <div key={model} className="space-y-2">
                    <h3 className="text-sm font-medium text-muted-foreground px-1">{model}</h3>
                    {traces.filter(t => t.model === model).map((trace) => (
                      <button
                        key={trace.filename}
                        onClick={() => handleTraceClick(trace)}
                        className="w-full text-left p-4 rounded-lg border hover:bg-slate-50 transition-colors"
                      >
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <Badge variant="default">
                                Level {trace.level}
                              </Badge>
                              <span className="text-sm text-muted-foreground">{formatDate(trace.timestamp)}</span>
                            </div>
                            <div className="flex items-center gap-4 text-sm">
                              <span className="flex items-center gap-1">
                                <Target className="h-3 w-3" />
                                {trace.total_questions} questions
                              </span>
                              <span className="flex items-center gap-1">
                                <CheckCircle className="h-3 w-3 text-green-600" />
                                {trace.correct} correct
                              </span>
                              <span className="font-medium text-blue-600">
                                {(trace.accuracy * 100).toFixed(1)}%
                              </span>
                            </div>
                          </div>
                          <FileText className="h-5 w-5 text-slate-400" />
                        </div>
                      </button>
                    ))}
                  </div>
                ));
              })()}
            </div>
          )}

          {/* Trace Detail View */}
          {selectedTrace && !loading && (
            <div className="space-y-4">
              {/* Back button */}
              <Button variant="outline" size="sm" onClick={handleBack}>
                ← Back to list
              </Button>

              {/* Summary */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 p-4 bg-slate-50 rounded-lg">
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Questions</div>
                  <div className="text-2xl font-bold">{selectedTrace.summary.total_questions}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Correct</div>
                  <div className="text-2xl font-bold text-green-600">{selectedTrace.summary.agent_correct}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Accuracy</div>
                  <div className="text-2xl font-bold text-blue-600">
                    {(selectedTrace.summary.agent_accuracy * 100).toFixed(1)}%
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Avg Time</div>
                  <div className="text-2xl font-bold text-slate-700">
                    {formatDuration(selectedTrace.summary.agent_avg_time_ms)}
                  </div>
                </div>
              </div>
            </div>
          )}

          {!loading && !selectedTrace && traces.length === 0 && !error && (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>No evaluation traces found</p>
            </div>
          )}
        </DialogContent>
      </div>
    </Dialog>
  );
}
