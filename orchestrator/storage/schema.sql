-- Core Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    workspace_path TEXT,
    status TEXT NOT NULL, -- active, archived, closed
    metadata_json TEXT
);

-- Runs (one row per chat turn/message exchange or eval sample)
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT,  -- NULL for eval runs
    created_at TEXT NOT NULL,

    -- Inputs
    user_message TEXT,
    system_prompt_snapshot TEXT, -- Full exact system prompt used

    -- Config
    profile_name TEXT NOT NULL,
    mode TEXT NOT NULL, -- chat, eval
    model_config_snapshot TEXT NOT NULL, -- JSON: temp, max_tokens, etc.

    -- Outputs
    final_answer TEXT,
    thinking_summary TEXT, -- Cleaned thinking for UI display
    error_message TEXT,
    status TEXT NOT NULL, -- running, succeeded, failed

    -- Context management
    turn_summary TEXT, -- Compact context string for cross-turn history

    -- Stateful mode support
    last_response_id TEXT, -- Response ID from /v1/responses for stateful chaining

    -- Telemetry
    usage_stats TEXT, -- JSON: {"input_tokens": 100, "output_tokens": 50, "latency_ms": 1200}
    rewound_at TEXT,
    rewind_group_id TEXT,

    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_conversation_id ON runs(conversation_id);

-- =============================================================================
-- Evaluation Tables
-- =============================================================================

-- Eval runs (benchmark execution sessions)
CREATE TABLE IF NOT EXISTS eval_runs (
    eval_run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,

    -- Configuration
    benchmark_name TEXT NOT NULL,     -- "gpqa_diamond", "mmlu_pro", etc.
    model_id TEXT NOT NULL,           -- Model identifier
    policy_name TEXT NOT NULL,        -- "direct", "vote", "cot", "solve_verify"
    policy_config_json TEXT,          -- Full policy configuration snapshot

    -- Progress tracking
    status TEXT NOT NULL,             -- running, completed, failed, cancelled
    total_samples INT NOT NULL,
    completed_samples INT DEFAULT 0,

    -- Aggregate results
    accuracy REAL,                    -- Final accuracy (0.0 - 1.0)
    avg_tokens_per_sample REAL,
    total_duration_ms INT,
    results_json TEXT,                -- Detailed aggregate results

    -- Error handling
    error_message TEXT
);

-- Individual eval samples (linked to full traces)
CREATE TABLE IF NOT EXISTS eval_samples (
    sample_id TEXT PRIMARY KEY,
    eval_run_id TEXT NOT NULL,
    created_at TEXT NOT NULL,

    -- Question data
    question_id TEXT NOT NULL,        -- ID from benchmark dataset
    question_text TEXT NOT NULL,
    correct_answer TEXT NOT NULL,

    -- Model response
    model_answer TEXT,
    is_correct BOOLEAN,

    -- Link to full trace (runs + trace_events)
    run_id TEXT,                      -- Links to runs table for full trace

    -- Metrics
    thinking_tokens INT,
    answer_tokens INT,
    total_tokens INT,
    duration_ms INT,

    -- Status
    status TEXT NOT NULL,             -- pending, running, completed, failed
    error_message TEXT,

    FOREIGN KEY(eval_run_id) REFERENCES eval_runs(eval_run_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

-- Eval indexes
CREATE INDEX IF NOT EXISTS idx_eval_runs_created_at ON eval_runs(created_at);
CREATE INDEX IF NOT EXISTS idx_eval_runs_benchmark ON eval_runs(benchmark_name);
CREATE INDEX IF NOT EXISTS idx_eval_samples_eval_run_id ON eval_samples(eval_run_id);
CREATE INDEX IF NOT EXISTS idx_eval_samples_run_id ON eval_samples(run_id);

-- =============================================================================
-- Trace Events (granular timeline for multi-step agent flows)
-- =============================================================================

CREATE TABLE IF NOT EXISTS trace_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,               -- Atomic sequential ordering per run
    created_at TEXT NOT NULL,

    -- Event classification
    event_type TEXT NOT NULL,           -- llm_request | llm_response | reasoning | tool_call | tool_response | error | retry
    event_status TEXT NOT NULL,         -- pending | success | error | skipped
    actor TEXT NOT NULL,                -- model | system | tool:<name>

    -- Request/response tracking
    endpoint TEXT,                      -- /v1/responses | /v1/chat/completions
    attempt INTEGER DEFAULT 1,          -- Retry attempt number

    -- Content
    content_json TEXT NOT NULL,         -- Event payload (JSON)

    -- Relationships
    parent_event_id TEXT,               -- tool_response -> tool_call linking
    step_number INTEGER,                -- Agent step (1, 2, 3...)

    -- Telemetry
    duration_ms INTEGER,
    token_count INTEGER,
    error_message TEXT,

    -- Constraints
    UNIQUE(run_id, seq),                -- Strict ordering guarantee
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(parent_event_id) REFERENCES trace_events(id) ON DELETE CASCADE
);

-- Trace event indexes
CREATE INDEX IF NOT EXISTS idx_trace_events_run_seq ON trace_events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_trace_events_type ON trace_events(event_type);
CREATE INDEX IF NOT EXISTS idx_trace_events_step ON trace_events(run_id, step_number);
CREATE INDEX IF NOT EXISTS idx_trace_events_parent ON trace_events(parent_event_id);

-- =============================================================================
-- Agent Tables (for web research agent with crash recovery)
-- =============================================================================

-- Agent steps (state machine steps)
CREATE TABLE IF NOT EXISTS agent_steps (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_number INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    state TEXT NOT NULL,              -- planning | tool_calling | synthesizing | complete | error
    thinking_text TEXT,
    decision TEXT,                    -- call_tool | synthesize | error
    error_message TEXT,
    UNIQUE(run_id, step_number),
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

-- Agent tool calls (NO result_raw - prevents WAL bloat)
CREATE TABLE IF NOT EXISTS agent_tool_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments TEXT NOT NULL,          -- JSON
    status TEXT NOT NULL,             -- pending | running | success | error | timeout | interrupted
    started_at TEXT,
    completed_at TEXT,
    duration_ms INTEGER,
    idempotency_key TEXT NOT NULL,    -- For retry detection
    execution_attempt INTEGER DEFAULT 1,
    result_summary TEXT,              -- 1-line only, no blobs
    error_message TEXT,
    -- Observability: approval audit trail
    approval_decision TEXT,           -- approved | denied | auto | timeout
    approval_policy TEXT,             -- strict | relaxed | yolo
    approval_decided_at TEXT,         -- ISO timestamp
    -- Observability: full tool result for write tools
    result_detail TEXT,               -- Full result (up to 10k chars) for write/edit/bash tools
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(step_id) REFERENCES agent_steps(id) ON DELETE CASCADE
);

-- Agent citations (evidence for answers)
CREATE TABLE IF NOT EXISTS agent_citations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT,
    snippet TEXT NOT NULL,
    used_in_answer BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
);

-- Agent indexes
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_steps_state ON agent_steps(state);

-- =============================================================================
-- Browser Terminal Sessions
-- =============================================================================

CREATE TABLE IF NOT EXISTS terminal_sessions (
    session_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE,
    workspace_path TEXT,
    shell TEXT NOT NULL,
    status TEXT NOT NULL,              -- running | closed | stale
    cols INTEGER NOT NULL,
    rows INTEGER NOT NULL,
    session_owner TEXT,                -- demo session_id when applicable
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_activity_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_terminal_sessions_conversation_id
    ON terminal_sessions(conversation_id);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_run ON agent_tool_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_step ON agent_tool_calls(step_id);
CREATE INDEX IF NOT EXISTS idx_agent_tool_calls_status ON agent_tool_calls(status);
CREATE INDEX IF NOT EXISTS idx_agent_citations_run ON agent_citations(run_id);

-- =============================================================================
-- Observability Tables
-- =============================================================================

-- Persisted SSE events (survives in-memory cleanup)
CREATE TABLE IF NOT EXISTS run_events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_data TEXT NOT NULL,          -- JSON
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_events_run_seq ON run_events(run_id, seq);

-- File change tracking per run
CREATE TABLE IF NOT EXISTS run_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,       -- file_write | file_edit | command_run
    file_path TEXT,
    action TEXT NOT NULL,              -- write_file | edit_file | bash_tool
    detail TEXT,                       -- Result summary or command output
    tool_call_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(tool_call_id) REFERENCES agent_tool_calls(id) ON DELETE CASCADE
);

-- Global app settings
CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Persistent coding-session state for cross-turn coding continuity
CREATE TABLE IF NOT EXISTS coding_sessions (
    conversation_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    last_run_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY(last_run_id) REFERENCES runs(run_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS coding_session_entries (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    step_number INTEGER,
    entry_type TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    token_estimate INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    compacted_at TEXT,
    rewound_at TEXT,
    rewind_group_id TEXT,
    UNIQUE(conversation_id, seq),
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS conversation_rewind_checkpoints (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    run_id TEXT NOT NULL UNIQUE,
    user_message TEXT NOT NULL,
    entry_seq_before INTEGER NOT NULL,
    state_before_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_run ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_coding_sessions_updated_at ON coding_sessions(updated_at);
CREATE INDEX IF NOT EXISTS idx_coding_session_entries_conversation_seq
    ON coding_session_entries(conversation_id, seq);
CREATE INDEX IF NOT EXISTS idx_coding_session_entries_compacted
    ON coding_session_entries(conversation_id, compacted_at, seq);
CREATE INDEX IF NOT EXISTS idx_conversation_rewind_checkpoints_conversation_created
    ON conversation_rewind_checkpoints(conversation_id, created_at);
