"""Configuration for the chat orchestrator.

This module is the single source of truth for all chat settings.
Configuration is loaded from chat_config.yaml.
"""

from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel


# =============================================================================
# Base Paths
# =============================================================================

BASE_DIR = Path(__file__).parent.parent
VAR_DIR = BASE_DIR / "var"
DB_PATH = VAR_DIR / "traces.sqlite"
PROMPTS_DIR = Path(__file__).parent / "prompts"
CHAT_CONFIG_PATH = Path(__file__).parent / "chat_config.yaml"

# Ensure directories exist
VAR_DIR.mkdir(exist_ok=True)


# =============================================================================
# Chat Configuration Classes
# =============================================================================

class ChatModelConfig(BaseModel):
    """Model generation parameters."""
    name: str = "ministral-14b-reasoning"  # Model name for Ollama
    temperature: float = 0.7
    max_tokens: int = 4096
    seed: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None


class ChatContextConfig(BaseModel):
    """Context window management settings."""
    max_messages: int = 50
    max_tokens: int = 6000
    reserve_for_response: int = 2048
    truncation_strategy: Literal["sliding_window", "oldest_first"] = "sliding_window"


class ChatTracingConfig(BaseModel):
    """Tracing settings."""
    enabled: bool = True
    log_level: Literal["debug", "info", "warn"] = "info"
    log_model_calls: bool = True


class SystemPromptConfig(BaseModel):
    """System prompt configuration with file path and inline fallback."""

    reasoning_prompt: str = "You are a helpful AI assistant. Think step by step."
    reasoning_prompt_path: Optional[Path] = None
    chat_prompt: str = "You are a helpful AI assistant. Answer directly and clearly."
    chat_prompt_path: Optional[Path] = None


# =============================================================================
# Thinking Configuration Classes
# =============================================================================

class AutoDetectionConfig(BaseModel):
    """Complexity auto-detection settings."""
    enabled: bool = True
    simple_threshold: float = 0.3
    complex_threshold: float = 0.7


class CoTConfig(BaseModel):
    """Chain-of-Thought strategy settings."""
    enabled: bool = True
    trigger_phrase: str = "Let's think step by step."
    thinking_budget: int = 512  # Max tokens for thinking phase
    answer_budget: int = 256  # Max tokens for answer phase


class SelfConsistencyConfig(BaseModel):
    """Self-Consistency strategy settings."""
    enabled: bool = True
    n_samples: int = 3
    temperature: float = 0.7
    voting_method: Literal["majority", "weighted"] = "majority"


class SelfReflectionConfig(BaseModel):
    """Self-Reflection strategy settings."""
    enabled: bool = True
    max_iterations: int = 2


class ChainOfDraftConfig(BaseModel):
    """Chain-of-Draft strategy settings."""
    enabled: bool = True
    max_words_per_step: int = 5


class CARConfig(BaseModel):
    """CAR (Certainty-based Adaptive Routing) strategy settings."""
    ppl_threshold: float = 5.0  # Below = direct answer, above = CoT
    max_short_tokens: int = 100  # Max tokens for short answer probe
    thinking_budget: int = 512  # Max tokens for thinking phase (when escalating)
    answer_budget: int = 256  # Max tokens for answer phase (when escalating)


class ThinkingTracingConfig(BaseModel):
    """Thinking tracing settings."""
    save_internal: bool = True
    save_user_summary: bool = True


class ThinkingUIConfig(BaseModel):
    """Thinking UI display settings."""
    show_thinking: bool = False
    collapsible: bool = True


class ThinkingConfig(BaseModel):
    """Complete thinking/reasoning configuration."""
    default_strategy: str = "car"
    car: CARConfig = CARConfig()
    auto_detection: AutoDetectionConfig = AutoDetectionConfig()
    cot: CoTConfig = CoTConfig()
    self_consistency: SelfConsistencyConfig = SelfConsistencyConfig()
    self_reflection: SelfReflectionConfig = SelfReflectionConfig()
    chain_of_draft: ChainOfDraftConfig = ChainOfDraftConfig()
    tracing: ThinkingTracingConfig = ThinkingTracingConfig()
    ui: ThinkingUIConfig = ThinkingUIConfig()


class ChatConfig(BaseModel):
    """Complete chat configuration loaded from chat_config.yaml.

    This is the single source of truth for all chat runtime settings.
    """
    model: ChatModelConfig = ChatModelConfig()
    context: ChatContextConfig = ChatContextConfig()
    system_prompt: str = "You are a helpful AI assistant. Answer directly and clearly."
    endpoint: str = "http://127.0.0.1:1234"
    tracing: ChatTracingConfig = ChatTracingConfig()
    thinking: ThinkingConfig = ThinkingConfig()

    def get_snapshot(self) -> dict:
        """Get a snapshot of config for tracing/reproducibility."""
        import hashlib
        prompt_hash = hashlib.md5(self.system_prompt.encode()).hexdigest()[:8]
        return {
            "model": self.model.model_dump(),
            "context": self.context.model_dump(),
            "system_prompt_hash": prompt_hash,
            "endpoint": self.endpoint,
            "tracing": self.tracing.model_dump(),
            "thinking": self.thinking.model_dump(),
        }


# =============================================================================
# Config Loading
# =============================================================================

_chat_config: Optional[ChatConfig] = None


def get_chat_config(reload: bool = False) -> ChatConfig:
    """Load chat config from YAML file.
    
    Args:
        reload: If True, reload from file even if cached.
    
    Returns:
        ChatConfig instance.
    """
    global _chat_config
    
    if _chat_config is not None and not reload:
        return _chat_config
    
    if CHAT_CONFIG_PATH.exists():
        import yaml
        with open(CHAT_CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        _chat_config = ChatConfig(**data)
    else:
        # Use defaults if file doesn't exist
        _chat_config = ChatConfig()
    
    return _chat_config
