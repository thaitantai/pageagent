"""Project-wide Settings (re-exported from root config.py).

Maintains backward compatibility for ``from fanpage_agent.config import Settings``.
"""

from config import ConfigError, Settings, _load_root_dotenv, _parse_csv_list  # noqa: F401
