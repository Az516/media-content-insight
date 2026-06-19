"""Service layer for media-content-insight.

Modules in this package orchestrate the persistence layer
(:mod:`app.models`) plus external dependencies such as MediaCrawler
(``crawler_service``) and LLM providers (``ai_analyzer``). Pure
domain rules live here -- the API layer in :mod:`app.api` should
remain thin and delegate to these services.
"""

from app.services.ai_analyzer import (
    AIAnalyzer,
    AIReport,
    LLMError,
    PROMPT_V1,
)
from app.services.crawler_service import (
    CrawlerError,
    CrawlerService,
    CrawlResult,
    LoginExpiredError,
    RiskControlError,
    SubprocessOutcome,
)
from app.services.data_store import (
    AIReportInput,
    AIReportSummary,
    DataStore,
)

__all__ = [
    "AIAnalyzer",
    "AIReport",
    "AIReportInput",
    "AIReportSummary",
    "CrawlerError",
    "CrawlerService",
    "CrawlResult",
    "DataStore",
    "LLMError",
    "LoginExpiredError",
    "PROMPT_V1",
    "RiskControlError",
    "SubprocessOutcome",
]
