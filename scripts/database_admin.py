from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.backup import create_backup, restore_backup, validate_database
from backend.app.core.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="云寻 SQLite 备份与恢复工具；恢复时必须先停止后端。")
    subparsers = parser.add_subparsers(dest="command", required=True)
    backup = subparsers.add_parser("backup")
    backup.add_argument("--dir", default="backups")
    backup.add_argument("--keep", type=int, default=10)
    restore = subparsers.add_parser("restore")
    restore.add_argument("file")
    restore.add_argument("--dir", default="backups")
    verify = subparsers.add_parser("verify")
    verify.add_argument("file")
    rehearse = subparsers.add_parser("rehearse-restore")
    rehearse.add_argument("file")
    args = parser.parse_args()
    database = Path(get_settings().db_path)
    if args.command == "backup":
        result = create_backup(database, Path(args.dir), keep=max(1, args.keep))
        print(f"备份完成：{result}")
    elif args.command == "restore":
        safety = restore_backup(database, Path(args.file), Path(args.dir))
        print(f"恢复完成；恢复前备份：{safety}。请重启后端。")
    elif args.command == "verify":
        version = validate_database(Path(args.file))
        print(f"数据库有效，Schema 版本：{version}")
    else:
        import sqlite3
        import tempfile
        from contextlib import closing

        source = Path(args.file)
        validate_database(source)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "restored.db"
            with closing(sqlite3.connect(source)) as source_conn, closing(sqlite3.connect(target)) as target_conn:
                source_conn.backup(target_conn)
            version = validate_database(target)
            print(f"恢复演练通过：Schema 版本 {version}，未覆盖正式数据库。")


if __name__ == "__main__":
    main()
