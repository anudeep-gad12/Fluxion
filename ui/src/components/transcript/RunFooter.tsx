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
    <div className="desktop-run-meta">
      <div className="desktop-run-metrics">
        <span className={pillClassName} data-status={dataStatus}>
          {statusLabel}
        </span>
        {metrics}
      </div>
      {actions}
    </div>
  );
}
