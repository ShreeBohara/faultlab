"""The pack registry: reviewed packs by id, loaded on demand. Request data never chooses code."""

from __future__ import annotations

from importlib import import_module

from faultlab.packs.base import PackError, TaskPack

# pack id -> (module, attribute). Adding a pack means adding a line here and passing the conformance tests.
PACKS: dict[str, tuple[str, str]] = {
    "orders.upgrade_then_confirm/v1": ("faultlab.packs.orders.pack", "PACK"),
}


def pack_ids() -> list[str]:
    return list(PACKS)


def load_pack(pack_id: str) -> TaskPack:
    if pack_id not in PACKS:
        raise PackError(f"Unknown pack {pack_id!r}; known: {', '.join(PACKS)}")
    module_name, attribute = PACKS[pack_id]
    pack = getattr(import_module(module_name), attribute)
    if not isinstance(pack, TaskPack) or pack.pack_id != pack_id:
        raise PackError(f"Registry entry {pack_id!r} does not resolve to a pack with that id")
    return pack


def load_packs() -> list[TaskPack]:
    return [load_pack(pack_id) for pack_id in PACKS]


__all__ = ["PACKS", "load_pack", "load_packs", "pack_ids"]
