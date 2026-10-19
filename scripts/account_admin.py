"""仅本机可信部署者使用；密码只通过终端隐藏输入，不接受命令行或环境变量传密。"""
from __future__ import annotations

import argparse
from contextlib import closing
from getpass import GetPassWarning, getpass
from pathlib import Path
import sqlite3
import sys
import warnings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pydantic import TypeAdapter, ValidationError

from backend.app.core.database import SCHEMA_VERSION
from backend.app.core.security import hash_password
from backend.app.repositories_account import replace_password_and_revoke_sessions
from backend.app.schemas import NewPassword


def _hidden_password(prompt: str) -> str:
    # getpass 的兜底会回显；无法关闭回显时应在读取秘密之前终止。
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            return getpass(prompt)
    except GetPassWarning:
        raise ValueError("当前终端无法隐藏输入，已取消；请使用支持隐藏输入的本机终端。") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机正式账号密码重置；操作前必须线下核验账号所有者身份。")
    parser.add_argument("--database", required=True, type=Path, help="已升级到当前版本的 SQLite 文件绝对路径")
    parser.add_argument("--username", required=True, help="要恢复的正式账号用户名")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        print("必须在本机交互终端运行；不接受管道、参数或环境变量传入密码。", file=sys.stderr)
        return 1
    if not args.database.is_absolute() or not args.database.is_file():
        print("请指定现有数据库的绝对路径，不会自动创建数据库。", file=sys.stderr)
        return 1
    try:
        with closing(sqlite3.connect(args.database.resolve().as_uri() + "?mode=rw", uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise ValueError("数据库版本不匹配，请先使用当前版本完成向前迁移。")
            username = args.username.strip().lower()
            account = conn.execute("SELECT id,is_guest,password_hash FROM users WHERE username=?", (username,)).fetchone()
            if not account or account["is_guest"]:
                raise ValueError("未找到正式账号；访客须在有效会话中先保存账号。")
            print(f"数据库：{args.database.resolve()}\n目标用户名：{username}\n将保留用户 ID 和全部业务数据，撤销全部会话与恢复码。")
            if input("已线下核验身份，请再次输入完整用户名确认（其他输入取消）：") != username:
                print("已取消，未修改账号。")
                return 1
            password = _hidden_password("新密码（8–64 位，隐藏输入）：")
            try:
                TypeAdapter(NewPassword).validate_python(password)
            except ValidationError:
                raise ValueError("新密码必须为 8–64 位，且不能全为空格。") from None
            if _hidden_password("再次输入新密码：") != password:
                raise ValueError("两次密码不一致，未修改账号。")
            password_hash = hash_password(password)
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute("SELECT id,is_guest,password_hash FROM users WHERE username=?", (username,)).fetchone()
                if not current or current["is_guest"] or dict(current) != dict(account):
                    raise ValueError("账号已变化，请重新核验后操作。")
                replace_password_and_revoke_sessions(conn, account["id"], password_hash)
            print("密码已重置；全部会话和旧恢复码已撤销。请用户登录后自行生成新恢复码。")
        return 0
    except (ValueError, EOFError, KeyboardInterrupt) as exc:
        print(str(exc) or "已取消，未修改账号。", file=sys.stderr)
        return 1
    except sqlite3.Error:
        print("数据库操作失败，事务已回滚；请检查文件权限、版本和占用情况。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
