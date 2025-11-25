"""
データベースユーティリティ
接続管理とクエリヘルパー
"""
import sqlite3
import streamlit as st
from contextlib import contextmanager
from config.settings import DATABASE_PATH


@contextmanager
def get_db_connection():
    """
    データベース接続のコンテキストマネージャー
    自動的に接続を開閉する

    使用例:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM races")
            results = cursor.fetchall()
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        yield conn
    except sqlite3.Error as e:
        st.error(f"データベースエラー: {e}")
        raise
    finally:
        if conn:
            conn.close()


@st.cache_data(ttl=600)  # 10分間キャッシュ
def execute_cached_query(query, params=None):
    """
    キャッシュ付きクエリ実行
    読み取り専用クエリに使用

    Args:
        query: SQLクエリ文字列
        params: クエリパラメータ（タプルまたはリスト）

    Returns:
        クエリ結果のリスト
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            results = cursor.fetchall()
            return results
    except Exception as e:
        st.error(f"クエリ実行エラー: {e}")
        return []


def execute_write_query(query, params=None, commit=True):
    """
    書き込みクエリ実行
    INSERT/UPDATE/DELETE用

    Args:
        query: SQLクエリ文字列
        params: クエリパラメータ（タプルまたはリスト）
        commit: 自動コミットするか

    Returns:
        影響を受けた行数
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if commit:
                conn.commit()

            return cursor.rowcount
    except Exception as e:
        st.error(f"クエリ実行エラー: {e}")
        return 0


def safe_query_to_df(query, params=None):
    """
    クエリ結果をpandas DataFrameで返す（安全版）

    Args:
        query: SQLクエリ文字列
        params: クエリパラメータ

    Returns:
        pandas DataFrame
    """
    import pandas as pd

    try:
        with get_db_connection() as conn:
            if params:
                df = pd.read_sql_query(query, conn, params=params)
            else:
                df = pd.read_sql_query(query, conn)
            return df
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return pd.DataFrame()
