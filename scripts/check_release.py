from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.config import get_settings, validate_startup_settings
from backend.app.core.database import SCHEMA_VERSION, init_db
from backend.app.core.backup import validate_database


def main() -> None:
    settings = get_settings()
    validate_startup_settings(settings)
    init_db()
    version = validate_database(Path(settings.db_path))
    if version != SCHEMA_VERSION:
        raise SystemExit(f"Schema 版本错误：{version}，目标版本：{SCHEMA_VERSION}")
    print(f"发布配置检查通过：environment={settings.environment} schema={version} debug={settings.debug}")


if __name__ == "__main__":
    main()
