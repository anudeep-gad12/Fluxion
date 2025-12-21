// Retry utility with exponential backoff

interface RetryOptions {
  maxRetries?: number;
  initialDelayMs?: number;
  maxDelayMs?: number;
  backoffFactor?: number;
}

/**
 * Wrap an async function with retry logic using exponential backoff.
 *
 * @param fn - The async function to retry
 * @param options - Retry configuration options
 * @returns The result of the function if it succeeds within retry limit
 * @throws The last error if all retries are exhausted
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const {
    maxRetries = 3,
    initialDelayMs = 1000,
    maxDelayMs = 10000,
    backoffFactor = 2,
  } = options;

  let lastError: Error | null = null;
  let delay = initialDelayMs;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error as Error;

      // Don't retry on the last attempt
      if (attempt < maxRetries) {
        // Wait before next attempt
        await new Promise((resolve) => setTimeout(resolve, delay));
        // Increase delay for next attempt (exponential backoff)
        delay = Math.min(delay * backoffFactor, maxDelayMs);
      }
    }
  }

  // All retries exhausted, throw the last error
  throw lastError;
}
