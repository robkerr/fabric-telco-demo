"""Product catalog: dim_product, dim_plan, dim_device, dim_promotion."""
from __future__ import annotations

import pandas as pd

from .common import GenContext

# Fixed, curated catalog so demo journeys reference stable products.
_PRODUCTS = [
    # product_id, name, category, monthly_price
    ("PROD_INT", "Home Internet", "internet", 0.0),      # priced via plan
    ("PROD_MOB", "Mobile", "mobile", 0.0),               # priced via plan
    ("PROD_VOICE", "Home Phone", "voice", 25.00),
    ("PROD_TV", "Streaming TV", "tv", 45.00),
]

_PLANS = [
    # plan_id, product_id, name, speed_mbps, data_gb, price
    ("PLAN_INT_100", "PROD_INT", "Internet 100", 100, None, 45.00),
    ("PLAN_INT_500", "PROD_INT", "Internet 500", 500, None, 65.00),
    ("PLAN_INT_1G", "PROD_INT", "Internet Gig", 1000, None, 85.00),
    ("PLAN_INT_2G", "PROD_INT", "Internet 2 Gig", 2000, None, 110.00),
    ("PLAN_MOB_UNL", "PROD_MOB", "Mobile Unlimited", None, None, 55.00),
    ("PLAN_MOB_40", "PROD_MOB", "Mobile 40GB", None, 40, 40.00),
    ("PLAN_MOB_10", "PROD_MOB", "Mobile 10GB", None, 10, 25.00),
    ("PLAN_VOICE_STD", "PROD_VOICE", "Home Phone Unlimited", None, None, 25.00),
    ("PLAN_TV_STD", "PROD_TV", "Streaming TV", None, None, 45.00),
]

_DEVICES = [
    # device_id, model, type, monthly_price
    ("DEV_MODEM_STD", "TelcoConnect Modem", "modem", 5.00),
    ("DEV_ROUTER_MESH", "TelcoConnect Mesh Router", "router", 10.00),
    ("DEV_PHONE_A", "Aurora 5G Phone", "phone", 22.00),
    ("DEV_PHONE_B", "Aurora Lite Phone", "phone", 12.00),
    ("DEV_NONE", "Bring Your Own Device", "byod", 0.00),
]

_PROMOTIONS = [
    # promotion_id, name, type, discount_pct, discount_amount, terms
    ("PROMO_ACQ_1", "New Customer $200 Credit", "acquisition", None, 200.00,
     "One-time bill credit for new residential accounts."),
    ("PROMO_ACQ_2", "First 3 Months Half Off Internet", "acquisition", 50.0, None,
     "50% off internet MRC for first 3 months."),
    ("PROMO_XSELL_1", "Add Mobile, Save $10/mo", "crosssell", None, 10.00,
     "$10/mo discount when mobile is added to an internet account."),
    ("PROMO_XSELL_2", "Bundle TV + Internet Save 15%", "crosssell", 15.0, None,
     "15% off when TV is bundled with internet."),
    ("PROMO_RET_1", "Loyalty $30 Credit", "retention", None, 30.00,
     "One-time loyalty credit to retain at-risk customers."),
    ("PROMO_RET_2", "Retention 20% Off 6 Months", "retention", 20.0, None,
     "20% off MRC for 6 months for save/retention offers."),
    ("PROMO_SVC_1", "Service Outage Credit", "service", None, 15.00,
     "Goodwill credit following a qualifying outage."),
]


def generate(ctx: GenContext) -> None:
    ctx.add("dim_product", pd.DataFrame(
        _PRODUCTS, columns=["product_id", "name", "category", "monthly_price"]))
    ctx.add("dim_plan", pd.DataFrame(
        _PLANS, columns=["plan_id", "product_id", "name", "speed_mbps", "data_gb", "price"]))
    ctx.add("dim_device", pd.DataFrame(
        _DEVICES, columns=["device_id", "model", "type", "monthly_price"]))
    ctx.add("dim_promotion", pd.DataFrame(
        _PROMOTIONS,
        columns=["promotion_id", "name", "type", "discount_pct", "discount_amount", "terms"]))
