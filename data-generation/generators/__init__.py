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
    devices,
)

# Order matters: later generators depend on frames produced by earlier ones.
# `devices` runs LAST (it only reads subscriptions/accounts/device-catalog) so adding it
# doesn't shift the RNG stream of the other generators — keeping their output stable.
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
    ("devices", devices),
]

__all__ = ["PIPELINE"]
