import { useState } from 'react';
import { X } from 'lucide-react';
import { Tooltip } from '@/components/ui/tooltip';
import type { ImageAttachment } from '@/types';
import { cn } from '@/lib/utils';

interface ImagePreviewStripProps {
  images?: ImageAttachment[] | null;
  className?: string;
  thumbnailClassName?: string;
  onRemove?: (id?: string) => void;
}

export function ImagePreviewStrip({
  images,
  className,
  thumbnailClassName,
  onRemove,
}: ImagePreviewStripProps) {
  const visibleImages = (images || []).filter((image) => image?.data_url);
  const [preview, setPreview] = useState<ImageAttachment | null>(null);

  if (visibleImages.length === 0) return null;

  return (
    <>
      <div className={cn('flex flex-wrap gap-2', className)}>
        {visibleImages.map((image, index) => (
          <div key={image.id || `${image.name}-${index}`} className="group relative">
            <button
              type="button"
              onClick={() => setPreview(image)}
              className={cn(
                'block overflow-hidden rounded-lg border border-[var(--desktop-border-strong)] bg-[var(--desktop-hover)] hover:border-cyan-400/40',
                thumbnailClassName || 'h-16 w-16'
              )}
              title={image.name || `Image ${index + 1}`}
            >
              <img
                src={image.data_url}
                alt={image.name || `Image ${index + 1}`}
                className="h-full w-full object-cover"
              />
            </button>
            {onRemove && (
              <Tooltip content="Remove image">
                <button
                  type="button"
                  onClick={() => onRemove(image.id)}
                  className="absolute -right-1.5 -top-1.5 flex h-4 w-4 items-center justify-center rounded-full border border-[var(--desktop-border-strong)] bg-[var(--desktop-panel-overlay)] text-[var(--desktop-text-secondary)] opacity-90 hover:text-[var(--desktop-text-primary)]"
                  aria-label="Remove image"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              </Tooltip>
            )}
          </div>
        ))}
      </div>

      {preview && (
        <div
          className="fixed inset-0 z-[var(--z-lightbox)] flex items-center justify-center bg-black/80 p-6"
          role="dialog"
          aria-modal="true"
          onClick={() => setPreview(null)}
        >
          <div className="max-h-full max-w-5xl" onClick={(event) => event.stopPropagation()}>
            <div className="mb-2 flex items-center justify-between gap-4 text-xs text-[var(--desktop-text-secondary)]">
              <span className="truncate">{preview.name}</span>
              <button
                type="button"
                onClick={() => setPreview(null)}
                className="rounded-md border border-[var(--desktop-border-strong)] px-2 py-1 hover:bg-[var(--desktop-hover-strong)]"
              >
                close
              </button>
            </div>
            <img
              src={preview.data_url}
              alt={preview.name || 'Image preview'}
              className="max-h-[82vh] max-w-full rounded-xl border border-[var(--desktop-border-strong)] object-contain"
            />
          </div>
        </div>
      )}
    </>
  );
}
