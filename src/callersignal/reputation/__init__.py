"""Rights-gated caller-reputation feed integration."""

from callersignal.reputation.feed import (
    AuthorizedReputationAdapter,
    FeedHttpResponse,
    HttpsJsonTransport,
    ReputationFeedDefinition,
)
from callersignal.reputation.ingest import (
    ReputationFeedActivation,
    ReputationRefreshScheduler,
    SourceActivation,
    activate_reputation_feeds,
)

__all__ = [
    "AuthorizedReputationAdapter",
    "FeedHttpResponse",
    "HttpsJsonTransport",
    "ReputationFeedActivation",
    "ReputationFeedDefinition",
    "ReputationRefreshScheduler",
    "SourceActivation",
    "activate_reputation_feeds",
]
