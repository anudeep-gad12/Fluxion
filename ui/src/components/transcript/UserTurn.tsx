/**
 * User message turn — Claude-Code style `>` line, no bubble.
 */

import { ImagePreviewStrip } from '@/components/ImagePreviewStrip';
import type { Run } from '@/types';

export function UserTurn({ run }: { run: Run }) {
  return (
    <div className="tr-user-turn">
      <div className="tr-line">
        <span className="tr-marker" aria-hidden>
          &gt;
        </span>
        <div className="tr-body tr-user-text">{run.user_message || run.prompt}</div>
      </div>
      {run.image_attachments && run.image_attachments.length > 0 && (
        <div className="tr-user-attachments">
          <ImagePreviewStrip images={run.image_attachments} thumbnailClassName="h-20 w-20" />
        </div>
      )}
    </div>
  );
}
