"""Synthetic telco data generators, executed in dependency order."""
from . import (
    geography,
    catalog,
    customers,
    subscriptions,
    billing,
    usage,
    service,
    engagement,
    ml,
)

# Order matters: later generators depend on frames produced by earlier ones.
PIPELINE = [
    ("geography", geography),
    ("catalog", catalog),
    ("customers", customers),
    ("subscriptions", subscriptions),
    ("billing", billing),
    ("usage", usage),
    ("service", service),
    ("engagement", engagement),
    ("ml", ml),
]

__all__ = ["PIPELINE"]
