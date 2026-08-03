from __future__ import annotations

import time

from .exceptions import CouponExhaustedError, CouponExpiredError, CouponInvalidError
from .models import Coupon, CouponType
from .repository import CouponRepository


class CouponManager:
    """Manages coupons: validation, redemption and discount computation."""

    def __init__(self, repository: CouponRepository | None = None) -> None:
        from .repository import InMemoryCouponRepository

        self._repository = repository or InMemoryCouponRepository()

    @property
    def repository(self) -> CouponRepository:
        return self._repository

    def create(
        self,
        code: str,
        coupon_type: str | CouponType = "percent",
        value: float = 0.0,
        max_redemptions: int = 0,
        expires_at: float = 0.0,
        applies_to: list[str] | None = None,
    ) -> Coupon:
        if isinstance(coupon_type, str):
            coupon_type = CouponType(coupon_type)
        coupon = Coupon(
            code=code.upper(),
            type=coupon_type,
            value=value,
            max_redemptions=max_redemptions,
            expires_at=expires_at,
            applies_to=applies_to or [],
        )
        return self._repository.create(coupon)

    def validate(self, code: str, plan_id: str = "", now: float | None = None) -> Coupon:
        coupon = self._repository.get(code)
        now = now or time.time()
        if coupon.expires_at and coupon.expires_at < now:
            raise CouponExpiredError(code)
        if coupon.max_redemptions and coupon.redemptions >= coupon.max_redemptions:
            raise CouponExhaustedError(code)
        if plan_id and coupon.applies_to and plan_id not in coupon.applies_to:
            raise CouponInvalidError(code, f"not applicable to plan {plan_id!r}")
        return coupon

    def redeem(self, code: str, plan_id: str = "", now: float | None = None) -> Coupon:
        coupon = self.validate(code, plan_id=plan_id, now=now)
        coupon.redemptions += 1
        return self._repository.update(coupon)

    def discount(self, code: str, subtotal: float, plan_id: str = "", now: float | None = None) -> tuple[float, str]:
        """Return ``(discount_amount, description)`` for a coupon applied to a subtotal."""
        coupon = self.validate(code, plan_id=plan_id, now=now)
        if coupon.type == CouponType.PERCENT:
            amount = round(subtotal * coupon.value / 100.0, 4)
            description = f"{coupon.value:.0f}% discount ({coupon.code})"
        elif coupon.type == CouponType.FIXED_AMOUNT:
            amount = min(subtotal, coupon.value)
            description = f"{coupon.value:.2f} {coupon.type.value} discount ({coupon.code})"
        else:
            amount = 0.0
            description = ""
        return amount, description

    def list(self) -> list[Coupon]:
        return self._repository.list()

    def get(self, code: str) -> Coupon:
        return self._repository.get(code)

    def delete(self, code: str) -> bool:
        return self._repository.delete(code)
