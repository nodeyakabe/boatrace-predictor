"""
データベース接続プール - 効率的なDB接続管理

スレッドセーフなコネクションプールを提供し、並列処理時のDB接続を最適化
"""
import sqlite3
import threading
import queue
import logging
from typing import Optional, Callable, TypeVar, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ConnectionPool:
    """
    SQLite接続プール

    使用例:
        pool = ConnectionPool('data/boatrace.db', pool_size=5)

        # コンテキストマネージャーで使用
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM races")

        # または関数実行
        result = pool.execute_query("SELECT COUNT(*) FROM races")
    """

    def __init__(self, db_path: str, pool_size: int = 5, timeout: float = 30.0):
        """
        Args:
            db_path: データベースファイルパス
            pool_size: プールサイズ（最大接続数）
            timeout: 接続取得タイムアウト（秒）
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self.timeout = timeout
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._closed = False

        # プールを初期化
        for _ in range(pool_size):
            conn = self._create_connection()
            self._pool.put(conn)

        logger.info(f"DB接続プール初期化完了: {pool_size}接続 ({db_path})")

    def _create_connection(self) -> sqlite3.Connection:
        """新しいDB接続を作成"""
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,  # スレッド間で接続を共有
            timeout=self.timeout
        )
        # WALモードを有効化（並列読み込みの最適化）
        conn.execute("PRAGMA journal_mode=WAL")
        # キャッシュサイズを増やす
        conn.execute("PRAGMA cache_size=-64000")  # 64MB
        return conn

    @contextmanager
    def get_connection(self):
        """
        接続をプールから取得（コンテキストマネージャー）

        使用例:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM races")
        """
        if self._closed:
            raise RuntimeError("接続プールは既に閉じられています")

        conn = None
        try:
            # プールから接続を取得
            conn = self._pool.get(timeout=self.timeout)
            yield conn
        except queue.Empty:
            raise TimeoutError(f"DB接続取得タイムアウト（{self.timeout}秒）")
        finally:
            if conn:
                # プールに接続を返却
                try:
                    conn.rollback()  # 未コミットのトランザクションをロールバック
                    self._pool.put(conn)
                except Exception as e:
                    logger.error(f"接続返却エラー: {e}")
                    # 接続が壊れている場合は新しい接続を作成
                    try:
                        conn.close()
                    except:
                        pass
                    new_conn = self._create_connection()
                    self._pool.put(new_conn)

    def execute_query(
        self,
        query: str,
        params: tuple = (),
        fetch_one: bool = False,
        fetch_all: bool = True
    ) -> Any:
        """
        クエリを実行

        Args:
            query: SQL クエリ
            params: パラメータタプル
            fetch_one: 単一行を取得
            fetch_all: 全行を取得

        Returns:
            クエリ結果
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            if fetch_one:
                return cursor.fetchone()
            elif fetch_all:
                return cursor.fetchall()
            else:
                return None

    def execute_many(
        self,
        query: str,
        params_list: list[tuple],
        commit: bool = True
    ) -> int:
        """
        バッチINSERT/UPDATE

        Args:
            query: SQL クエリ
            params_list: パラメータのリスト
            commit: コミットするか

        Returns:
            影響を受けた行数
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params_list)
            if commit:
                conn.commit()
            return cursor.rowcount

    def execute_script(self, script: str, commit: bool = True) -> None:
        """
        SQLスクリプトを実行

        Args:
            script: SQLスクリプト
            commit: コミットするか
        """
        with self.get_connection() as conn:
            conn.executescript(script)
            if commit:
                conn.commit()

    def close_all(self):
        """全接続を閉じる"""
        with self._lock:
            if self._closed:
                return

            self._closed = True

            # プール内の全接続を閉じる
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except (queue.Empty, Exception) as e:
                    logger.warning(f"接続クローズエラー: {e}")

            logger.info("DB接続プールをクローズしました")

    def __del__(self):
        """デストラクタ"""
        self.close_all()


# グローバル接続プール（シングルトン）
_global_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()


def get_global_pool(db_path: str = None, pool_size: int = 5) -> ConnectionPool:
    """
    グローバル接続プールを取得

    使用例:
        pool = get_global_pool('data/boatrace.db')
        with pool.get_connection() as conn:
            ...
    """
    global _global_pool

    if _global_pool is None:
        with _pool_lock:
            if _global_pool is None:
                if db_path is None:
                    import os
                    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
                    db_path = os.path.join(project_root, 'data/boatrace.db')

                _global_pool = ConnectionPool(db_path, pool_size=pool_size)

    return _global_pool


@contextmanager
def get_db_connection(db_path: str = None):
    """
    DB接続を取得（簡易版）

    使用例:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM races")
    """
    pool = get_global_pool(db_path)
    with pool.get_connection() as conn:
        yield conn


def execute_with_retry(
    func: Callable[[sqlite3.Connection], T],
    db_path: str = None,
    max_retries: int = 3
) -> T:
    """
    DB操作をリトライ付きで実行

    使用例:
        def my_query(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM races")
            return cursor.fetchall()

        results = execute_with_retry(my_query)

    Args:
        func: 実行する関数（接続を引数に取る）
        db_path: DBパス
        max_retries: 最大リトライ回数

    Returns:
        関数の戻り値
    """
    from src.utils.retry_handler import retry_with_backoff, DB_CONFIG

    @retry_with_backoff(config=DB_CONFIG, exceptions=(sqlite3.OperationalError,))
    def execute():
        with get_db_connection(db_path) as conn:
            return func(conn)

    return execute()


class BatchInserter:
    """
    バッチINSERTヘルパー

    使用例:
        inserter = BatchInserter(
            table="races",
            columns=["venue_code", "race_date", "race_number"],
            batch_size=100
        )

        for data in large_dataset:
            inserter.add(data['venue_code'], data['race_date'], data['race_number'])

        inserter.flush()  # 残りをINSERT
    """

    def __init__(
        self,
        table: str,
        columns: list[str],
        batch_size: int = 100,
        db_path: str = None,
        on_conflict: str = "IGNORE"
    ):
        """
        Args:
            table: テーブル名
            columns: カラム名リスト
            batch_size: バッチサイズ
            db_path: DBパス
            on_conflict: 重複時の動作（IGNORE, REPLACE, など）
        """
        self.table = table
        self.columns = columns
        self.batch_size = batch_size
        self.db_path = db_path
        self.on_conflict = on_conflict

        self._buffer: list[tuple] = []
        self._total_inserted = 0

        # INSERT文を準備
        columns_str = ', '.join(columns)
        placeholders = ', '.join(['?' for _ in columns])
        self._insert_sql = f"INSERT OR {on_conflict} INTO {table} ({columns_str}) VALUES ({placeholders})"

    def add(self, *values):
        """レコードを追加"""
        if len(values) != len(self.columns):
            raise ValueError(f"カラム数が一致しません: {len(values)} != {len(self.columns)}")

        self._buffer.append(values)

        # バッファが満タンになったらフラッシュ
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        """バッファをDBに書き込み"""
        if not self._buffer:
            return

        pool = get_global_pool(self.db_path)
        count = pool.execute_many(self._insert_sql, self._buffer, commit=True)

        self._total_inserted += len(self._buffer)
        logger.debug(f"バッチINSERT完了: {len(self._buffer)}件 ({self.table})")

        self._buffer.clear()

    def get_total_inserted(self) -> int:
        """総INSERT件数を取得"""
        return self._total_inserted

    def __enter__(self):
        """コンテキストマネージャー"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了時にフラッシュ"""
        self.flush()
