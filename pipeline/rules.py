"""Classified values for the build.

This is the machine-readable form of the decisions in data/quality/issues/.
A token that is not listed here fails `python pipeline/build.py` until it is
added here and recorded in the matching issue file.
"""

ISSUE_DUPLICATES = "data/quality/issues/01-duplicate-users.md"
ISSUE_SENTINELS = "data/quality/issues/02-test-and-sentinel-values.md"
ISSUE_FOREIGN_KEYS = "data/quality/issues/03-missing-foreign-keys.md"
ISSUE_MEASURES = "data/quality/issues/04-invalid-measures.md"
ISSUE_SUBSCRIPTIONS = "data/quality/issues/05-blank-subscription-fields.md"

# BIZ_3 is MakerHarbor, the only business whose content has creators.
MAKERHARBOR_BUSINESS_ID = "BIZ_3"

BUSINESS_IDS = {"BIZ_1", "BIZ_2", "BIZ_3"}
BUSINESS_NAMES = {
    "PageGarden Premium (SYNTHETIC)",
    "GatherSquare Community (SYNTHETIC)",
    "MakerHarbor (SYNTHETIC)",
}
BUSINESS_LINES = {
    "premium_published_content",
    "consumer_community",
    "creator_content",
}
HQ_PLANETS = {"Terra Prime", "Nearia", "Wavanda"}

COUNTRIES = {
    "Altara",
    "Australia",
    "Brazil",
    "Canada",
    "Eloria",
    "Freelandia",
    "Genora",
    "Germany",
    "Gondale",
    "Hogglewick",
    "Japan",
    "Latoria",
    "Nearia",
    "United Kingdom",
    "United States",
    "Wavanda",
    "Wondervale",
    "Zubria",
}

TEST_FLAGS = {"True", "False"}

AGE_TO_UNKNOWN = {"", "N/A", "999"}
AGE_BANDS = {"13-17", "18-24", "25-34", "35-44", "45-54", "55-64", "65+", "unknown"}

CHANNEL_TO_UNKNOWN = {"", "carrier_pigeon", "influencer_TEST_CAMPAIGN"}
CHANNELS = {"organic_search", "referral", "paid_social", "email_campaign", "unknown"}

DEVICE_TO_UNKNOWN = {"smart_toaster", "unknown_device"}
DEVICES = {"iOS_app", "Android_app", "web_mobile", "web_desktop", "unknown"}

CONTENT_TYPE_TO_UNKNOWN = {"TEST_TYPE"}
CONTENT_TYPES = {
    "ebook",
    "audiobook",
    "poll",
    "forum_post",
    "video",
    "serialized_chapter",
    "unknown",
}
CATEGORIES = {
    "Sci-Fi",
    "Book Club Chatter",
    "Cooking",
    "Poetry (Bad)",
    "Mystery",
    "Indie Fiction",
    "Ask the Community",
    "Romance",
    "Serialized Drama",
    "Definitely Not Fan Fiction",
    "Self-Help",
    "Fake History of Imaginary Countries",
    "Fantasy",
    "Memes About Reading",
    "How-To Guides",
    "General Nonsense",
    "Fan Theories",
}

PAYOUT_TIERS = {"Tier_0_Starter", "Tier_1_Standard", "Tier_2_Growth", "Tier_3_Partner"}

PLAN_TIERS = {"Free", "Basic", "Premium", "Premium_Plus_Deluxe_XL"}
BILLING_CYCLES = {"monthly", "annual", "lifetime_deal_fake", "not_applicable"}

STATUS_TO_UNKNOWN = {"TEST_STATUS_DO_NOT_USE"}
STATUSES = {"active", "canceled", "paused", "trialing", "unknown"}

EVENT_TYPE_TO_UNKNOWN = {"glitch_in_the_matrix"}
EVENT_TYPES = {
    "content_open",
    "content_complete",
    "like",
    "share",
    "search_query",
    "comment_post",
    "download",
    "page_view",
    "subscription_cancel",
    "subscription_start",
    "unknown",
}
EVENTS_WITHOUT_CONTENT = {
    "search_query",
    "page_view",
    "subscription_start",
    "subscription_cancel",
}
EVENTS_WITH_CONTENT = {
    "content_open",
    "content_complete",
    "like",
    "share",
    "comment_post",
    "download",
}

# Named event counts on the content mart. Anything else, including unknown, is other_events.
CONTENT_EVENT_COLUMNS = {
    "content_open": "content_opens",
    "content_complete": "content_completes",
    "like": "likes",
    "share": "shares",
    "comment_post": "comments",
    "download": "downloads",
}


def runtime_is_invalid(value):
    number = float(value)
    return number < 0 or number >= 99999


def follower_count_is_invalid(value):
    number = float(value)
    return number < 0 or number >= 999999


def price_is_invalid(value):
    number = float(value)
    return number < 0 or number >= 999


def duration_is_invalid(value):
    number = float(value)
    return number < 0 or number in (86400, 604800)
