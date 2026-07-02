/**
 * Run footer meta row (status pill + metrics + actions) shared by run renderers.
 */

import type { ReactNode } from 'react';

export function RunFooter({
  pillClassName,
  dataStatus,
  statusLabel,
  metrics,
  actions,
}: {
  pillClassName: string;
  dataStatus: string;
  statusLabel: ReactNode;
  metrics: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="desktop-run-meta mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-1 font-mono text-[11px]">
      <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-zinc-500">
        <span className={pillClassName} data-status={dataStatus}>
          {statusLabel}
        </span>
        {metrics}
      </div>
      {actions}
    </div>
  );
}
