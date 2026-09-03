/**
 * M1.3: Deterministic tool-loop circuit breaker for GastosE multi-agent runtime.
 *
 * Detects consecutive repetitions of the same tool + equivalent arguments +
 * equivalent result within a session/agent, and blocks the third identical
 * execution to prevent infinite loops.
 *
 * Mechanism:
 * - `tool.execute.after` hook records each completed tool call (tool, args,
 *   result hash) per session.
 * - `permission.ask` hook checks if the pending tool call matches the last
 *   two recorded calls for that session. If so, it denies the permission.
 *
 * State is kept in-memory per session and resets when:
 * - A different tool is called.
 * - Arguments change materially.
 * - Result changes materially.
 */

const THRESHOLD = 2; // Block on 3rd consecutive identical call

/**
 * Create a stable hash of a value for comparison.
 * Uses JSON.stringify with sorted keys for deterministic output.
 */
function stableHash(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return `s:${value}`;
  if (typeof value === "number" || typeof value === "boolean") return `p:${String(value)}`;
  if (Array.isArray(value)) {
    return `a:[${value.map(stableHash).join(",")}]`;
  }
  if (typeof value === "object") {
    const keys = Object.keys(value).sort();
    const parts = keys.map((k) => `${k}:${stableHash(value[k])}`);
    return `o:{${parts.join(",")}}`;
  }
  return `u:${String(value)}`;
}

/**
 * Extract a comparable result signature from tool output.
 * Normalizes the output to reduce false positives from minor formatting
 * differences while preserving material changes.
 */
function resultSignature(output) {
  if (!output) return "empty";
  // Normalize whitespace: collapse multiple spaces/newlines
  const normalized = String(output)
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+/g, " ")
    .trim();
  return stableHash(normalized);
}

/**
 * Per-session state for the circuit breaker.
 */
class SessionBreaker {
  constructor() {
    // Map<sessionID, Array<{tool, argsHash, resultHash}>>
    this.history = new Map();
  }

  /**
   * Record a completed tool call.
   */
  record(sessionID, tool, args, output) {
    const argsHash = stableHash(args);
    const resultHash = resultSignature(output);

    if (!this.history.has(sessionID)) {
      this.history.set(sessionID, []);
    }

    const history = this.history.get(sessionID);
    history.push({ tool, argsHash, resultHash });

    // Keep only the last 10 entries to bound memory
    if (history.length > 10) {
      history.shift();
    }
  }

  /**
   * Check if the next call would be a 3rd consecutive identical call.
   * Returns true if the call should be blocked.
   *
   * A call is considered "identical" if it matches the last recorded call
   * in tool, args, AND result. This prevents false positives when the same
   * tool+args are called but produce different results (e.g., git status
   * after a file change).
   */
  shouldBlock(sessionID, tool, args) {
    const argsHash = stableHash(args);
    const history = this.history.get(sessionID);
    if (!history || history.length < THRESHOLD) {
      return false;
    }

    // Check the last THRESHOLD entries
    const recent = history.slice(-THRESHOLD);

    // All recent entries must match the pending call in tool and args
    const allMatchToolArgs = recent.every(
      (entry) => entry.tool === tool && entry.argsHash === argsHash
    );

    if (!allMatchToolArgs) {
      return false;
    }

    // Additionally, the last entry's result must match what we expect
    // (we can't know the future result, but if the last result was different
    // from the one before it, the loop is not "stuck")
    const lastEntry = recent[recent.length - 1];
    const prevEntry = recent[0];

    // If the last two results are different, the tool is producing different
    // output, so it's not a stuck loop
    if (lastEntry.resultHash !== prevEntry.resultHash) {
      return false;
    }

    return true;
  }

  /**
   * Get the last entry for reporting purposes.
   */
  getLast(sessionID) {
    const history = this.history.get(sessionID);
    if (!history || history.length === 0) return null;
    return history[history.length - 1];
  }

  /**
   * Clear state for a session (e.g., on session end).
   */
  clear(sessionID) {
    this.history.delete(sessionID);
  }
}

// Global breaker instance (shared across all sessions in this process)
const breaker = new SessionBreaker();

/**
 * Plugin entry point.
 * Returns hooks that intercept tool execution and permission requests.
 */
export default async () => {
  return {
    /**
     * Called after a tool completes. Records the call for loop detection.
     */
    "tool.execute.after": async (input, output) => {
      const { tool, sessionID, args } = input;
      const { output: toolOutput } = output;
      breaker.record(sessionID, tool, args, toolOutput);
    },

    /**
     * Called when a permission is requested. If the tool call matches the
     * last two recorded calls for this session, deny it to break the loop.
     */
    "permission.ask": async (input, output) => {
      const { sessionID, callID, metadata } = input;

      // Extract tool name and args from permission metadata if available
      // The permission object may contain tool info in metadata or title
      const toolName =
        metadata?.tool || metadata?.toolName || input.title?.match(/^(?:tool:)?(\w+)/)?.[1] || null;

      if (!toolName) {
        // Cannot determine tool; allow by default
        return;
      }

      // Try to extract args from metadata
      const args = metadata?.args || metadata?.arguments || {};

      if (breaker.shouldBlock(sessionID, toolName, args)) {
        const last = breaker.getLast(sessionID);
        output.status = "deny";
        // The deny reason is communicated via the permission system
        console.error(
          `[circuit-breaker] BLOCKED: session=${sessionID} tool=${toolName} ` +
          `callID=${callID} reason=3rd consecutive identical call ` +
          `(last: tool=${last?.tool}, argsHash=${last?.argsHash}, resultHash=${last?.resultHash})`
        );
      }
    },
  };
};
