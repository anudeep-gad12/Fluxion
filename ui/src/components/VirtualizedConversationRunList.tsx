import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react';
import type { Run } from '@/types';

const DEFAULT_ESTIMATED_ROW_HEIGHT = 420;
const DEFAULT_OVERSCAN = 6;
const DEFAULT_THRESHOLD = 40;
const ROW_GAP_PX = 32;

interface VirtualizedConversationRunListProps {
  runs: Run[];
  scrollContainerRef: RefObject<HTMLDivElement | null>;
  renderRun: (run: Run) => ReactNode;
  virtualizeThreshold?: number;
  overscan?: number;
}

function binarySearchOffset(offsets: number[], target: number): number {
  let low = 0;
  let high = offsets.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const current = offsets[mid] ?? 0;
    const next = offsets[mid + 1] ?? Number.POSITIVE_INFINITY;
    if (target < current) {
      high = mid - 1;
    } else if (target >= next) {
      low = mid + 1;
    } else {
      return mid;
    }
  }

  return Math.max(0, Math.min(offsets.length - 1, low));
}

const MeasuredRow = memo(function MeasuredRow({
  runId,
  top,
  onHeightChange,
  children,
}: {
  runId: string;
  top: number;
  onHeightChange: (runId: string, height: number) => void;
  children: ReactNode;
}) {
  const rowRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const el = rowRef.current;
    if (!el) return;

    const measure = () => {
      onHeightChange(runId, el.offsetHeight);
    };

    measure();

    if (typeof ResizeObserver === 'undefined') {
      return;
    }

    const observer = new ResizeObserver(() => {
      measure();
    });
    observer.observe(el);

    return () => observer.disconnect();
  }, [onHeightChange, runId]);

  return (
    <div
      ref={rowRef}
      className="absolute left-0 right-0 pb-8"
      style={{ top }}
      data-run-id={runId}
    >
      {children}
    </div>
  );
});

export const VirtualizedConversationRunList = memo(function VirtualizedConversationRunList({
  runs,
  scrollContainerRef,
  renderRun,
  virtualizeThreshold = DEFAULT_THRESHOLD,
  overscan = DEFAULT_OVERSCAN,
}: VirtualizedConversationRunListProps) {
  const shouldVirtualize = runs.length >= virtualizeThreshold;
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);
  const [measuredHeights, setMeasuredHeights] = useState<Record<string, number>>({});

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const updateMetrics = () => {
      setScrollTop(container.scrollTop);
      setViewportHeight(container.clientHeight);
    };

    updateMetrics();
    container.addEventListener('scroll', updateMetrics, { passive: true });

    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', updateMetrics);
      return () => {
        container.removeEventListener('scroll', updateMetrics);
        window.removeEventListener('resize', updateMetrics);
      };
    }

    const observer = new ResizeObserver(() => {
      updateMetrics();
    });
    observer.observe(container);

    return () => {
      container.removeEventListener('scroll', updateMetrics);
      observer.disconnect();
    };
  }, [scrollContainerRef]);

  useEffect(() => {
    setMeasuredHeights((current) => {
      const activeRunIds = new Set(runs.map((run) => run.run_id));
      let changed = false;
      const next: Record<string, number> = {};
      for (const [runId, height] of Object.entries(current)) {
        if (activeRunIds.has(runId)) {
          next[runId] = height;
        } else {
          changed = true;
        }
      }
      return changed ? next : current;
    });
  }, [runs]);

  const handleHeightChange = useCallback((runId: string, height: number) => {
    setMeasuredHeights((current) => {
      if (current[runId] === height) return current;
      return { ...current, [runId]: height };
    });
  }, []);

  const { totalHeight, visibleRuns } = useMemo(() => {
    if (!shouldVirtualize) {
      return {
        totalHeight: 0,
        visibleRuns: runs.map((run) => ({ run, top: 0 })),
      };
    }

    const offsets: number[] = new Array(runs.length);
    let runningOffset = 0;
    for (let index = 0; index < runs.length; index += 1) {
      offsets[index] = runningOffset;
      const run = runs[index];
      const measuredHeight = measuredHeights[run.run_id];
      runningOffset += (measuredHeight ?? DEFAULT_ESTIMATED_ROW_HEIGHT) + ROW_GAP_PX;
    }
    const computedTotalHeight = Math.max(0, runningOffset - ROW_GAP_PX);

    if (!runs.length) {
      return {
        totalHeight: computedTotalHeight,
        visibleRuns: [] as Array<{ run: Run; top: number }>,
      };
    }

    const viewportEnd = scrollTop + Math.max(viewportHeight, 1);
    const startIndex = binarySearchOffset(offsets, Math.max(0, scrollTop));
    const endIndex = binarySearchOffset(offsets, Math.max(0, viewportEnd));
    const visibleStart = Math.max(0, startIndex - overscan);
    const visibleEnd = Math.min(runs.length - 1, endIndex + overscan);

    return {
      totalHeight: computedTotalHeight,
      visibleRuns: runs.slice(visibleStart, visibleEnd + 1).map((run, relativeIndex) => {
        const index = visibleStart + relativeIndex;
        return {
          run,
          top: offsets[index] ?? 0,
        };
      }),
    };
  }, [measuredHeights, overscan, runs, scrollTop, shouldVirtualize, viewportHeight]);

  if (!shouldVirtualize) {
    return <div className="space-y-8">{runs.map((run) => renderRun(run))}</div>;
  }

  return (
    <div style={{ height: totalHeight, position: 'relative' }}>
      {visibleRuns.map(({ run, top }) => (
        <MeasuredRow
          key={run.run_id}
          runId={run.run_id}
          top={top}
          onHeightChange={handleHeightChange}
        >
          {renderRun(run)}
        </MeasuredRow>
      ))}
    </div>
  );
});
