"""Payment gateway configuration and exchange rate matrix."""
from __future__ import annotations

import os
from pydantic import BaseModel, Field
from .models import Currency


class GatewayConfig(BaseModel):
    environment: str = "sandbox"
    base_url: str = "https://api.gateway.internal/v1"
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 10.0
    max_retries: int = 3
    backoff_factor: float = 1.5
    hmac_secret: str = "sec_test_live_key_982734190"
    circuit_breaker_threshold: int = 5
    # Cross-border processing fee in integer basis points (1 bps = 0.01% = 0.0001)
    # Default 250 bps = 2.50%
    cross_border_fee_bps: int = 250
    # Fixed transaction fee in minor units (30 cents)
    fixed_fee_cents: int = 30

    # Currency exchange rates relative to USD (base: 1.0 USD)
    exchange_rates: dict[Currency, float] = Field(default_factory=lambda: {
        Currency.USD: 1.0,
        Currency.EUR: 0.92,
        Currency.GBP: 0.78,
        Currency.JPY: 154.5,
        Currency.CAD: 1.38,
    })

    @classmethod
    def load_from_env(cls) -> GatewayConfig:
        return cls(
            environment=os.environ.get("GATEWAY_ENV", "sandbox"),
            connect_timeout_seconds=float(os.environ.get("GATEWAY_CONNECT_TIMEOUT", "5.0")),
            read_timeout_seconds=float(os.environ.get("GATEWAY_READ_TIMEOUT", "10.0")),
            max_retries=int(os.environ.get("GATEWAY_MAX_RETRIES", "3")),
        )
