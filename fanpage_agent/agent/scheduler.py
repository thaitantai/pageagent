"""Scheduler — re-exported from root scheduler.

Maintains backward compatibility for ``from fanpage_agent.agent.scheduler import ...``.
"""

from scheduler import (  # noqa: F401
    daemon,
    load_config,
    main,
    tick,
)
