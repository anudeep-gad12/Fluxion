-- Core Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT,
    summary TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL, -- active, archived, closed
    metadata_json TEXT
);

-- Runs (one row per chat turn/message exchange)
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    
    -- Inputs
    user_message TEXT,
    system_prompt_snapshot TEXT, -- Full exact system prompt used
    
    -- Config
    profile_name TEXT NOT NULL,
    mode TEXT NOT NULL, -- chat
    model_config_snapshot TEXT NOT NULL, -- JSON: temp, max_tokens, etc.
    
    -- Outputs
    final_answer TEXT,
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
