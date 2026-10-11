"""The adapter registry: reviewed adapters by id. Request data never chooses code."""

from __future__ import annotations

from importlib import import_module

from faultlab.adapters.base import BaseAdapter
from faultlab.core.errors import FaultLabError

ADAPTERS: dict[str, tuple[str, str]] = {
    "reference-orders": ("faultlab.adapters.reference", "ReferenceOrdersAdapter"),
}


class AdapterError(FaultLabError, ValueError):
    """An adapter id the registry does not know, or an entry that does not resolve to an adapter."""


def adapter_ids() -> list[str]:
    return list(ADAPTERS)


def load_adapter(adapter_id: str, **settings) -> BaseAdapter:
    if adapter_id not in ADAPTERS:
        raise AdapterError(f"Unknown adapter {adapter_id!r}; known: {', '.join(ADAPTERS)}")
    module_name, attribute = ADAPTERS[adapter_id]
    factory = getattr(import_module(module_name), attribute)
    adapter = factory(**settings)
    if not isinstance(adapter, BaseAdapter) or adapter.adapter_id != adapter_id:
        raise AdapterError(f"Registry entry {adapter_id!r} does not resolve to an adapter with that id")
    return adapter


def load_adapters() -> list[BaseAdapter]:
    return [load_adapter(adapter_id) for adapter_id in ADAPTERS]


__all__ = ["ADAPTERS", "AdapterError", "adapter_ids", "load_adapter", "load_adapters"]
