"""Central policy values for Insane Deep Search."""

from __future__ import annotations

import dataclasses


USER_AGENT = "insane-deep-search/0.1 (+https://github.com/nunoiland/insane-deep-search)"

DEFAULT_PACKS = ("news", "community", "tech", "research")
VALID_PACKS = frozenset(DEFAULT_PACKS)
VALID_SOURCE_TYPES = frozenset({"news", "community", "developer", "registry", "research", "page"})

TRACKING_PARAMS = frozenset(
    {
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "msclkid",
        "ref_src",
    }
)

SKIP_LINK_EXTENSIONS = frozenset(
    {
        ".7z",
        ".avi",
        ".css",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".js",
        ".m4a",
        ".m4v",
        ".mov",
        ".mp3",
        ".mp4",
        ".ogg",
        ".png",
        ".rar",
        ".svg",
        ".tar",
        ".webm",
        ".webp",
        ".woff",
        ".woff2",
        ".zip",
    }
)

LOW_VALUE_LINK_HINTS = frozenset(
    {
        "/about",
        "/account",
        "/accounts",
        "/advertise",
        "/auth",
        "/billing",
        "/captcha",
        "/checkout",
        "/contact",
        "/cookie",
        "/help",
        "/login",
        "/logout",
        "/paywall",
        "/privacy",
        "/register",
        "/search",
        "/share",
        "/signin",
        "/signup",
        "/subscribe",
        "/terms",
    }
)

LOW_VALUE_QUERY_PARAMS = frozenset({"active_tab", "activetab", "auth", "login", "share", "signup", "tab"})

STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "the",
        "to",
        "with",
        "관련",
        "검색",
        "뉴스",
        "정보",
        "확인",
        "찾아줘",
        "해외",
        "포함",
    }
)

BLOCKED_SIGNAL_CHECKS = {
    "captcha": "captcha",
    "access denied": "access denied",
    "checking your browser": "browser challenge",
    "verify you are human": "human verification",
    "unusual traffic": "unusual traffic",
    "temporarily blocked": "temporary block",
    "rate limit": "rate limit",
    "login required": "login required",
    "sign in to continue": "login required",
    "subscribe to continue": "paywall",
}

FETCH_VERDICT_BONUS = {
    "strong_ok": 5.0,
    "weak_ok": 2.0,
    "blocked": -1.0,
    "fail": -2.0,
    "weak_fail": -1.0,
}


@dataclasses.dataclass(frozen=True)
class FetchPolicy:
    blocked_statuses: frozenset[int] = frozenset({401, 403, 429})
    weak_failure_min_status: int = 500
    strong_min_bytes: int = 1200
    weak_min_bytes: int = 200


@dataclasses.dataclass(frozen=True)
class RankingPolicy:
    default_trust_weight: float = 1.0
    max_query_match_score: float = 12.0
    max_engagement_score: float = 8.0
    strong_research_threshold: float = 13.0
    strong_news_threshold: float = 12.0
    medium_default_threshold: float = 9.0
    medium_community_threshold: float = 12.0


@dataclasses.dataclass(frozen=True)
class DiscoveryPolicy:
    default_dig_pages: int = 8
    default_max_page_links: int = 12
    body_parse_limit: int = 500_000
    link_text_limit: int = 240
    candidate_limit: int = 60
    domain_limit: int = 3
    max_depth: int = 1
    trust_weight: float = 1.8
    article_path_bonus: float = 1.0
    text_hit_score: float = 2.5
    url_hit_score: float = 1.0


FETCH_POLICY = FetchPolicy()
RANKING_POLICY = RankingPolicy()
DISCOVERY_POLICY = DiscoveryPolicy()
