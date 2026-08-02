from __future__ import annotations

from .config import BillingConfig

DEFAULT_JURISDICTIONS: dict[str, float] = {
    "US": 0.0,
    "GB": 0.2,
    "DE": 0.19,
    "SG": 0.09,
    "ID": 0.11,
}


class TaxCalculator:
    """Strategy: computes tax for a subtotal under a jurisdiction or fixed rate."""

    def __init__(self, config: BillingConfig | None = None, jurisdictions: dict[str, float] | None = None) -> None:
        self._config = config or BillingConfig()
        self._jurisdictions = dict(jurisdictions) if jurisdictions is not None else dict(DEFAULT_JURISDICTIONS)

    @property
    def jurisdictions(self) -> dict[str, float]:
        return dict(self._jurisdictions)

    def register_jurisdiction(self, code: str, rate: float) -> None:
        self._jurisdictions[code.upper()] = rate

    def rate_for(self, country_code: str = "") -> float:
        if country_code:
            return self._jurisdictions.get(country_code.upper(), self._config.tax_rate)
        return self._config.tax_rate

    def tax(self, subtotal: float, country_code: str = "") -> float:
        return round(subtotal * self.rate_for(country_code), 4)

    def tax_details(self, subtotal: float, country_code: str = "") -> dict[str, float]:
        rate = self.rate_for(country_code)
        return {
            "rate": rate,
            "amount": round(subtotal * rate, 4),
        }
