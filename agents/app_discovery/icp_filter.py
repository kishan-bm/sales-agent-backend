import os
from datetime import date, timedelta

STALE_DAYS = int(os.getenv("STALE_DAYS", "730"))

TARGET_CATEGORIES_PLAY = {
    "health and fitness", "lifestyle", "food and drink", "medical",
    "parenting", "education", "house and home", "health", "shopping",
    "beauty", "sports", "tools", "productivity", "entertainment",
}
TARGET_CATEGORIES_APPLE = {
    "health & fitness", "lifestyle", "food & drink", "medical",
    "parenting", "education", "shopping", "sports", "utilities",
    "entertainment", "productivity",
}

# Hard exclusions — we will never pitch to these
MARKETPLACE_KEYWORDS = [
    "amazon", "flipkart", "meesho", "myntra", "ajio",
    "snapdeal", "paytm mall", "tatacliq", "zepto", "blinkit",
    "swiggy instamart", "bigbasket", "dunzo", "nykaa fashion",
]

D2C_KEYWORDS = [
    "our brand", "our products", "own brand", "official store", "official app",
    "brand store", "shop our", "manufactured by", "made by us", "created by",
    "exclusive", "direct", "our range", "our collection", "our store",
    "founder", "homegrown", "made in india", "india brand", "indian brand",
    "buy our", "shop now", "order now", "buy direct",
]
POSITIVE_KEYWORDS = [
    "subscription", "membership", "loyalty", "reward", "points",
    "diet", "nutrition", "meal", "fitness", "workout", "yoga",
    "wellness", "skincare", "beauty", "organic", "ayurvedic",
    "baby", "kids", "family", "maternity", "parenting",
    "home decor", "furniture", "appliance",
    "learning", "course", "tutor", "education",
    "supplement", "vitamin", "protein", "herbal", "natural",
    "hair", "skin", "health", "care", "clean", "pure",
    "pharmacy", "medicine", "dental", "doctor", "clinic",
    "food", "snack", "drink", "grocery", "cook", "recipe",
]
INDIA_SIGNALS = ["india", "indian", "₹", "inr", "bharat", ".in"]


def _normalize(s: str) -> str:
    return s.lower().replace("&", "and").replace("/", " ").replace("-", " ")


def _contains_any(text: str, keywords: list[str]) -> int:
    t = text.lower()
    return sum(1 for kw in keywords if kw in t)


def apply_icp_filter(app: dict, store: str) -> bool:
    desc  = (app.get("description") or app.get("summary") or "").lower()
    name  = (app.get("title") or app.get("app_name") or "").lower()
    text  = desc + " " + name
    dev_url = (app.get("developerWebsite") or app.get("sellerUrl") or "").lower()

    # ── Hard gate 1: no major marketplace (non-negotiable) ─────────────────
    if _contains_any(text, MARKETPLACE_KEYWORDS) > 0:
        return False

    # ── Hard gate 2: India signal (we only pitch to Indian apps) ───────────
    has_india = (
        any(s in text for s in INDIA_SIGNALS)
        or app.get("country") == "in"
        or ".in" in dev_url
        or app.get("developerEmail", "").endswith(".in")
    )
    if not has_india:
        return False

    # ── Staleness check (optional — don't block if date unknown) ───────────
    updated = (app.get("updated") or app.get("currentVersionReleaseDate")
               or app.get("releaseDate"))
    if updated:
        try:
            if isinstance(updated, (int, float)):
                updated_date = date.fromtimestamp(updated)
            else:
                from dateutil import parser as dp
                updated_date = dp.parse(str(updated)).date()
            # Block if updated VERY recently (within 6 months) — clearly active
            if updated_date > date.today() - timedelta(days=180):
                return False
        except Exception:
            pass  # can't parse date → don't block

    # ── Soft signals: app passes if it matches ANY ONE of these ────────────
    raw_cat = _normalize(app.get("genre") or app.get("primaryGenreName") or "")

    category_match = (
        any(c in raw_cat for c in TARGET_CATEGORIES_PLAY) if store == "play"
        else any(c in raw_cat for c in TARGET_CATEGORIES_APPLE)
    )
    d2c_match      = _contains_any(text, D2C_KEYWORDS) >= 1
    keyword_match  = _contains_any(text, POSITIVE_KEYWORDS) >= 1

    # At least ONE soft signal must match
    return category_match or d2c_match or keyword_match


def extract_signals(app: dict) -> tuple[list[str], list[str]]:
    """Returns (d2c_signals_found, positive_keywords_found)."""
    text = (app.get("description") or "") + " " + (app.get("title") or "")
    d2c  = [kw for kw in D2C_KEYWORDS     if kw in text.lower()]
    pos  = [kw for kw in POSITIVE_KEYWORDS if kw in text.lower()]
    return d2c, pos
