"""TelegramFormatterTool assembled from domain-specific mixins.

Each mixin lives in its own module under formatters/:
  helpers   — static/helper methods (_parse_now, _age_hours, …)
  plan      — format_weekly_plan, format_caption_package
  report    — format_weekly_report, format_metrics_auto_fetch, format_analytics_review
  triage    — format_community_triage, format_approval_queue, format_approval_audit,
              format_approved_triage_replies, format_operator_digest, format_metrics_backlog
  research  — format_research_brief, format_hashtag_set
"""

from fanpage_agent.tools.publishing.formatters.helpers import _HelpersMixin
from fanpage_agent.tools.publishing.formatters.plan import _PlanMixin
from fanpage_agent.tools.publishing.formatters.report import _ReportMixin
from fanpage_agent.tools.publishing.formatters.triage import _TriageMixin
from fanpage_agent.tools.publishing.formatters.research import _ResearchMixin


class TelegramFormatterTool(
    _HelpersMixin,
    _PlanMixin,
    _ReportMixin,
    _TriageMixin,
    _ResearchMixin,
):
    """Formats structured JSON payloads into Telegram-friendly Markdown messages.

    The class is composed from domain-specific mixins for maintainability.
    Each mixin lives in its own module under formatters/.
    """
