"""
コンドル - 競艇予想システム
4タブ構成: データ参照、レース予想、データ準備、設定・管理
バックグラウンド処理対応版
"""

import streamlit as st
import sqlite3
import pandas as pd
import math
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

# グローバル進捗表示
from ui.components.global_progress import render_global_progress, show_job_complete_notification

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

    # データベースビューを初期化（セッション状態で1回のみ実行）
    if 'views_initialized' not in st.session_state:
        try:
            initialize_views(DATABASE_PATH)
            st.session_state.views_initialized = True
        except Exception as e:
            st.warning(f"ビュー初期化エラー: {e}")

    st.title("🦅 コンドル")

    # グローバル進捗バー（ヘッダー部分に表示）
    render_global_progress()
    show_job_complete_notification()

    # サイドバー
    with st.sidebar:
        st.header("メニュー")
        st.info("データベース: " + DATABASE_PATH)

        st.markdown("---")

        # グローバルフィルター
        target_date, selected_venues = render_sidebar_filters()

    # メインタブ（4タブ構成）
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔮 レース予想",
        "🔧 データ準備",
        "📊 データ参照",
        "⚙️ 設定・管理"
    ])

    # Tab 1: レース予想（統合版）
    with tab1:
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
            # レース一覧を表示（総合タブが最初に表示される）
            render_unified_race_list()

    # Tab 2: データ準備
    with tab2:
        render_data_preparation_tab()

    # Tab 3: データ参照
    with tab3:
        render_data_reference_tab(target_date, selected_venues)

    # Tab 4: 設定・管理
    with tab4:
        st.header("⚙️ 設定・管理")

        settings_mode = st.selectbox(
            "管理内容を選択",
            ["予測精度改善", "オッズ自動取得", "モデル学習", "高度なモデル学習", "モデルベンチマーク", "システム設定", "データ管理", "法則管理", "システム監視"]
        )

        if settings_mode == "予測精度改善":
            from ui.components.improvements_display import render_improvements_summary_page
            render_improvements_summary_page()

        elif settings_mode == "オッズ自動取得":
            from ui.components.odds_fetcher_ui import render_odds_fetcher
            render_odds_fetcher()

        elif settings_mode == "モデル学習":
            from ui.components.model_training import render_model_training_page
            render_model_training_page()

        elif settings_mode == "高度なモデル学習":
            from ui.components.advanced_training import render_advanced_training
            render_advanced_training()

        elif settings_mode == "モデルベンチマーク":
            from ui.components.advanced_training import render_model_benchmark
            render_model_benchmark()

        elif settings_mode == "システム設定":
            render_system_settings()

        elif settings_mode == "データ管理":
            render_data_management()

        elif settings_mode == "法則管理":
            render_rule_management()

        elif settings_mode == "システム監視":
            render_system_monitor()


def render_data_preparation_tab():
    """データ準備タブ - 改善されたレイアウト"""
    from src.utils.job_manager import is_job_running, get_job_progress, cancel_job, start_job
    import os

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    JOB_TODAY_PREDICTION = 'today_prediction'
    JOB_TENJI = 'tenji_collection'
    JOB_MISSING_DATA = 'missing_data_fetch'

    # ヘッダー
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, rgba(33, 150, 243, 0.1) 0%, rgba(255,255,255,0.95) 100%);
        border-left: 4px solid #2196f3;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        <h2 style="margin: 0; color: #1565c0;">🔧 データ準備</h2>
        <p style="margin: 8px 0 0 0; color: #666;">今日の予測生成やデータ収集をワンクリックで実行</p>
    </div>
    """, unsafe_allow_html=True)

    # 実行中ジョブの状態表示
    running_jobs = []
    for job_name in [JOB_TODAY_PREDICTION, JOB_TENJI, JOB_MISSING_DATA]:
        if is_job_running(job_name):
            running_jobs.append((job_name, get_job_progress(job_name)))

    if running_jobs:
        st.markdown("### 🔄 実行中のジョブ")
        for job_name, progress in running_jobs:
            job_labels = {
                JOB_TODAY_PREDICTION: '今日の予測生成',
                JOB_TENJI: 'オリジナル展示収集',
                JOB_MISSING_DATA: 'データ収集'
            }
            label = job_labels.get(job_name, job_name)

            with st.container():
                col1, col2 = st.columns([5, 1])
                with col1:
                    pct = progress.get('progress', 0) if progress else 0
                    msg = progress.get('message', '処理中...') if progress else '処理中...'
                    st.progress(pct / 100, text=f"**{label}**: {msg}")
                with col2:
                    if st.button("⏹️", key=f"stop_{job_name}", help="停止"):
                        cancel_job(job_name)
                        st.rerun()

        import time
        time.sleep(3)
        st.rerun()

    # メインアクション - カード形式
    st.markdown("### 🚀 クイックアクション")

    col1, col2 = st.columns(2)

    with col1:
        # 今日の予測を生成カード
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, rgba(76, 175, 80, 0.15) 0%, white 100%);
            border: 1px solid #4caf50;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        ">
            <div style="font-size: 2em; margin-bottom: 8px;">🎯</div>
            <div style="font-size: 1.1em; font-weight: bold; color: #2e7d32;">今日の予測を生成</div>
            <div style="font-size: 0.85em; color: #666; margin-top: 4px;">スケジュール取得 → 出走表 → 予測生成</div>
        </div>
        """, unsafe_allow_html=True)

        if not is_job_running(JOB_TODAY_PREDICTION):
            if st.button("▶️ 実行", key="run_today_pred", type="primary", use_container_width=True):
                script_path = os.path.join(PROJECT_ROOT, 'scripts', 'background_today_prediction.py')
                result = start_job(JOB_TODAY_PREDICTION, script_path)
                if result['success']:
                    st.success("✅ 開始しました")
                    st.rerun()
                else:
                    st.error(result['message'])

    with col2:
        # オリジナル展示収集カード
        st.markdown("""
        <div style="
            background: linear-gradient(135deg, rgba(255, 152, 0, 0.15) 0%, white 100%);
            border: 1px solid #ff9800;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        ">
            <div style="font-size: 2em; margin-bottom: 8px;">📊</div>
            <div style="font-size: 1.1em; font-weight: bold; color: #e65100;">オリジナル展示収集</div>
            <div style="font-size: 0.85em; color: #666; margin-top: 4px;">直線・1周・回り足タイム等</div>
        </div>
        """, unsafe_allow_html=True)

        if not is_job_running(JOB_TENJI):
            col_t1, col_t2 = st.columns(2)
            with col_t1:
                if st.button("📅 今日", key="tenji_today", use_container_width=True):
                    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_tenji_collection.py')
                    result = start_job(JOB_TENJI, script_path, args=['0'])
                    if result['success']:
                        st.success("✅ 開始しました")
                        st.rerun()
            with col_t2:
                if st.button("📅 昨日", key="tenji_yesterday", use_container_width=True):
                    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_tenji_collection.py')
                    result = start_job(JOB_TENJI, script_path, args=['-1'])
                    if result['success']:
                        st.success("✅ 開始しました")
                        st.rerun()

    st.markdown("---")

    # データ収集セクション
    st.markdown("### 📥 データ収集")

    # 収集状況サマリー
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        cursor.execute("SELECT MAX(race_date) FROM races")
        latest = cursor.fetchone()[0]
        st.metric("最新データ", latest if latest else "N/A")
    with col2:
        today = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (today,))
        st.metric("本日のレース", cursor.fetchone()[0])
    with col3:
        cursor.execute("SELECT COUNT(*) FROM races")
        st.metric("総レース数", f"{cursor.fetchone()[0]:,}")
    with col4:
        cursor.execute("SELECT COUNT(*) FROM results")
        st.metric("結果データ", f"{cursor.fetchone()[0]:,}")
    conn.close()

    # 収集オプション
    with st.expander("📥 新規データ収集・補完", expanded=False):
        st.caption("指定期間のデータを収集します。既存データがある場合は自動でスキップされます。")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📅 今日", key="collect_today", use_container_width=True):
                _start_data_collection('today')
        with col2:
            if st.button("📅 今週", key="collect_week", use_container_width=True, type="primary"):
                _start_data_collection('week')
        with col3:
            if st.button("📅 期間指定...", key="collect_period", use_container_width=True):
                st.session_state['show_collect_period'] = True

        if st.session_state.get('show_collect_period'):
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("開始日", key="coll_start")
            with col2:
                end_date = st.date_input("終了日", key="coll_end")
            if st.button("✅ 実行", key="coll_exec"):
                _start_data_collection('period', start_date, end_date)
                st.session_state['show_collect_period'] = False

    # データ品質チェック
    with st.expander("🔍 データ品質チェック", expanded=False):
        if st.button("チェック実行", key="quality_check"):
            try:
                from src.analysis.data_coverage_checker import DataCoverageChecker
                checker = DataCoverageChecker(DATABASE_PATH)
                report = checker.get_coverage_report()
                overall = report.get('overall_score', 0)

                col1, col2 = st.columns([1, 3])
                with col1:
                    st.metric("充足率", f"{overall:.1f}%")
                with col2:
                    st.progress(overall / 100)

                if overall >= 0.8:
                    st.success("✅ データは充実しています")
                elif overall >= 0.5:
                    st.warning("⚠️ 一部データが不足しています")
                else:
                    st.error("❌ データが大幅に不足しています")
            except Exception as e:
                st.error(f"エラー: {e}")


def _start_data_collection(collection_type: str, start_date=None, end_date=None):
    """データ収集をバックグラウンドで開始"""
    from src.utils.job_manager import start_job
    import os

    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    JOB_MISSING_DATA = 'missing_data_fetch'

    if collection_type == 'today':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday
    elif collection_type == 'week':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday - timedelta(days=6)
        end_date = yesterday

    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'bulk_missing_data_fetch_parallel.py')
    args = ['--start-date', str(start_date), '--end-date', str(end_date)]

    result = start_job(JOB_MISSING_DATA, script_path, args=args)
    if result['success']:
        st.success(f"✅ {result['message']}")
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def render_data_reference_tab(target_date, selected_venues):
    """データ参照タブ - 改善されたレイアウト"""

    # ヘッダー
    st.markdown("""
    <div style="
        background: linear-gradient(135deg, rgba(156, 39, 176, 0.1) 0%, rgba(255,255,255,0.95) 100%);
        border-left: 4px solid #9c27b0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
    ">
        <h2 style="margin: 0; color: #7b1fa2;">📊 データ参照</h2>
        <p style="margin: 8px 0 0 0; color: #666;">レース結果・会場分析・選手分析など各種データを閲覧</p>
    </div>
    """, unsafe_allow_html=True)

    # タブで分類
    sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs([
        "🏁 レース結果",
        "🏟️ 会場分析",
        "👤 選手分析",
        "📈 統計・品質"
    ])

    with sub_tab1:
        _render_race_results_section(target_date, selected_venues)

    with sub_tab2:
        render_venue_analysis_page()

    with sub_tab3:
        render_racer_analysis_page()

    with sub_tab4:
        _render_statistics_section()


def _render_race_results_section(target_date, selected_venues):
    """レース結果セクション - 予想との照合（信頼度・払戻金付き）"""
    st.subheader("🏁 レース結果と予想の照合")

    col1, col2, col3 = st.columns(3)
    with col1:
        start_date = st.date_input("開始日", target_date - timedelta(days=7), key="res_start")
    with col2:
        end_date = st.date_input("終了日", target_date, key="res_end")
    with col3:
        prediction_type = st.selectbox("予想タイプ", ["advance", "before"], format_func=lambda x: "事前予想" if x == "advance" else "直前予想", key="pred_type")

    try:
        # レース結果を取得
        query = """
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                r.race_number,
                MAX(CASE WHEN res.rank = 1 THEN res.pit_number END) as result_1st,
                MAX(CASE WHEN res.rank = 2 THEN res.pit_number END) as result_2nd,
                MAX(CASE WHEN res.rank = 3 THEN res.pit_number END) as result_3rd
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

        query += " GROUP BY r.id ORDER BY r.race_date DESC, r.venue_code, r.race_number"

        df_results = safe_query_to_df(query, params=params)

        if df_results.empty:
            st.info("該当するレース結果がありません")
            return

        # 予想データを取得（信頼度も含む）
        race_ids = df_results['race_id'].tolist()
        if not race_ids:
            st.info("レースIDがありません")
            return

        placeholders = ','.join('?' * len(race_ids))
        pred_query = f"""
            SELECT race_id, pit_number, rank_prediction, confidence, total_score
            FROM race_predictions
            WHERE race_id IN ({placeholders})
              AND prediction_type = ?
        """
        pred_params = race_ids + [prediction_type]
        df_predictions = safe_query_to_df(pred_query, params=pred_params)

        # 三連単払戻金を取得（payoutsテーブルから）
        payout_query = f"""
            SELECT race_id, combination, amount
            FROM payouts
            WHERE race_id IN ({placeholders})
              AND bet_type = 'trifecta'
        """
        df_payouts = safe_query_to_df(payout_query, params=race_ids)

        # 払戻金辞書を作成（race_id -> {combination: amount}）
        payout_dict = {}
        for _, row in df_payouts.iterrows():
            race_id = row['race_id']
            if race_id not in payout_dict:
                payout_dict[race_id] = {}
            payout_dict[race_id][row['combination']] = row['amount']

        # 予想を整形（race_idごとに1位予想、2位予想、3位予想、信頼度を取得）
        pred_dict = {}
        for race_id in race_ids:
            race_preds = df_predictions[df_predictions['race_id'] == race_id]
            if not race_preds.empty:
                sorted_preds = race_preds.sort_values('rank_prediction')
                pred_1st = sorted_preds.iloc[0]['pit_number'] if len(sorted_preds) > 0 else None
                pred_2nd = sorted_preds.iloc[1]['pit_number'] if len(sorted_preds) > 1 else None
                pred_3rd = sorted_preds.iloc[2]['pit_number'] if len(sorted_preds) > 2 else None
                # 1位予想の信頼度とスコアを取得
                confidence = sorted_preds.iloc[0]['confidence'] if len(sorted_preds) > 0 else None
                total_score = sorted_preds.iloc[0]['total_score'] if len(sorted_preds) > 0 else None
                pred_dict[race_id] = (pred_1st, pred_2nd, pred_3rd, confidence, total_score)
            else:
                pred_dict[race_id] = (None, None, None, None, None)

        # 的中判定
        results_data = []
        hit_1st = 0
        hit_1st_2nd = 0
        hit_trifecta = 0
        total_with_pred = 0
        total_payout = 0  # 的中時の払戻金合計

        venue_map = {v['code']: v['name'] for v in VENUES.values()}

        for _, row in df_results.iterrows():
            race_id = row['race_id']
            venue_name = venue_map.get(row['venue_code'], row['venue_code'])

            result_1st = row['result_1st']
            result_2nd = row['result_2nd']
            result_3rd = row['result_3rd']

            # 結果の組み合わせから払戻金を取得（payoutsテーブルから直接取得）
            trifecta_payout = None
            if result_1st and result_2nd and result_3rd:
                combination = f"{int(result_1st)}-{int(result_2nd)}-{int(result_3rd)}"
                race_payouts = payout_dict.get(race_id, {})
                trifecta_payout = race_payouts.get(combination)

            pred = pred_dict.get(race_id, (None, None, None, None, None))
            pred_1st, pred_2nd, pred_3rd, confidence, total_score = pred

            # 信頼度表示
            if confidence:
                conf_map = {'high': '高', 'medium': '中', 'low': '低'}
                conf_display = conf_map.get(confidence, confidence)
            else:
                conf_display = '-'

            # 払戻金表示（NaNチェック）
            if trifecta_payout and not (isinstance(trifecta_payout, float) and math.isnan(trifecta_payout)):
                payout_display = f"¥{int(trifecta_payout):,}"
            else:
                payout_display = '-'

            # 的中判定
            if pred_1st is not None:
                total_with_pred += 1
                hit_1 = "◎" if pred_1st == result_1st else "×"
                hit_12 = "◎" if (pred_1st == result_1st and pred_2nd == result_2nd) else "×"
                hit_123 = "◎" if (pred_1st == result_1st and pred_2nd == result_2nd and pred_3rd == result_3rd) else "×"

                if hit_1 == "◎":
                    hit_1st += 1
                if hit_12 == "◎":
                    hit_1st_2nd += 1
                if hit_123 == "◎":
                    hit_trifecta += 1
                    if trifecta_payout and not (isinstance(trifecta_payout, float) and math.isnan(trifecta_payout)):
                        total_payout += trifecta_payout
            else:
                hit_1 = "-"
                hit_12 = "-"
                hit_123 = "-"

            results_data.append({
                '日付': row['race_date'],
                '会場': venue_name,
                'R': row['race_number'],
                '結果': f"{int(result_1st) if result_1st else '-'}-{int(result_2nd) if result_2nd else '-'}-{int(result_3rd) if result_3rd else '-'}",
                '予想': f"{int(pred_1st) if pred_1st else '-'}-{int(pred_2nd) if pred_2nd else '-'}-{int(pred_3rd) if pred_3rd else '-'}",
                '信頼度': conf_display,
                '1着': hit_1,
                '3連単': hit_123,
                '払戻金': payout_display
            })

        # 的中率サマリー
        if total_with_pred > 0:
            st.markdown("### 📊 的中率サマリー")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                rate_1st = hit_1st / total_with_pred * 100
                st.metric("1着的中", f"{hit_1st}/{total_with_pred}", f"{rate_1st:.1f}%")
            with col2:
                rate_12 = hit_1st_2nd / total_with_pred * 100
                st.metric("1-2着的中", f"{hit_1st_2nd}/{total_with_pred}", f"{rate_12:.1f}%")
            with col3:
                rate_tri = hit_trifecta / total_with_pred * 100
                st.metric("3連単的中", f"{hit_trifecta}/{total_with_pred}", f"{rate_tri:.1f}%")
            with col4:
                # 回収率（各レース100円賭けた場合）
                if total_with_pred > 0:
                    roi = (total_payout / (total_with_pred * 100)) * 100 if total_with_pred > 0 else 0
                    st.metric("回収率", f"{roi:.1f}%", f"¥{int(total_payout):,}")
            with col5:
                st.metric("予想あり", f"{total_with_pred}件", f"全{len(df_results)}件中")

            st.markdown("---")

        # 結果テーブル表示
        df_display = pd.DataFrame(results_data)

        # 的中マークに色付け
        def highlight_hit(val):
            if val == "◎":
                return 'background-color: #c8e6c9; color: #2e7d32; font-weight: bold;'
            elif val == "×":
                return 'background-color: #ffcdd2; color: #c62828;'
            return ''

        def highlight_confidence(val):
            if val == "高":
                return 'background-color: #e3f2fd; color: #1565c0; font-weight: bold;'
            elif val == "中":
                return 'background-color: #fff3e0; color: #e65100;'
            elif val == "低":
                return 'background-color: #fce4ec; color: #c2185b;'
            return ''

        styled_df = df_display.style.applymap(highlight_hit, subset=['1着', '3連単']).applymap(highlight_confidence, subset=['信頼度'])
        st.dataframe(styled_df, use_container_width=True, hide_index=True, height=400)
        st.caption(f"表示件数: {len(df_display)}件")

    except Exception as e:
        st.error(f"エラー: {e}")
        import traceback
        st.code(traceback.format_exc())


def _render_statistics_section():
    """統計・データ品質セクション"""

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📈 データ統計")

        try:
            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            # 統計カード
            stats = []
            cursor.execute("SELECT COUNT(*) FROM races")
            stats.append(("総レース数", f"{cursor.fetchone()[0]:,}"))

            cursor.execute("SELECT COUNT(*) FROM entries")
            stats.append(("出走表", f"{cursor.fetchone()[0]:,}"))

            cursor.execute("SELECT COUNT(*) FROM results")
            stats.append(("結果", f"{cursor.fetchone()[0]:,}"))

            cursor.execute("SELECT COUNT(*) FROM race_predictions")
            stats.append(("予想データ", f"{cursor.fetchone()[0]:,}"))

            cursor.execute("SELECT COUNT(*) FROM payouts")
            stats.append(("払戻金データ", f"{cursor.fetchone()[0]:,}"))

            cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
            min_d, max_d = cursor.fetchone()
            stats.append(("データ期間", f"{min_d} ～ {max_d}"))

            conn.close()

            for label, value in stats:
                st.markdown(f"""
                <div style="
                    background: #f5f5f5;
                    border-radius: 8px;
                    padding: 12px;
                    margin-bottom: 8px;
                    display: flex;
                    justify-content: space-between;
                ">
                    <span style="color: #666;">{label}</span>
                    <span style="font-weight: bold;">{value}</span>
                </div>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"統計取得エラー: {e}")

    with col2:
        st.markdown("#### 🔍 データ品質")

        try:
            from src.analysis.data_coverage_checker import DataCoverageChecker
            checker = DataCoverageChecker(DATABASE_PATH)
            report = checker.get_coverage_report()

            overall = report.get('overall_score', 0)
            overall_pct = overall * 100  # 0-1を0-100%に変換

            # 全体スコア表示
            color = "#4caf50" if overall_pct >= 80 else "#ff9800" if overall_pct >= 50 else "#f44336"
            st.markdown(f"""
            <div style="
                background: linear-gradient(135deg, rgba(0,0,0,0.02) 0%, white 100%);
                border: 2px solid {color};
                border-radius: 12px;
                padding: 20px;
                text-align: center;
            ">
                <div style="font-size: 2.5em; font-weight: bold; color: {color};">{overall_pct:.1f}%</div>
                <div style="color: #666;">データ充足率</div>
            </div>
            """, unsafe_allow_html=True)

            # カテゴリ別（上位5つ、プログレスバーは0-1の範囲でクリップ）
            st.markdown("")
            categories = report.get('categories', {})
            for cat_name, cat_data in list(categories.items())[:5]:
                items = cat_data.get('items', [])
                avg = sum(i.get('coverage', 0) for i in items) / len(items) if items else 0
                # プログレスバーは0-1の範囲に制限
                progress_val = min(1.0, max(0.0, avg))
                st.progress(progress_val, text=f"{cat_name}: {avg*100:.0f}%")

        except Exception as e:
            st.warning(f"品質チェック: {e}")

        if st.button("詳細を見る", key="quality_detail"):
            from ui.components.data_quality_monitor import render_data_quality_monitor
            render_data_quality_monitor()


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
