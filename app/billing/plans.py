from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .exceptions import PlanNotFoundError
from .models import Plan, PlanTier, UsageCategory


class PricingStrategy(ABC):
    """Strategy: computes the monthly price of a plan for a given usage profile."""

    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def compute(self, plan: Plan, usage: dict[str, int] | None = None, seats: int = 1, interval: str = "monthly") -> float:
        raise NotImplementedError


class FlatPricingStrategy(PricingStrategy):
    def name(self) -> str:
        return "flat"

    def compute(self, plan: Plan, usage: dict[str, int] | None = None, seats: int = 1, interval: str = "monthly") -> float:
        base = plan.price_for(interval)
        return base * max(1, seats)


class PerSeatPricingStrategy(PricingStrategy):
    def name(self) -> str:
        return "per_seat"

    def compute(self, plan: Plan, usage: dict[str, int] | None = None, seats: int = 1, interval: str = "monthly") -> float:
        return plan.price_for(interval) * max(1, seats)


class TieredPricingStrategy(PricingStrategy):
    """Usage tiers defined on the plan limits under ``tiers`` metadata."""

    def name(self) -> str:
        return "tiered"

    def compute(self, plan: Plan, usage: dict[str, int] | None = None, seats: int = 1, interval: str = "monthly") -> float:
        usage = usage or {}
        total = plan.price_for(interval) * max(1, seats)
        tiers = plan.limits.get("tiers", []) if isinstance(plan.limits.get("tiers"), list) else []
        for tier in tiers:
            threshold = int(tier.get("threshold", 0))
            price = float(tier.get("price", 0.0))
            dimension = str(tier.get("dimension", "api_requests"))
            if usage.get(dimension, 0) > threshold:
                total += price
        return round(total, 4)


class UsageBasedPricingStrategy(PricingStrategy):
    """Per-unit overage pricing: plan price plus unit rate over included units."""

    def name(self) -> str:
        return "usage"

    def compute(self, plan: Plan, usage: dict[str, int] | None = None, seats: int = 1, interval: str = "monthly") -> float:
        usage = usage or {}
        total = plan.price_for(interval) * max(1, seats)
        overage = plan.limits
        for dimension, included in overage.items():
            if dimension.startswith("_") or dimension == "tiers":
                continue
            used = int(usage.get(dimension, 0))
            rate = float(plan.metadata.get(f"{dimension}_rate", 0.0))
            if rate and used > int(included):
                total += (used - int(included)) * rate
        return round(total, 4)


class PricingStrategyFactory:
    """Factory: builds pricing strategies by name."""

    _registry: dict[str, type[PricingStrategy]] = {
        FlatPricingStrategy.name: FlatPricingStrategy,
        "flat": FlatPricingStrategy,
        PerSeatPricingStrategy.name: PerSeatPricingStrategy,
        "per_seat": PerSeatPricingStrategy,
        TieredPricingStrategy.name: TieredPricingStrategy,
        "tiered": TieredPricingStrategy,
        UsageBasedPricingStrategy.name: UsageBasedPricingStrategy,
        "usage": UsageBasedPricingStrategy,
    }

    @classmethod
    def create(cls, name: str) -> PricingStrategy:
        strategy_cls = cls._registry.get(name)
        if strategy_cls is None:
            return FlatPricingStrategy()
        return strategy_cls()


def _limits(
    tokens: int,
    requests: int,
    storage: int,
    embeddings: int,
    mcp: int,
    plugins: int,
    uploads: int,
    users: int,
) -> dict[str, int]:
    return {
        UsageCategory.TOKENS.value: tokens,
        UsageCategory.API_REQUESTS.value: requests,
        UsageCategory.VECTOR_STORAGE.value: storage,
        UsageCategory.EMBEDDINGS.value: embeddings,
        UsageCategory.MCP_CALLS.value: mcp,
        UsageCategory.PLUGINS.value: plugins,
        UsageCategory.UPLOADS.value: uploads,
        UsageCategory.ACTIVE_USERS.value: users,
    }


class PlanCatalog:
    """Registry of plans offered by the platform."""

    FREE_PLAN_ID = "free"
    CUSTOM_PLAN_ID = "custom"

    def __init__(self) -> None:
        self._plans: dict[str, Plan] = {
            self.FREE_PLAN_ID: Plan(
                id=self.FREE_PLAN_ID,
                name="Free",
                tier=PlanTier.FREE,
                price_monthly=0.0,
                price_annual=0.0,
                supports_trial=False,
                limits=_limits(
                    tokens=100_000,
                    requests=1_000,
                    storage=100,
                    embeddings=5_000,
                    mcp=50,
                    plugins=1,
                    uploads=20,
                    users=1,
                ),
                features=["1 active user", "1 plugin", "Community support"],
            ),
            "starter": Plan(
                id="starter",
                name="Starter",
                tier=PlanTier.STARTER,
                price_monthly=29.0,
                price_annual=290.0,
                limits=_limits(
                    tokens=2_000_000,
                    requests=50_000,
                    storage=2_000,
                    embeddings=100_000,
                    mcp=500,
                    plugins=3,
                    uploads=200,
                    users=5,
                ),
                features=["5 users", "3 plugins", "MCP access"],
            ),
            "professional": Plan(
                id="professional",
                name="Professional",
                tier=PlanTier.PROFESSIONAL,
                price_monthly=99.0,
                price_annual=990.0,
                limits=_limits(
                    tokens=10_000_000,
                    requests=250_000,
                    storage=20_000,
                    embeddings=500_000,
                    mcp=2_000,
                    plugins=10,
                    uploads=1_000,
                    users=20,
                ),
                features=["20 users", "10 plugins", "Webhooks"],
            ),
            "team": Plan(
                id="team",
                name="Team",
                tier=PlanTier.TEAM,
                price_monthly=299.0,
                price_annual=2_990.0,
                limits=_limits(
                    tokens=50_000_000,
                    requests=1_000_000,
                    storage=100_000,
                    embeddings=2_000_000,
                    mcp=10_000,
                    plugins=25,
                    uploads=5_000,
                    users=100,
                ),
                features=["100 users", "25 plugins", "SSO", "Audit logs"],
            ),
            "enterprise": Plan(
                id="enterprise",
                name="Enterprise",
                tier=PlanTier.ENTERPRISE,
                price_monthly=999.0,
                price_annual=9_990.0,
                limits=_limits(
                    tokens=200_000_000,
                    requests=5_000_000,
                    storage=500_000,
                    embeddings=10_000_000,
                    mcp=50_000,
                    plugins=100,
                    uploads=25_000,
                    users=500,
                ),
                features=["500 users", "100 plugins", "Dedicated support", "SLA"],
            ),
            self.CUSTOM_PLAN_ID: Plan(
                id=self.CUSTOM_PLAN_ID,
                name="Custom",
                tier=PlanTier.CUSTOM,
                price_monthly=0.0,
                price_annual=0.0,
                is_custom=True,
                supports_trial=False,
                pricing_strategy="flat",
                limits=_limits(0, 0, 0, 0, 0, 0, 0, 0),
                features=["Tailored limits", "Custom contract"],
            ),
        }

    def get(self, plan_id: str) -> Plan:
        plan = self._plans.get(plan_id)
        if plan is None:
            raise PlanNotFoundError(plan_id)
        return plan

    def all(self) -> list[Plan]:
        return list(self._plans.values())

    def ids(self) -> list[str]:
        return list(self._plans.keys())

    def register(self, plan: Plan) -> Plan:
        self._plans[plan.id] = plan
        return plan

    def remove(self, plan_id: str) -> bool:
        if plan_id not in self._plans:
            return False
        del self._plans[plan_id]
        return True

    def limits_for(self, plan_id: str) -> dict[str, int]:
        return dict(self.get(plan_id).limits)


class PricingEngine:
    """Combines catalog and pricing strategies to price plans."""

    def __init__(self, catalog: PlanCatalog | None = None, factory: type[PricingStrategyFactory] = PricingStrategyFactory) -> None:
        self._catalog = catalog or PlanCatalog()
        self._factory = factory

    @property
    def catalog(self) -> PlanCatalog:
        return self._catalog

    def price(
        self,
        plan_id: str,
        usage: dict[str, int] | None = None,
        seats: int = 1,
        interval: str = "monthly",
        strategy: str | None = None,
    ) -> dict[str, Any]:
        plan = self._catalog.get(plan_id)
        strategy_name = strategy or plan.pricing_strategy
        engine = self._factory.create(strategy_name)
        amount = engine.compute(plan, usage=usage, seats=seats, interval=interval)
        return {
            "plan_id": plan_id,
            "strategy": engine.name(),
            "amount": round(amount, 4),
            "currency": "USD",
            "interval": interval,
            "seats": seats,
        }

    def create_custom_plan(
        self,
        plan_id: str,
        name: str,
        price: float,
        limits: dict[str, int] | None = None,
        features: list[str] | None = None,
        strategy: str = "flat",
    ) -> Plan:
        plan = Plan(
            id=plan_id,
            name=name,
            tier=PlanTier.CUSTOM,
            price_monthly=price,
            price_annual=price * 10,
            limits=limits or _limits(0, 0, 0, 0, 0, 0, 0, 0),
            features=features or [],
            supports_trial=False,
            is_custom=True,
            pricing_strategy=strategy,
        )
        return self._catalog.register(plan)
