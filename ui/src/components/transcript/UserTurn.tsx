/**
 * User message turn shared by chat and agent run renderers.
 */

import { ImagePreviewStrip } from '@/components/ImagePreviewStrip';
import { formatRelativeTime } from '@/lib/utils';
import type { Run } from '@/types';

export function UserTurn({ run }: { run: Run }) {
  return (
    <div className="desktop-run">
      <div className="min-w-0 flex-1">
        <div className="desktop-message-card fluxion-card rounded-[1.35rem] border px-6 py-5">
          <span className="whitespace-pre-wrap text-[14px] leading-[1.9] text-zinc-50">
            {run.user_message || run.prompt}
          </span>
          <ImagePreviewStrip
            images={run.image_attachments}
            className="mt-3"
            thumbnailClassName="h-20 w-20"
          />
        </div>
        <p className="desktop-run-meta mt-2 px-1 text-[11px] text-zinc-500">
          {formatRelativeTime(run.created_at)}
        </p>
      </div>
    </div>
  );
}
