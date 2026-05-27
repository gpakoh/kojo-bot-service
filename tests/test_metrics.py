from tg_bot.infrastructure.metrics import (
    REGISTRY,
    kojo_orders_total,
)


def test_metrics_increment() -> None:
    before = kojo_orders_total.labels(status="Принят", tenant_id="default")._value.get()
    kojo_orders_total.labels(status="Принят", tenant_id="default").inc()
    after = kojo_orders_total.labels(status="Принят", tenant_id="default")._value.get()
    assert after == before + 1


def test_registry_not_empty() -> None:
    names = [m.name for m in REGISTRY.collect()]
    assert "kojo_orders" in names
    assert "kojo_llm_latency_seconds" in names
