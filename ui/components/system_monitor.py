"""
システム監視コンポーネント
"""
import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from config.settings import DATABASE_PATH
import os


def render_system_monitor():
    """システム監視ダッシュボード"""
    st.header("📊 システム監視")

    # システム概要
    st.markdown("### 🖥️ システム概要")

    col1, col2, col3 = st.columns(3)

    with col1:
        db_size = get_database_size()
        st.metric("DB サイズ", f"{db_size:.2f} MB")

    with col2:
        table_count = get_table_count()
        st.metric("テーブル数", table_count)

    with col3:
        last_update = get_last_update_time()
        st.metric("最終更新", last_update)

    st.markdown("---")

    # データベース統計
    st.markdown("### 📊 データベース統計")
    render_database_statistics()

    st.markdown("---")

    # 最近の活動
    st.markdown("### 📝 最近の活動")
    render_recent_activity()

    st.markdown("---")

    # エラーログ
    st.markdown("### ⚠️ エラーログ")
    render_error_logs()


def get_database_size():
    """データベースサイズを取得（MB）"""
    try:
        db_size = os.path.getsize(DATABASE_PATH)
        return db_size / (1024 * 1024)  # バイトをMBに変換
    except Exception:
        return 0.0


def get_table_count():
    """テーブル数を取得"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def get_last_update_time():
    """最終更新時刻を取得"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(race_date) FROM races")
        last_date = cursor.fetchone()[0]
        conn.close()
        return last_date if last_date else "N/A"
    except Exception:
        return "N/A"


def render_database_statistics():
    """データベース統計を表示"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # 主要テーブルの行数
        tables = [
            'races', 'entries', 'results', 'race_details',
            'weather', 'tide', 'venue_rules'
        ]

        stats = []
        for table in tables:
            try:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                stats.append({
                    'テーブル': table,
                    'レコード数': f"{count:,}"
                })
            except Exception:
                stats.append({
                    'テーブル': table,
                    'レコード数': 'N/A'
                })

        df_stats = pd.DataFrame(stats)
        st.dataframe(df_stats, use_container_width=True, hide_index=True)

        conn.close()

    except Exception as e:
        st.error(f"統計取得エラー: {e}")


def render_recent_activity():
    """最近の活動を表示"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # 最近追加されたレース
        query = """
            SELECT race_date, venue_code, race_number
            FROM races
            ORDER BY id DESC
            LIMIT 10
        """

        df = pd.read_sql_query(query, conn)

        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("最近の活動はありません")

        conn.close()

    except Exception as e:
        st.error(f"活動取得エラー: {e}")


def render_error_logs():
    """エラーログを表示"""
    st.info("エラーログ機能は今後実装予定です")

    # 簡易的なデータ整合性チェック
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # 結果のないレース
        cursor.execute("""
            SELECT COUNT(*)
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            WHERE res.id IS NULL
            AND r.race_date < date('now')
        """)
        no_result_count = cursor.fetchone()[0]

        if no_result_count > 0:
            st.warning(f"⚠️ 結果が登録されていない過去のレース: {no_result_count}件")
        else:
            st.success("✅ データ整合性: 問題なし")

        conn.close()

    except Exception as e:
        st.error(f"整合性チェックエラー: {e}")


def render_performance_metrics():
    """パフォーマンス指標を表示"""
    st.subheader("⚡ パフォーマンス指標")

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # クエリ実行時間の測定
        import time

        # テストクエリ1: レース総数
        start = time.time()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM races")
        cursor.fetchone()
        query1_time = (time.time() - start) * 1000

        # テストクエリ2: 複雑なJOIN
        start = time.time()
        cursor.execute("""
            SELECT r.race_date, COUNT(e.id)
            FROM races r
            LEFT JOIN entries e ON r.id = e.race_id
            GROUP BY r.race_date
            LIMIT 100
        """)
        cursor.fetchall()
        query2_time = (time.time() - start) * 1000

        col1, col2 = st.columns(2)

        with col1:
            st.metric("単純クエリ", f"{query1_time:.2f} ms")

        with col2:
            st.metric("複雑クエリ", f"{query2_time:.2f} ms")

        if query2_time > 1000:
            st.warning("⚠️ クエリ実行が遅い可能性があります。インデックスの最適化を検討してください")
        else:
            st.success("✅ クエリパフォーマンス: 良好")

        conn.close()

    except Exception as e:
        st.error(f"パフォーマンス測定エラー: {e}")
