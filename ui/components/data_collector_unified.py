"""
データ収集UI（統合版）

データ取得作業を一元管理:
- クイック収集（今日/明日/今週）
- 不足データ検出・取得（期間指定対応）
- オリジナル展示収集

バックグラウンドジョブ対応版
"""
import streamlit as st
import subprocess
import os
import sys
import json
from datetime import datetime, timedelta
import sqlite3
from typing import List, Dict
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH, VENUES
from src.utils.job_manager import (
    is_job_running, start_job, get_job_progress,
    cancel_job, get_all_jobs
)
from src.analysis.data_coverage_checker import DataCoverageChecker

# ジョブ名定数
JOB_TENJI = 'tenji_collection'
JOB_MISSING_DATA = 'missing_data_fetch'
JOB_DATA_COLLECTION = 'data_collection'


def render_data_collector():
    """データ収集UIのメインレンダリング"""
    st.header("📥 データ収集")

    # 実行中ジョブの状況表示
    _render_job_status_bar()

    st.markdown("データ取得作業を一元管理します。タブで作業を選択してください。")

    tab1, tab2, tab3 = st.tabs([
        "🚀 クイック収集",
        "🔍 不足データ検出",
        "🎯 オリジナル展示"
    ])

    with tab1:
        _render_quick_collection()

    with tab2:
        _render_missing_data_detector()

    with tab3:
        _render_original_tenji()


def _render_job_status_bar():
    """実行中ジョブのステータスバーを表示"""
    jobs = get_all_jobs()
    running_jobs = {k: v for k, v in jobs.items() if v.get('is_running')}

    if running_jobs:
        st.info("🔄 **バックグラウンドジョブ実行中** - タブを移動しても処理は継続します")

        for job_name, progress in running_jobs.items():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                job_label = {
                    JOB_TENJI: 'オリジナル展示収集',
                    JOB_MISSING_DATA: '不足データ取得'
                }.get(job_name, job_name)

                progress_val = progress.get('progress', 0)
                message = progress.get('message', '処理中...')

                st.progress(progress_val / 100, text=f"{job_label}: {message}")

            with col2:
                st.caption(f"進捗: {progress_val}%")

            with col3:
                if st.button("キャンセル", key=f"dc_cancel_{job_name}"):
                    cancel_job(job_name)
                    st.rerun()

        if st.button("🔄 状況を更新", key="dc_refresh_jobs"):
            st.rerun()

        st.markdown("---")

    # 完了したジョブの通知（5分以内）
    recent_completed = {k: v for k, v in jobs.items()
                        if v.get('status') in ['completed', 'failed', 'cancelled']
                        and not v.get('is_running')}

    for job_name, progress in recent_completed.items():
        status = progress.get('status')
        message = progress.get('message', '')
        completed_at = progress.get('completed_at', '')

        if completed_at:
            try:
                completed_time = datetime.fromisoformat(completed_at)
                if (datetime.now() - completed_time).seconds < 300:
                    if status == 'completed':
                        st.success(f"✅ {message}")
                    elif status == 'failed':
                        st.error(f"❌ {message}")
                    elif status == 'cancelled':
                        st.warning(f"⚠️ {message}")
            except:
                pass


def _render_quick_collection():
    """クイック収集タブ（2段階収集アプローチ）"""
    st.subheader("🚀 クイック収集")

    st.info("💡 **今日のデータ**は「ワークフロー自動化」タブの「今日の予想を準備」ボタンで一括取得できます")

    # 実行中ジョブの状態確認
    if is_job_running(JOB_DATA_COLLECTION):
        progress = get_job_progress(JOB_DATA_COLLECTION)
        st.warning("🔄 データ収集がバックグラウンドで実行中です")

        if progress:
            pct = progress.get('progress', 0)
            message = progress.get('message', '処理中...')
            step = progress.get('step', '')

            if step:
                st.text(f"{step}: {message}")
            else:
                st.text(message)
            st.progress(pct / 100)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 状況を更新", key="refresh_quick_collection"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_quick_collection"):
                    cancel_job(JOB_DATA_COLLECTION)
                    st.rerun()

        st.markdown("---")
        _render_collection_summary()
        return

    st.markdown("---")

    # ========== 第1段階: 基本データ収集 ==========
    st.markdown("### 📋 基本データ収集（速い）")
    st.caption("レース基本情報のみ収集。既存データはスキップして高速処理。")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📅 今日", key="basic_today", use_container_width=True):
            _start_basic_data_collection('today')

    with col2:
        if st.button("📅 今週", key="basic_week", use_container_width=True, type="primary"):
            _start_basic_data_collection('week')

    with col3:
        if st.button("📅 期間指定...", key="basic_period", use_container_width=True):
            st.session_state['show_basic_period_selector'] = True

    # 基本データ期間指定モーダル
    if st.session_state.get('show_basic_period_selector'):
        with st.expander("📅 基本データ収集 - 期間指定", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("開始日", key="basic_start_date")
            with col2:
                end_date = st.date_input("終了日", key="basic_end_date")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 実行", key="basic_period_exec"):
                    _start_basic_data_collection('period', start_date, end_date)
                    st.session_state['show_basic_period_selector'] = False
                    st.rerun()
            with col2:
                if st.button("❌ キャンセル", key="basic_period_cancel"):
                    st.session_state['show_basic_period_selector'] = False
                    st.rerun()

    st.markdown("---")

    # ========== 第2段階: 補完データ収集 ==========
    st.markdown("### 🔧 補完データ収集（詳細）")
    st.caption("結果・払戻金・決まり手など、欠損している詳細データを補完。")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔧 今日", key="complement_today", use_container_width=True):
            _start_complement_data_collection('today')

    with col2:
        if st.button("🔧 今週", key="complement_week", use_container_width=True, type="secondary"):
            _start_complement_data_collection('week')

    with col3:
        if st.button("🔧 期間指定...", key="complement_period", use_container_width=True):
            st.session_state['show_complement_period_selector'] = True

    # 補完データ期間指定モーダル
    if st.session_state.get('show_complement_period_selector'):
        with st.expander("🔧 補完データ収集 - 期間指定", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("開始日", key="complement_start_date")
            with col2:
                end_date = st.date_input("終了日", key="complement_end_date")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 実行", key="complement_period_exec"):
                    _start_complement_data_collection('period', start_date, end_date)
                    st.session_state['show_complement_period_selector'] = False
                    st.rerun()
            with col2:
                if st.button("❌ キャンセル", key="complement_period_cancel"):
                    st.session_state['show_complement_period_selector'] = False
                    st.rerun()

    # 収集状況サマリー
    st.markdown("---")
    _render_collection_summary()


def _render_collection_summary():
    """収集状況サマリーを表示"""
    st.markdown("#### 📊 データ収集状況")

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
        today_count = cursor.fetchone()[0]
        st.metric("本日のレース", today_count)

    with col3:
        cursor.execute("SELECT COUNT(*) FROM races")
        total = cursor.fetchone()[0]
        st.metric("総レース数", f"{total:,}")

    with col4:
        cursor.execute("SELECT COUNT(*) FROM results")
        results = cursor.fetchone()[0]
        st.metric("結果データ", f"{results:,}")

    conn.close()


def _start_basic_data_collection(collection_type: str, start_date=None, end_date=None):
    """
    基本データ収集をバックグラウンドで開始

    Args:
        collection_type: 'today', 'week', 'period'
        start_date: 期間指定の開始日
        end_date: 期間指定の終了日
    """
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'background_data_collection.py')

    args = ['--type', collection_type]

    if collection_type == 'period' and start_date and end_date:
        args.extend(['--start-date', str(start_date), '--end-date', str(end_date)])

    result = start_job(
        JOB_DATA_COLLECTION,
        script_path,
        args=args
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("📋 基本データ収集を開始しました。タブを移動しても処理は継続します。")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def _start_complement_data_collection(collection_type: str, start_date=None, end_date=None):
    """
    補完データ収集をバックグラウンドで開始

    Args:
        collection_type: 'today', 'week', 'period'
        start_date: 期間指定の開始日
        end_date: 期間指定の終了日
    """
    from datetime import timedelta

    # 日付範囲を計算
    if collection_type == 'today':
        today = datetime.now().date()
        start_date = today
        end_date = today
    elif collection_type == 'week':
        today = datetime.now().date()
        start_date = today - timedelta(days=7)
        end_date = today
    # period の場合は引数の start_date, end_date をそのまま使用

    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_missing_data_fetch.py')

    args = [
        '--start-date', str(start_date),
        '--end-date', str(end_date)
    ]

    result = start_job(
        JOB_MISSING_DATA,
        script_path,
        args=args
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("🔧 補完データ収集を開始しました。タブを移動しても処理は継続します。")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def _render_missing_data_detector():
    """不足データ検出・取得タブ"""
    st.subheader("🔍 不足データの検出と取得")

    # ジョブ実行中チェック
    if is_job_running(JOB_MISSING_DATA):
        progress = get_job_progress(JOB_MISSING_DATA)
        st.warning("🔄 不足データ取得がバックグラウンドで実行中です")

        if progress:
            st.progress(progress.get('progress', 0) / 100)

            col1, col2 = st.columns([3, 1])
            with col1:
                st.text(progress.get('message', '処理中...'))
            with col2:
                phase = progress.get('phase', 0)
                total_steps = progress.get('total_steps', 2)
                st.caption(f"フェーズ {phase}/{total_steps}")

            # 詳細情報の表示
            with st.expander("📊 詳細情報", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("処理済み", progress.get('processed', 0))
                with col2:
                    st.metric("総数", progress.get('total', 0))
                with col3:
                    st.metric("エラー", progress.get('errors', 0))

                started_at = progress.get('started_at', '')
                if started_at:
                    try:
                        start_time = datetime.fromisoformat(started_at)
                        elapsed = datetime.now() - start_time
                        st.caption(f"経過時間: {int(elapsed.total_seconds()//60)}分{int(elapsed.total_seconds()%60)}秒")
                    except:
                        pass

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 状況を更新", key="refresh_missing"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_missing"):
                    cancel_job(JOB_MISSING_DATA)
                    st.rerun()
        return

    st.markdown("**期間指定で不足データを検出・取得**")

    # 期間選択
    col1, col2 = st.columns(2)

    with col1:
        default_start = datetime.now().date() - timedelta(days=30)
        start_date = st.date_input(
            "開始日",
            value=default_start,
            key="missing_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            value=datetime.now().date(),
            key="missing_end_date"
        )

    # DataCoverageCheckerを使用して全カテゴリを取得
    try:
        checker = DataCoverageChecker(DATABASE_PATH)
        report = checker.get_coverage_report()
        all_categories = list(report["categories"].keys())
    except Exception:
        all_categories = ["レース基本情報", "選手データ", "モーター・ボート", "天候・気象", "水面・潮汐", "レース展開", "オッズ・人気", "結果データ", "直前情報", "払戻データ"]

    # 検出タイプ（デフォルトで全カテゴリを選択）
    check_types = st.multiselect(
        "検出対象（カテゴリ）",
        all_categories,
        default=all_categories  # 全カテゴリをデフォルト選択
    )

    if st.button("🔍 不足データを検出", type="primary"):
        with st.spinner("不足データを検出中..."):
            missing_dates = _detect_missing_data(start_date, end_date, check_types)
            st.session_state['missing_dates'] = missing_dates
            st.session_state['missing_check_types'] = check_types

    # 検出結果の表示
    if 'missing_dates' in st.session_state and st.session_state['missing_dates']:
        missing_dates = st.session_state['missing_dates']

        st.markdown("---")
        st.warning(f"⚠️ {len(missing_dates)}件の不足データが見つかりました")

        with st.expander("不足データ詳細", expanded=True):
            import pandas as pd
            df = pd.DataFrame(missing_dates)
            st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("📥 不足データを取得", type="primary", use_container_width=True):
            _start_missing_data_job(
                missing_dates,
                st.session_state.get('missing_check_types', [])
            )

    elif 'missing_dates' in st.session_state:
        st.success("✅ 不足データはありません！")


def _detect_missing_data(start_date, end_date, check_types: List[str]) -> List[Dict]:
    """
    DataCoverageCheckerを使用して不足データを検出

    Args:
        start_date: 開始日
        end_date: 終了日
        check_types: チェック対象カテゴリのリスト

    Returns:
        不足データのリスト
    """
    try:
        checker = DataCoverageChecker(DATABASE_PATH)
        report = checker.get_coverage_report()
    except Exception as e:
        st.error(f"データチェッカーの初期化エラー: {e}")
        return []

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    missing = []
    current_date = start_date

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')

        # 日付のレース数を確認
        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (date_str,))
        race_count = cursor.fetchone()[0]

        issues = []
        issue_details = []

        # 各カテゴリの不足をチェック
        for category_name in check_types:
            if category_name not in report["categories"]:
                continue

            category_data = report["categories"][category_name]

            for item in category_data["items"]:
                # 各項目の充足率をチェック（90%未満を不足とする）
                if item["coverage"] < 0.9:
                    # 日付単位でのチェック（必要に応じて）
                    if race_count > 0:
                        item_name = item["name"]
                        coverage_pct = item["coverage"] * 100

                        # カテゴリごとに不足を記録
                        if category_name not in [issue["category"] for issue in issue_details]:
                            issue_details.append({
                                "category": category_name,
                                "items": [f"{item_name}({coverage_pct:.0f}%)"]
                            })
                        else:
                            # 既存カテゴリに項目を追加
                            for detail in issue_details:
                                if detail["category"] == category_name:
                                    detail["items"].append(f"{item_name}({coverage_pct:.0f}%)")
                                    break

        # レース情報がない日付もチェック
        if race_count == 0 and "レース基本情報" in check_types:
            issues.append("レース情報なし")

        # 不足項目を文字列化
        if issue_details:
            for detail in issue_details:
                category = detail["category"]
                items = detail["items"][:3]  # 最大3項目表示
                if len(detail["items"]) > 3:
                    items.append(f"他{len(detail['items'])-3}項目")
                issues.append(f"{category}: " + ", ".join(items))

        if issues or race_count == 0:
            missing.append({
                '日付': date_str,
                '曜日': ['月', '火', '水', '木', '金', '土', '日'][current_date.weekday()],
                'レース': race_count,
                '結果': 0,  # 後で計算
                '詳細': 0,  # 後で計算
                '展示': 0,  # 後で計算
                'ステータス': '🔴 未取得' if race_count == 0 else '🟡 結果不足' if issues else '🟢 完了'
            })

        current_date += timedelta(days=1)

    conn.close()
    return missing


def _start_missing_data_job(missing_dates: List[Dict], check_types: List[str]):
    """不足データ取得をバックグラウンドで開始"""
    jobs_dir = os.path.join(PROJECT_ROOT, 'temp', 'jobs')
    os.makedirs(jobs_dir, exist_ok=True)

    # UIカテゴリをワークフロー用のcheck_typesに変換
    # ワークフローは "直前情報取得" と "当日確定情報" の2種類のみ認識
    workflow_check_types = []

    # 直前情報取得が必要なカテゴリ
    beforeinfo_categories = {"直前情報", "レース展開", "オッズ・人気", "天候・気象", "水面・潮汐"}
    # 当日確定情報が必要なカテゴリ（レース詳細を追加）
    confirmed_categories = {"レース基本情報", "選手データ", "モーター・ボート", "結果データ", "払戻データ", "レース詳細"}

    if any(cat in check_types for cat in beforeinfo_categories):
        workflow_check_types.append("直前情報取得")
    if any(cat in check_types for cat in confirmed_categories):
        workflow_check_types.append("当日確定情報")

    # デフォルトで両方を含める（全データ取得のため）
    if not workflow_check_types:
        workflow_check_types = ["直前情報取得", "当日確定情報"]

    config_path = os.path.join(jobs_dir, f'{JOB_MISSING_DATA}_config.json')
    config = {
        'missing_dates': missing_dates,
        'check_types': workflow_check_types
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    worker_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_missing_data.py')

    result = start_job(
        JOB_MISSING_DATA,
        worker_path,
        args=['--config', config_path]
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("タブを移動しても処理は継続します。「状況を更新」ボタンで進捗を確認できます。")

        if 'missing_dates' in st.session_state:
            del st.session_state['missing_dates']

        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def _render_original_tenji():
    """オリジナル展示データ収集タブ"""
    st.subheader("🎯 オリジナル展示データ収集")

    if is_job_running(JOB_TENJI):
        progress = get_job_progress(JOB_TENJI)
        st.warning("🔄 オリジナル展示収集がバックグラウンドで実行中です")

        if progress:
            st.progress(progress.get('progress', 0) / 100)
            st.text(progress.get('message', '処理中...'))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 状況を更新", key="refresh_tenji"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_tenji"):
                    cancel_job(JOB_TENJI)
                    st.rerun()
        return

    st.markdown("""
    **毎日実行が必要なデータ:**
    - 直線タイム（chikusen_time）
    - 1周タイム（isshu_time）
    - 回り足タイム（mawariashi_time）

    ⚠️ **注意**: オリジナル展示データは限られた期間のみ公開されます。過去データは取得できません。
    """)

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📅 今日", key="tenji_today", type="primary", use_container_width=True):
            _start_tenji_job(0)

    with col2:
        if st.button("📅 昨日", key="tenji_yesterday", use_container_width=True):
            _start_tenji_job(-1)

    st.caption("※ オリジナル展示データは今日と昨日のみ取得可能です")

    st.markdown("---")
    st.subheader("収集状況")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    today = datetime.now().date()
    tenji_status = []

    for i in range(7):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%Y-%m-%d')

        count = 0
        try:
            # オリジナル展示データはrace_detailsテーブルのchikusen_time等に保存される
            cursor.execute("""
                SELECT COUNT(*) FROM race_details rd
                JOIN races ra ON rd.race_id = ra.id
                WHERE ra.race_date = ? AND rd.chikusen_time IS NOT NULL
            """, (date_str,))
            count = cursor.fetchone()[0]
        except Exception:
            pass

        status = "🟢 収集済" if count > 0 else "🔴 未収集"
        tenji_status.append({
            '日付': date_str,
            '曜日': ['月', '火', '水', '木', '金', '土', '日'][target_date.weekday()],
            '件数': count,
            'ステータス': status
        })

    conn.close()

    import pandas as pd
    df = pd.DataFrame(tenji_status)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _start_tenji_job(days_offset: int):
    """オリジナル展示収集をバックグラウンドで開始"""
    worker_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_tenji_collection.py')

    result = start_job(
        JOB_TENJI,
        worker_path,
        args=[str(days_offset)]
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("タブを移動しても処理は継続します。「状況を更新」ボタンで進捗を確認できます。")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


