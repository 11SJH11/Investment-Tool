import pytest

from app.data.providers.registry import ProviderRegistry


def test_provider_registry_registers_and_returns_provider():
    registry = ProviderRegistry()
    provider = object()

    registry.register("market", provider)

    assert registry.get("market") is provider
    assert registry.configured() == ["market"]


def test_provider_registry_explains_missing_provider():
    registry = ProviderRegistry()

    with pytest.raises(RuntimeError, match="No provider configured"):
        registry.get("market")
