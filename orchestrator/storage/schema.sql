-- Core Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
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

    -- Telemetry
    usage_stats TEXT, -- JSON: {"input_tokens": 100, "output_tokens": 50, "latency_ms": 1200}

    FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
);

-- Model Calls (detailed log of each LLM call)
CREATE TABLE IF NOT EXISTS model_calls (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    seq INT NOT NULL,
    created_at TEXT NOT NULL,
    
    -- Content
    step_type TEXT NOT NULL, -- model_call
    content TEXT,
    metadata_json TEXT, -- JSON: messages, response, tokens, timing, config
    
    FOREIGN KEY(run_id) REFERENCES runs(run_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_conversation_id ON runs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_model_calls_run_id ON model_calls(run_id);

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

    -- Link to full trace (runs + model_calls)
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
