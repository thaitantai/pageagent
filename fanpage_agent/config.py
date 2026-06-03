"""Project-wide Settings (re-exported from root config.py).

Maintains backward compatibility for ``from fanpage_agent.config import Settings``.
"""

from config import Settings, _parse_csv_list, _load_root_dotenv  # noqa: F401
