"""
簡易DB接続プール

DB接続の再利用により、大幅な速度向上を実現
"""

import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional


class DBConnectionPool:
    """
    シンプルなDB接続プール

    スレッドごとに1つの接続を保持し、再利用する
    """

    def __init__(self, db_path: str):
        """
        Args:
            db_path: データベースファイルのパス
        """
        self.db_path = db_path
        self._local = threading.local()

    def get_connection(self) -> sqlite3.Connection:
        """
        現在のスレッド用のDB接続を取得

        既存の接続があればそれを返し、なければ新規作成

        Returns:
            sqlite3.Connection: DB接続
        """
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_path,
                check_same_thread=False
            )
            self._local.connection.row_factory = sqlite3.Row

            # SQLite最適化設定
            cursor = self._local.connection.cursor()

            # WALモード有効化（並行読み取り性能向上）
            cursor.execute("PRAGMA journal_mode=WAL")

            # メモリキャッシュサイズ増加（64MB）
            cursor.execute("PRAGMA cache_size=-64000")

            # 同期モード最適化（安全性は保ちつつ高速化）
            cursor.execute("PRAGMA synchronous=NORMAL")

            # メモリマップI/O有効化（256MB）
            cursor.execute("PRAGMA mmap_size=268435456")

            # 一時ファイルをメモリに配置
            cursor.execute("PRAGMA temp_store=MEMORY")

            # クエリプランナーの最適化
            cursor.execute("PRAGMA optimize")

            cursor.close()

        return self._local.connection

    @contextmanager
    def get_cursor(self):
        """
        カーソルを取得するコンテキストマネージャー

        Yields:
            sqlite3.Cursor: DBカーソル
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
        finally:
            # カーソルは閉じるが接続は維持
            cursor.close()

    def close(self):
        """現在のスレッドの接続を閉じる"""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            self._local.connection.close()
            self._local.connection = None

    def close_all(self):
        """
        全ての接続を閉じる

        注意: 通常は不要。アプリケーション終了時のみ使用
        """
        self.close()


# グローバル接続プールインスタンス
_pool: Optional[DBConnectionPool] = None


def get_pool(db_path: str = "data/boatrace.db") -> DBConnectionPool:
    """
    グローバル接続プールを取得

    Args:
        db_path: データベースファイルのパス

    Returns:
        DBConnectionPool: 接続プール
    """
    global _pool
    if _pool is None or _pool.db_path != db_path:
        _pool = DBConnectionPool(db_path)
    return _pool


def get_connection(db_path: str = "data/boatrace.db") -> sqlite3.Connection:
    """
    DB接続を取得（簡易インターフェース）

    Args:
        db_path: データベースファイルのパス

    Returns:
        sqlite3.Connection: DB接続
    """
    return get_pool(db_path).get_connection()
