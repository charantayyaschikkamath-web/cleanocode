"""Deterministic what-if calculation module (Account 7)."""

from .engine import calculate_comparison
from .models import WhatIfCompareRequest, WhatIfResponse

__all__ = ["calculate_comparison", "WhatIfCompareRequest", "WhatIfResponse"]
