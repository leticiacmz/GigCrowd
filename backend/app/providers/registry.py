from typing import Dict
from app.providers.base import BaseProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, name: str, provider: BaseProvider):
        self._providers[name] = provider

    def get_provider(self, name: str) -> BaseProvider:
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")

        return self._providers[name]


registry = ProviderRegistry()