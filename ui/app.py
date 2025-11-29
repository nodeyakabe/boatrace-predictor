"""
コンドル - 競艇予想システム
4タブ構成: データ参照、レース予想、データ準備、設定・管理
"""

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config.settings import DATABASE_PATH, VENUES
from src.database.views import initialize_views

# 共通コンポーネント
from ui.components.common.filters import render_sidebar_filters
from ui.components.common.db_utils import get_db_connection, safe_query_to_df

# Tab1: データ参照
from ui.components.venue_analysis import render_venue_analysis_page
from ui.components.racer_analysis import render_racer_analysis_page
from ui.components.pattern_analysis import render_pattern_analysis_page

# Tab2: レース予想（統合版） - 遅延インポートに変更
# from ui.components.unified_race_list import render_unified_race_list, check_and_show_detail, get_selected_race
# from ui.components.unified_race_detail import render_unified_race_detail
# from ui.components.bet_history import render_bet_history_page
# from ui.components.backtest import render_backtest_page

# Tab3: データ準備 (遅延インポートに変更)
# from ui.components.workflow_manager import render_workflow_manager
# from ui.components.bulk_data_collector import render_bulk_data_collector
# from ui.components.model_training import render_model_training_page
# from ui.components.auto_data_collector import render_auto_data_collector
# from ui.components.data_quality_monitor import render_data_quality_monitor
# from ui.components.advanced_training import render_advanced_training, render_model_benchmark

# Tab4: 設定・管理
from ui.components.data_export import render_data_export_page, render_past_races_summary, render_ai_analysis_export
from ui.components.system_monitor import render_system_monitor


def main():
    st.set_page_config(
        page_title="コンドル - 競艇予想システム",
        page_icon="🦅",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # データベースビューを初期化
    try:
        initialize_views(DATABASE_PATH)
    except Exception as e:
        st.warning(f"ビュー初期化エラー: {e}")

    st.title("🦅 コンドル")

    # サイドバー
    with st.sidebar:
        st.header("メニュー")
        st.info("データベース: " + DATABASE_PATH)

        st.markdown("---")

        # グローバルフィルター
        target_date, selected_venues = render_sidebar_filters()

    # メインタブ（4タブ構成）
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 データ参照",
        "🔮 レース予想",
        "🔧 データ準備",
        "⚙️ 設定・管理"
    ])

    # Tab 1: データ参照
    with tab1:
        st.header("📊 データ参照")

        data_view = st.selectbox(
            "表示内容を選択",
            ["レース結果", "会場分析", "選手分析", "パターン分析", "統計情報"]
        )

        if data_view == "レース結果":
            render_race_results_view(target_date, selected_venues)

        elif data_view == "会場分析":
            render_venue_analysis_page()

        elif data_view == "選手分析":
            render_racer_analysis_page()

        elif data_view == "パターン分析":
            render_pattern_analysis_page()

        elif data_view == "統計情報":
            render_statistics_view()

    # Tab 2: レース予想（統合版）
    with tab2:
        st.header("🔮 レース予想")

        # 遅延インポート
        from ui.components.unified_race_list import render_unified_race_list, check_and_show_detail, get_selected_race
        from ui.components.unified_race_detail import render_unified_race_detail

        # 詳細画面への遷移チェック
        if check_and_show_detail():
            selected_race = get_selected_race()
            if selected_race:
                render_unified_race_detail(
                    race_date=selected_race['race_date'],
                    venue_code=selected_race['venue_code'],
                    race_number=selected_race['race_number'],
                    predictions=selected_race.get('predictions')
                )
            else:
                render_unified_race_list()
        else:
            # 通常の予想モード選択
            prediction_mode = st.selectbox(
                "予想モードを選択",
                ["レース一覧・推奨", "レース詳細分析", "購入履歴", "バックテスト"]
            )

            if prediction_mode == "レース一覧・推奨":
                render_unified_race_list()

            elif prediction_mode == "レース詳細分析":
                render_unified_race_detail()

            elif prediction_mode == "購入履歴":
                from ui.components.bet_history import render_bet_history_page
                render_bet_history_page()

            elif prediction_mode == "バックテスト":
                from ui.components.backtest import render_backtest_page
                render_backtest_page()

    # Tab 3: データ準備
    with tab3:
        st.header("🔧 データ準備")

        preparation_mode = st.selectbox(
            "準備内容を選択",
            ["📋 データメンテナンス", "ワークフロー自動化", "オッズ自動取得", "高度なモデル学習", "モデルベンチマーク", "自動データ収集", "手動データ収集", "モデル学習", "データ品質"]
        )

        if preparation_mode == "📋 データメンテナンス":
            from ui.components.data_maintenance import render_data_maintenance
            render_data_maintenance()

        elif preparation_mode == "ワークフロー自動化":
            from ui.components.workflow_manager import render_workflow_manager
            render_workflow_manager()

        elif preparation_mode == "オッズ自動取得":
            from ui.components.odds_fetcher_ui import render_odds_fetcher
            render_odds_fetcher()

        elif preparation_mode == "高度なモデル学習":
            from ui.components.advanced_training import render_advanced_training
            render_advanced_training()

        elif preparation_mode == "モデルベンチマーク":
            from ui.components.advanced_training import render_model_benchmark
            render_model_benchmark()

        elif preparation_mode == "自動データ収集":
            from ui.components.auto_data_collector import render_auto_data_collector
            render_auto_data_collector()

        elif preparation_mode == "手動データ収集":
            from ui.components.bulk_data_collector import render_bulk_data_collector
            render_bulk_data_collector(target_date, selected_venues)

        elif preparation_mode == "モデル学習":
            from ui.components.model_training import render_model_training_page
            render_model_training_page()

        elif preparation_mode == "データ品質":
            from ui.components.data_quality_monitor import render_data_quality_monitor
            render_data_quality_monitor()

    # Tab 4: 設定・管理
    with tab4:
        st.header("⚙️ 設定・管理")

        settings_mode = st.selectbox(
            "管理内容を選択",
            ["予測精度改善", "システム設定", "データ管理", "法則管理", "システム監視"]
        )

        if settings_mode == "予測精度改善":
            from ui.components.improvements_display import render_improvements_summary_page
            render_improvements_summary_page()

        elif settings_mode == "システム設定":
            render_system_settings()

        elif settings_mode == "データ管理":
            render_data_management()

        elif settings_mode == "法則管理":
            render_rule_management()

        elif settings_mode == "システム監視":
            render_system_monitor()


def render_race_results_view(target_date, selected_venues):
    """レース結果ビュー"""
    st.subheader("🏁 レース結果")

    try:
        # 日付範囲選択
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("開始日", target_date - timedelta(days=7))
        with col2:
            end_date = st.date_input("終了日", target_date)

        # 結果クエリ
        query = """
            SELECT
                r.race_date,
                r.venue_code,
                r.race_number,
                MAX(CASE WHEN res.rank = 1 THEN res.pit_number END) as first,
                MAX(CASE WHEN res.rank = 2 THEN res.pit_number END) as second,
                MAX(CASE WHEN res.rank = 3 THEN res.pit_number END) as third
            FROM races r
            LEFT JOIN results res ON r.id = res.race_id
            WHERE res.rank <= 3
              AND r.race_date BETWEEN ? AND ?
        """

        params = [start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")]

        if selected_venues:
            placeholders = ','.join('?' * len(selected_venues))
            query += f" AND r.venue_code IN ({placeholders})"
            params.extend(selected_venues)

        query += """
            GROUP BY r.id, r.race_date, r.venue_code, r.race_number
            ORDER BY r.race_date DESC, r.race_number DESC
            LIMIT 100
        """

        # 改善: DB接続管理を使用
        df = safe_query_to_df(query, params=params)

        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.info(f"表示件数: {len(df)}件")
        else:
            st.warning("該当するレース結果がありません")

    except Exception as e:
        st.error(f"エラー: {e}")


def render_statistics_view():
    """統計情報ビュー"""
    st.subheader("📈 統計情報")

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        col1, col2, col3 = st.columns(3)

        with col1:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM races")
            total_races = cursor.fetchone()[0]
            st.metric("総レース数", f"{total_races:,}")

        with col2:
            cursor.execute("SELECT COUNT(*) FROM entries")
            total_entries = cursor.fetchone()[0]
            st.metric("総出走表数", f"{total_entries:,}")

        with col3:
            cursor.execute("SELECT COUNT(*) FROM results")
            total_results = cursor.fetchone()[0]
            st.metric("総結果数", f"{total_results:,}")

        # データ期間
        st.markdown("---")
        st.subheader("📅 データ期間")
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
        min_date, max_date = cursor.fetchone()

        if min_date and max_date:
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"最古データ: {min_date}")
            with col2:
                st.info(f"最新データ: {max_date}")

        conn.close()

    except Exception as e:
        st.error(f"エラー: {e}")




def render_system_settings():
    """システム設定"""
    st.subheader("⚙️ システム設定")

    st.text(f"データベースパス: {DATABASE_PATH}")

    st.markdown("---")
    st.subheader("競艇場一覧")

    venues_list = list(VENUES.items())
    for venue_id, venue_info in venues_list:
        st.text(f"{venue_info['code']}: {venue_info['name']}")


def render_data_management():
    """データ管理"""
    st.subheader("💾 データ管理")

    management_task = st.radio(
        "管理タスクを選択",
        ["AI解析用エクスポート", "データエクスポート", "過去レース統計", "データ削除"]
    )

    if management_task == "AI解析用エクスポート":
        render_ai_analysis_export()

    elif management_task == "データエクスポート":
        render_data_export_page()

    elif management_task == "過去レース統計":
        render_past_races_summary()

    elif management_task == "データ削除":
        st.warning("⚠️ データ削除機能は慎重に使用してください")
        st.info("この機能は今後実装予定です")


def render_rule_management():
    """法則管理"""
    st.subheader("📜 法則管理")

    try:
        conn = sqlite3.connect(DATABASE_PATH)

        # 有効な法則を取得
        query = """
            SELECT rule_type, COUNT(*) as count
            FROM venue_rules
            WHERE is_active = 1
            GROUP BY rule_type
            ORDER BY count DESC
        """
        df_active = pd.read_sql_query(query, conn)

        if not df_active.empty:
            st.markdown("**📊 適用中の法則**")
            st.dataframe(df_active, use_container_width=True, hide_index=True)

        # 全法則の一覧
        st.markdown("---")
        st.markdown("**🎛️ 法則の有効/無効切り替え**")

        query_all = """
            SELECT id, venue_code, description, is_active
            FROM venue_rules
            ORDER BY is_active DESC, id
            LIMIT 50
        """
        df_all = pd.read_sql_query(query_all, conn)

        for idx, rule in df_all.iterrows():
            col1, col2 = st.columns([1, 5])

            with col1:
                current_state = bool(rule['is_active'])
                new_state = st.checkbox(
                    "有効",
                    value=current_state,
                    key=f"rule_{rule['id']}"
                )

                if new_state != current_state:
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE venue_rules SET is_active = ? WHERE id = ?",
                        (1 if new_state else 0, rule['id'])
                    )
                    conn.commit()
                    st.rerun()

            with col2:
                venue_tag = f"[{rule['venue_code']}]" if rule['venue_code'] else "[全国]"
                st.write(f"{venue_tag} {rule['description']}")

        conn.close()

    except Exception as e:
        st.error(f"エラー: {e}")


if __name__ == "__main__":
    main()
