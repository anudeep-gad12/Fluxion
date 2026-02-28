import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatRelativeTime(ts: string): string {
  const date = new Date(ts);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  if (diff < 60000) {
    return 'just now';
  } else if (diff < 3600000) {
    const mins = Math.floor(diff / 60000);
    return `${mins}m ago`;
  } else if (diff < 86400000) {
    const hours = Math.floor(diff / 3600000);
    return `${hours}h ago`;
  } else {
    return date.toLocaleDateString();
  }
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

/**
 * Strip structured/machine-readable content from thinking text.
 *
 * Model/provider agnostic — handles any model that puts structured
 * tool call instructions inside reasoning tokens (Qwen XML, Harmony, etc.)
 */
export function sanitizeThinking(content: string): string {
  if (!content) return '';
  return content
    // Think wrapper tags
    .replace(/\[\s*\/?\s*THINK\s*\]/gi, '')
    .replace(/<\s*\/?\s*think\s*>/gi, '')
    // Completed XML tool call blocks (Qwen, generic)
    .replace(/<tool_call>[\s\S]*?<\/tool_call>/g, '')
    .replace(/<function_call>[\s\S]*?<\/function_call>/g, '')
    .replace(/<tool_use>[\s\S]*?<\/tool_use>/g, '')
    // Harmony-style tool call blocks (gpt-oss)
    .replace(/◁tool_call▷[\s\S]*?◁\/tool_call▷/g, '')
    // Incomplete/in-progress blocks (still streaming, no closing tag yet)
    .replace(/<(?:tool_call|function_call|tool_use)>[\s\S]*$/g, '')
    .replace(/◁(?:tool_call)▷[\s\S]*$/g, '')
    // Clean up leftover blank lines
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}
