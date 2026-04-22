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

    # 崩壊検知モニター
    st.markdown("### 🔍 崩壊検知モニター")
    render_rolling_roi_monitor()

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


@st.cache_data(ttl=3600)  # 1時間キャッシュ（確認頻度が低いため）
def _load_rolling_roi_data(start_date: str, end_date: str):
    """崩壊検知モニターのデータを取得（キャッシュ付き）"""
    import sys
    import os
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from scripts.analysis.rolling_roi_monitor import (
        get_per_race_results, calc_window_roi, assess_status,
        DEFAULT_WINDOW1, DEFAULT_WINDOW2, PRIORITY_CONDITIONS
    )
    from config.bet_conditions import STANDARD_BET_CONDITIONS

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    rows = []
    all_results_flat = []

    for cond in sorted(STANDARD_BET_CONDITIONS, key=lambda x: x.get('priority', 999)):
        results = get_per_race_results(cursor, cond, start_date, end_date)

        roi_long,  n_long,  _  = calc_window_roi(results, DEFAULT_WINDOW1)
        roi_short, n_short, _  = calc_window_roi(results, DEFAULT_WINDOW2)
        status, reason         = assess_status(roi_long, n_long, roi_short, n_short,
                                               DEFAULT_WINDOW1, DEFAULT_WINDOW2)

        total_inv  = sum(r[2] for r in results)
        total_pay  = sum(r[3] for r in results)
        total_hits = sum(r[4] for r in results)
        total_bets = len(results)
        all_roi    = 100.0 * total_pay / total_inv if total_inv > 0 else 0.0

        # 統計的文脈（誤検知確率）
        false_alarm_pct = None
        if status in ('STOP', 'WARNING') and total_bets > 0 and total_hits > 0:
            hit_rate = total_hits / total_bets
            # 短期ウィンドウが割れているほうで計算
            n_check = n_short if (roi_short is not None and roi_short < 80) else n_long
            false_alarm_pct = (1.0 - hit_rate) ** n_check * 100.0 if n_check > 0 else None

        rows.append({
            'id': cond['id'],
            'is_priority': cond['id'] in PRIORITY_CONDITIONS,
            'status': status,
            'reason': reason,
            'total_bets': total_bets,
            'all_roi': all_roi,
            'all_profit': total_pay - total_inv,
            'total_hits': total_hits,
            'roi_long': roi_long,
            'n_long': n_long,
            'roi_short': roi_short,
            'n_short': n_short,
            'false_alarm_pct': false_alarm_pct,
        })
        all_results_flat.extend(results)

    conn.close()
    return rows, all_results_flat, DEFAULT_WINDOW1, DEFAULT_WINDOW2


def render_rolling_roi_monitor():
    """崩壊検知モニター UI"""
    st.caption(
        "各条件の直近100件・50件ROIを監視し、パフォーマンス崩壊を早期検知します。"
        "　WARNING: 片方ROI < 80%　/　STOP: 両方ROI < 80%"
    )

    # 期間選択（サイドバーでなくインライン）
    col_s, col_e, col_btn = st.columns([2, 2, 1])
    with col_s:
        start_date = st.date_input(
            "開始日", value=datetime(2026, 1, 1).date(), key="monitor_start"
        ).strftime('%Y-%m-%d')
    with col_e:
        end_date = st.date_input(
            "終了日", value=datetime.today().date(), key="monitor_end"
        ).strftime('%Y-%m-%d')
    with col_btn:
        st.write("")
        refresh = st.button("🔄 再取得", key="monitor_refresh", use_container_width=True)
        if refresh:
            st.cache_data.clear()

    with st.spinner("条件別ローリングROIを計算中..."):
        try:
            rows, all_results_flat, w1, w2 = _load_rolling_roi_data(start_date, end_date)
        except Exception as e:
            st.error(f"データ取得エラー: {e}")
            return

    if not rows:
        st.info("データがありません。期間を広げてください。")
        return

    # ステータスアイコン
    STATUS_ICON = {'OK': '✅', 'WARNING': '⚠️', 'STOP': '🛑', 'LOW_SAMPLE': '📊'}
    STATUS_COLOR = {'OK': 'green', 'WARNING': 'orange', 'STOP': 'red', 'LOW_SAMPLE': 'gray'}

    # アラートサマリー
    stops    = [r for r in rows if r['status'] == 'STOP']
    warnings = [r for r in rows if r['status'] == 'WARNING']
    ok_conds = [r for r in rows if r['status'] == 'OK']
    low_samp = [r for r in rows if r['status'] == 'LOW_SAMPLE']

    sum_cols = st.columns(4)
    sum_cols[0].metric("🛑 STOP",      len(stops))
    sum_cols[1].metric("⚠️ WARNING",   len(warnings))
    sum_cols[2].metric("✅ OK",         len(ok_conds))
    sum_cols[3].metric("📊 低サンプル", len(low_samp))

    if stops or warnings:
        alert_msg = ""
        if stops:
            alert_msg += f"**[STOP]** {', '.join(r['id'] for r in stops)}  \n"
        if warnings:
            alert_msg += f"**[WARNING]** {', '.join(r['id'] for r in warnings)}"
        st.warning(alert_msg)
        st.caption(
            "⚠️ STOP/WARNINGは**統計的誤検知の可能性**があります。"
            "三連単（的中率0.7-2%）では100件ウィンドウでも30-50%の確率で0的中になります。"
            "最終判断は**年次退出基準**（100件以上: 直近2年連続ROI<100%）で行ってください。"
        )

    st.markdown("---")

    # 条件別テーブル
    table_rows = []
    for r in rows:
        roi_l_str = f"{r['roi_long']:.1f}%" if r['roi_long'] is not None else "N/A"
        roi_s_str = f"{r['roi_short']:.1f}%" if r['roi_short'] is not None else "N/A"
        fa_str = f"{r['false_alarm_pct']:.0f}%" if r['false_alarm_pct'] is not None else ""
        table_rows.append({
            '': STATUS_ICON.get(r['status'], ''),
            '条件ID': ('★ ' if r['is_priority'] else '') + r['id'],
            '全期間ROI': f"{r['all_roi']:.1f}%",
            '全期間収支': f"{r['all_profit']:+,}円",
            '件数': r['total_bets'],
            f'直近{w1}件ROI': roi_l_str,
            f'直近{w2}件ROI': roi_s_str,
            '誤検知確率': fa_str,
            '状態': r['status'],
        })

    df = pd.DataFrame(table_rows)

    def highlight_status(row):
        s = row['状態']
        if s == 'STOP':
            return ['background-color: #ffcccc'] * len(row)
        elif s == 'WARNING':
            return ['background-color: #fff3cc'] * len(row)
        return [''] * len(row)

    styled = df.style.apply(highlight_status, axis=1)
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.caption(
        f"誤検知確率: 正常でもその確率でSTOP/WARNINGが発生します。"
        f"30%以上 → 誤検知の可能性: 高（何もしない）。"
        f"10%未満 → 本物の崩壊シグナルとして調査開始。"
    )


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
