"""
M1.3: Deterministic tests for the tool-loop circuit breaker.

These tests validate the core logic of the circuit breaker:
1. A → A (same result) → third A is blocked.
2. A → B → A does NOT produce a false positive.
3. A(result X) → A(result Y) does NOT produce a false positive.

The tests replicate the JavaScript logic in Python for deterministic
verification without requiring a JS runtime.
"""

import json
import pytest


def stable_hash(value):
    """
    Replicate the JavaScript stableHash function.
    Creates a deterministic string representation of a value.
    """
    if value is None:
        return "null"
    if isinstance(value, str):
        return f"s:{value}"
    if isinstance(value, (int, float, bool)):
        return f"p:{str(value).lower() if isinstance(value, bool) else str(value)}"
    if isinstance(value, list):
        return f"a:[{','.join(stable_hash(v) for v in value)}]"
    if isinstance(value, dict):
        keys = sorted(value.keys())
        parts = [f"{k}:{stable_hash(value[k])}" for k in keys]
        return f"o:{{{','.join(parts)}}}"
    return f"u:{str(value)}"


def result_signature(output):
    """
    Replicate the JavaScript resultSignature function.
    Normalizes output to reduce false positives from minor formatting.
    """
    if not output:
        return "empty"
    # Normalize whitespace
    normalized = (
        output.replace("\r\n", "\n")
        .replace("\n\n\n", "\n\n")
        .replace("  ", " ")
        .strip()
    )
    # Collapse multiple spaces
    while "  " in normalized:
        normalized = normalized.replace("  ", " ")
    return stable_hash(normalized)


class SessionBreaker:
    """
    Python replica of the JavaScript SessionBreaker class.
    """

    THRESHOLD = 2  # Block on 3rd consecutive identical call

    def __init__(self):
        self.history = {}

    def record(self, session_id, tool, args, output):
        args_hash = stable_hash(args)
        result_hash = result_signature(output)

        if session_id not in self.history:
            self.history[session_id] = []

        self.history[session_id].append(
            {"tool": tool, "argsHash": args_hash, "resultHash": result_hash}
        )

        # Keep only the last 10 entries
        if len(self.history[session_id]) > 10:
            self.history[session_id].pop(0)

    def should_block(self, session_id, tool, args):
        args_hash = stable_hash(args)
        history = self.history.get(session_id, [])
        if len(history) < self.THRESHOLD:
            return False

        recent = history[-self.THRESHOLD:]

        # All recent entries must match the pending call in tool and args
        all_match_tool_args = all(
            entry["tool"] == tool and entry["argsHash"] == args_hash
            for entry in recent
        )

        if not all_match_tool_args:
            return False

        # Additionally, the last two results must be the same
        # If results differ, the tool is producing different output (not stuck)
        last_entry = recent[-1]
        prev_entry = recent[0]

        if last_entry["resultHash"] != prev_entry["resultHash"]:
            return False

        return True

    def get_last(self, session_id):
        history = self.history.get(session_id, [])
        if not history:
            return None
        return history[-1]

    def clear(self, session_id):
        self.history.pop(session_id, None)


class TestCircuitBreaker:
    """Tests for the circuit breaker logic."""

    def setup_method(self):
        self.breaker = SessionBreaker()

    def test_a_a_same_result_third_blocked(self):
        """
        A → A (same result) → third A is blocked.
        
        The breaker blocks the 3rd consecutive identical call. After 2
        identical calls are recorded, the next (3rd) call is blocked.
        """
        session = "session-1"
        tool = "bash"
        args = {"command": "ls -la"}
        result = "total 42\ndrwxr-xr-x 3 user user 4096 .\n-rw-r--r-- 1 user user 123 file.txt"

        # First call: record
        self.breaker.record(session, tool, args, result)
        # After 1 call, should not block (need 2 consecutive to trigger)
        assert not self.breaker.should_block(session, tool, args), "After 1st call, should not be blocked"

        # Second call: record
        self.breaker.record(session, tool, args, result)
        # After 2 identical calls, the 3rd call should be blocked
        assert self.breaker.should_block(session, tool, args), "After 2 identical calls, 3rd should be blocked"

    def test_a_b_a_no_false_positive(self):
        """
        A → B → A does NOT produce a false positive.
        """
        session = "session-2"
        tool_a = "bash"
        args_a = {"command": "ls -la"}
        result_a = "total 42\ndrwxr-xr-x 3 user user 4096 ."

        tool_b = "read"
        args_b = {"filePath": "/workspace/gastosE/AGENTS.md"}
        result_b = "# GastosE — Instrucciones de proyecto"

        # Call A
        self.breaker.record(session, tool_a, args_a, result_a)
        assert not self.breaker.should_block(session, tool_a, args_a), "First A should not be blocked"

        # Call B (different tool)
        self.breaker.record(session, tool_b, args_b, result_b)
        assert not self.breaker.should_block(session, tool_b, args_b), "First B should not be blocked"

        # Call A again (after B)
        assert not self.breaker.should_block(session, tool_a, args_a), "A after B should not be blocked"

        # Record the second A
        self.breaker.record(session, tool_a, args_a, result_a)

        # Third A (after A, B, A) should NOT be blocked because the last two are B and A
        assert not self.breaker.should_block(session, tool_a, args_a), "Third A after A,B,A should not be blocked"

    def test_a_result_x_a_result_y_no_false_positive(self):
        """
        A(result X) → A(result Y) does NOT produce a false positive.
        """
        session = "session-3"
        tool = "bash"
        args = {"command": "git status"}

        result_x = "On branch main\nnothing to commit, working tree clean"
        result_y = "On branch main\nChanges not staged for commit:\n  modified: file.txt"

        # Call A with result X
        self.breaker.record(session, tool, args, result_x)
        assert not self.breaker.should_block(session, tool, args), "First A should not be blocked"

        # Call A with result Y (different result)
        self.breaker.record(session, tool, args, result_y)
        assert not self.breaker.should_block(session, tool, args), "Second A with different result should not be blocked"

        # Third A should NOT be blocked because the last two results are different
        assert not self.breaker.should_block(session, tool, args), "Third A after different results should not be blocked"

    def test_different_args_no_block(self):
        """
        Different arguments should not trigger the breaker.
        """
        session = "session-4"
        tool = "bash"
        args_1 = {"command": "ls -la"}
        args_2 = {"command": "ls -la /tmp"}
        result = "total 42"

        self.breaker.record(session, tool, args_1, result)
        self.breaker.record(session, tool, args_2, result)

        # Third call with args_1 should NOT be blocked (last two are args_1 and args_2)
        assert not self.breaker.should_block(session, tool, args_1), "Different args should not trigger block"

    def test_session_isolation(self):
        """
        State should be independent per session.
        """
        session_1 = "session-5"
        session_2 = "session-6"
        tool = "bash"
        args = {"command": "ls"}
        result = "file.txt"

        # Record two calls in session_1
        self.breaker.record(session_1, tool, args, result)
        self.breaker.record(session_1, tool, args, result)

        # Session_1 should be blocked
        assert self.breaker.should_block(session_1, tool, args), "Session_1 should be blocked"

        # Session_2 should NOT be affected
        assert not self.breaker.should_block(session_2, tool, args), "Session_2 should not be affected"

    def test_history_bounded(self):
        """
        History should be bounded to prevent memory leaks.
        """
        session = "session-7"
        tool = "bash"
        args = {"command": "ls"}
        result = "file.txt"

        # Record more than 10 calls
        for _ in range(15):
            self.breaker.record(session, tool, args, result)

        # History should be bounded to 10
        assert len(self.breaker.history[session]) == 10, "History should be bounded to 10 entries"

    def test_clear_resets_state(self):
        """
        Clearing a session should reset its state.
        """
        session = "session-8"
        tool = "bash"
        args = {"command": "ls"}
        result = "file.txt"

        self.breaker.record(session, tool, args, result)
        self.breaker.record(session, tool, args, result)

        # Should be blocked
        assert self.breaker.should_block(session, tool, args), "Should be blocked before clear"

        # Clear the session
        self.breaker.clear(session)

        # Should no longer be blocked
        assert not self.breaker.should_block(session, tool, args), "Should not be blocked after clear"

    def test_stable_hash_deterministic(self):
        """
        stable_hash should produce deterministic output.
        """
        value = {"b": 2, "a": 1, "c": [1, 2, 3]}
        hash1 = stable_hash(value)
        hash2 = stable_hash(value)
        assert hash1 == hash2, "stable_hash should be deterministic"

    def test_stable_hash_key_order_independent(self):
        """
        stable_hash should not depend on key order.
        """
        value1 = {"a": 1, "b": 2}
        value2 = {"b": 2, "a": 1}
        assert stable_hash(value1) == stable_hash(value2), "stable_hash should be key-order independent"

    def test_result_signature_normalization(self):
        """
        result_signature should normalize whitespace.
        """
        output1 = "line1\n\n\nline2"
        output2 = "line1\n\nline2"
        assert result_signature(output1) == result_signature(output2), "result_signature should normalize whitespace"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
