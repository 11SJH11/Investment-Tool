"""Shared bounded author inputs; no runtime authority or provider configuration."""

ARCHIVED_SOURCE_BYTES = 128000
AUTHOR_EVIDENCE_BYTES = 200000
MODEL_REQUEST_BYTES = 240000
# Conservative one-token-per-byte reservation plus protocol overhead. No cache discount.
MODEL_INPUT_TOKEN_RESERVATION = 250000
