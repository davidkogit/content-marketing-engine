"""
LLM module — provider abstraction, factory, encrypted configuration service,
RAG context collection, prompt building, orchestrator, and post-processor.

Exports:
    LLMProvider / LLMResponse — base classes for provider implementations
    OpenAIProvider / AnthropicProvider — concrete async providers
    LLMProviderError / LLMAuthError / LLMRateLimitError / LLMServerError — errors
    get_provider / list_providers / is_valid_provider — factory functions
    LLMConfigService — CRUD for persisted LLM config with API key encryption
    encrypt_api_key / decrypt_api_key — encryption helpers
    ContextCollector / GenerationContext — RAG context assembly
    BrandRulesLoader / BrandRules — brand-governance rule file loader
    PromptBuilder — system and user prompt construction
    GenerationOrchestrator — full pipeline orchestrator
    PostProcessor — LLM response parser and claim extractor
    GeneratedResponse / GenerationType — output schemas
"""

from app.llm.provider_base import (
    LLMAuthError,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMResponse,
    LLMServerError,
)
from app.llm.openai_provider import OpenAIProvider
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.provider_factory import get_provider, is_valid_provider, list_providers
from app.llm.config_service import (
    LLMConfigService,
    decrypt_api_key,
    encrypt_api_key,
)
from app.llm.brand_rules import BrandRules, BrandRulesLoader
from app.llm.context_collector import ContextCollector, GenerationContext
from app.llm.prompt_builder import PromptBuilder
from app.llm.post_processor import PostProcessor
from app.llm.orchestrator import GenerationOrchestrator
from app.llm.generation_schemas import (
    GeneratedResponse,
    GenerationType,
    GenerationMetadata,
    ExtractedClaim,
    SourceRef,
    RuleViolation,
    TaskStatus,
    TaskStatusResponse,
)

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMProviderError",
    "LLMAuthError",
    "LLMRateLimitError",
    "LLMServerError",
    "OpenAIProvider",
    "AnthropicProvider",
    "get_provider",
    "is_valid_provider",
    "list_providers",
    "LLMConfigService",
    "encrypt_api_key",
    "decrypt_api_key",
    "BrandRules",
    "BrandRulesLoader",
    "ContextCollector",
    "GenerationContext",
    "PromptBuilder",
    "PostProcessor",
    "GenerationOrchestrator",
    "GeneratedResponse",
    "GenerationType",
    "GenerationMetadata",
    "ExtractedClaim",
    "SourceRef",
    "RuleViolation",
    "TaskStatus",
    "TaskStatusResponse",
]
