"""Audit test: every documented RLS bypass must have a visible warning."""
from pathlib import Path


def test_event_store_has_rls_bypass_warning():
    source = Path("tg_bot/infrastructure/event_store.py").read_text(encoding="utf-8")
    assert "WARNING: EventStore uses raw pool.acquire()" in source or \
           "system-level RLS bypass" in source
