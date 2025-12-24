"""
データ収集UI（統合・簡素化版）

データ取得作業を一元管理:
- 新規データ収集: 指定期間の全データを収集
- データ補完: 既存データの不足分を自動検出して補完
- 不足データ検出: 詳細な不足データ分析と取得
- オリジナル展示収集: 直線タイム等の限定データ

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
    """データ収集UIのメインレンダリング（統合版）"""
    st.header("📥 データ収集")

    # 実行中ジョブの状況表示
    _render_job_status_bar()

    st.markdown("データ取得作業を一元管理します。")

    # 全機能を1ページに統合
    _render_unified_collection()


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


def _render_unified_collection():
    """統合データ収集UI（全機能を1ページに）"""

    # 収集状況サマリー
    _render_collection_summary()

    st.markdown("---")

    # データカバレッジ可視化
    _render_data_coverage()

    st.markdown("---")

    # ========== セクション1: 新規データ収集 ==========
    _render_new_data_collection()

    st.markdown("---")

    # ========== セクション2: データ補完（不足データ検出付き） ==========
    _render_data_complement()

    st.markdown("---")

    # ========== セクション3: オリジナル展示収集 ==========
    _render_original_tenji_inline()


def _render_new_data_collection():
    """新規データ収集セクション"""
    st.subheader("📥 新規データ収集")
    st.caption("指定期間の全データ（基本情報・結果・払戻金・決まり手・レース詳細・直前情報等）を収集します。")

    # 実行中ジョブの状態確認
    if is_job_running(JOB_MISSING_DATA):
        progress = get_job_progress(JOB_MISSING_DATA)
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
                if st.button("🔄 状況を更新", key="refresh_new_collection"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_new_collection"):
                    cancel_job(JOB_MISSING_DATA)
                    st.rerun()
        return

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("📅 今日", key="new_today", use_container_width=True):
            _start_complete_data_collection('today')

    with col2:
        if st.button("📅 今週", key="new_week", use_container_width=True, type="primary"):
            _start_complete_data_collection('week')

    with col3:
        if st.button("📅 期間指定...", key="new_period", use_container_width=True):
            st.session_state['show_new_period_selector'] = True

    # 新規データ期間指定モーダル
    if st.session_state.get('show_new_period_selector'):
        with st.expander("📅 新規データ収集 - 期間指定", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("開始日", key="new_start_date")
            with col2:
                end_date = st.date_input("終了日", key="new_end_date")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 実行", key="new_period_exec"):
                    _start_complete_data_collection('period', start_date, end_date)
                    st.session_state['show_new_period_selector'] = False
                    st.rerun()
            with col2:
                if st.button("❌ キャンセル", key="new_period_cancel"):
                    st.session_state['show_new_period_selector'] = False
                    st.rerun()


def _render_data_complement():
    """データ補完セクション（不足データ検出機能統合）"""
    st.subheader("🔧 データ補完")
    st.caption("既存データから不足している項目を自動検出して補完します。")

    # 実行中ジョブの状態確認
    if is_job_running(JOB_MISSING_DATA):
        progress = get_job_progress(JOB_MISSING_DATA)
        st.warning("🔄 データ補完がバックグラウンドで実行中です")

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
                if st.button("🔄 状況を更新", key="refresh_complement"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_complement"):
                    cancel_job(JOB_MISSING_DATA)
                    st.rerun()
        return

    # クイック補完ボタン
    st.markdown("**クイック補完:**")
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔧 今日", key="complement_today", use_container_width=True):
            _start_complement_data_collection('today')

    with col2:
        if st.button("🔧 今週", key="complement_week", use_container_width=True):
            _start_complement_data_collection('week')

    with col3:
        if st.button("🔧 期間指定...", key="complement_period_btn", use_container_width=True):
            st.session_state['show_complement_period'] = True

    # 期間指定モーダル
    if st.session_state.get('show_complement_period'):
        with st.expander("🔧 期間指定補完", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("開始日", key="comp_start")
            with col2:
                end_date = st.date_input("終了日", key="comp_end")

            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ 実行", key="comp_exec"):
                    _start_complement_data_collection('period', start_date, end_date)
                    st.session_state['show_complement_period'] = False
                    st.rerun()
            with col2:
                if st.button("❌ キャンセル", key="comp_cancel"):
                    st.session_state['show_complement_period'] = False
                    st.rerun()

    st.markdown("---")

    # 詳細検出セクション
    st.markdown("**詳細な不足データ検出:**")
    st.caption("⚠️ 未来の日付は除外されます（開催予定のレースは結果がまだありません）")

    col1, col2 = st.columns(2)
    with col1:
        default_start = datetime.now().date() - timedelta(days=60)
        detect_start = st.date_input("検出開始日", value=default_start, key="detect_start")
    with col2:
        # 検出終了日は昨日まで（今日以降は開催前の可能性があるため）
        default_end = datetime.now().date() - timedelta(days=1)
        detect_end = st.date_input("検出終了日", value=default_end, key="detect_end")

    # カテゴリ選択
    try:
        checker = DataCoverageChecker(DATABASE_PATH)
        report = checker.get_coverage_report()
        all_categories = list(report["categories"].keys())
    except Exception:
        all_categories = ["レース基本情報", "選手データ", "モーター・ボート", "天候・気象", "水面・潮汐", "レース展開", "オッズ・人気", "結果データ", "直前情報", "払戻データ"]

    check_types = st.multiselect(
        "検出対象カテゴリ",
        all_categories,
        default=all_categories,
        key="detect_categories"
    )

    if st.button("🔍 不足データを検出", type="primary", key="detect_btn"):
        with st.spinner("不足データを検出中..."):
            missing_dates = _detect_missing_data(detect_start, detect_end, check_types)
            st.session_state['missing_dates'] = missing_dates
            st.session_state['missing_check_types'] = check_types

    # 検出結果の表示
    if 'missing_dates' in st.session_state and st.session_state['missing_dates']:
        missing_dates = st.session_state['missing_dates']
        st.warning(f"⚠️ {len(missing_dates)}件の不足データが見つかりました")

        with st.expander("不足データ詳細", expanded=True):
            import pandas as pd
            df = pd.DataFrame(missing_dates)
            st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("📥 検出された不足データを取得", type="primary", use_container_width=True, key="fetch_detected"):
            _start_missing_data_job(missing_dates, st.session_state.get('missing_check_types', []))

    elif 'missing_dates' in st.session_state:
        st.success("✅ 不足データはありません！")


def _render_original_tenji_inline():
    """オリジナル展示収集セクション（インライン版）"""
    st.subheader("🎯 オリジナル展示収集")
    st.caption("直線タイム・1周タイム・回り足タイム等の限定データを収集します。")

    if is_job_running(JOB_TENJI):
        progress = get_job_progress(JOB_TENJI)
        st.warning("🔄 オリジナル展示収集がバックグラウンドで実行中です")

        if progress:
            st.progress(progress.get('progress', 0) / 100)
            st.text(progress.get('message', '処理中...'))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 状況を更新", key="refresh_tenji_inline"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_tenji_inline"):
                    cancel_job(JOB_TENJI)
                    st.rerun()
        return

    st.warning("⚠️ オリジナル展示データは限られた期間のみ公開されます。過去データは取得できません。")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📅 今日", key="tenji_today_inline", type="primary", use_container_width=True):
            _start_tenji_job(0)
    with col2:
        if st.button("📅 昨日", key="tenji_yesterday_inline", use_container_width=True):
            _start_tenji_job(-1)

    # 収集状況（過去7日間）
    with st.expander("📊 収集状況（過去7日間）", expanded=False):
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        today = datetime.now().date()
        tenji_status = []

        for i in range(7):
            target_date = today - timedelta(days=i)
            date_str = target_date.strftime('%Y-%m-%d')

            count = 0
            try:
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


def _start_complete_data_collection(collection_type: str, start_date=None, end_date=None):
    """
    新規データ収集（全データ種）をバックグラウンドで開始

    指定期間の全データを収集します:
    - レース基本情報
    - 結果データ
    - 払戻金
    - 決まり手
    - レース詳細（ST time、actual_course等）
    - 直前情報（展示タイム、チルト角等）

    Args:
        collection_type: 'today', 'week', 'period'
        start_date: 期間指定の開始日
        end_date: 期間指定の終了日
    """
    # 日付範囲を計算（未来のレースを除外するため昨日まで）
    if collection_type == 'today':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday
    elif collection_type == 'week':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday - timedelta(days=6)  # 昨日から遡って7日間
        end_date = yesterday
    # period の場合は引数の start_date, end_date をそのまま使用

    # bulk_missing_data_fetch_parallel.pyを使用（並列化版で高速）
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'data_collection', 'bulk_missing_data_fetch_parallel.py')

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
        st.info("📥 新規データ収集を開始しました（並列化版で高速処理）。タブを移動しても処理は継続します。")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def _start_complement_data_collection(collection_type: str, start_date=None, end_date=None):
    """
    データ補完をバックグラウンドで開始

    指定期間で不足しているデータのみを補完します:
    - 決まり手（欠損レース）
    - 払戻金（欠損レース）
    - レース詳細（ST time、actual_course等の欠損）
    - 直前情報（未収集レース）

    内部的には新規データ収集と同じワークフローを使用しますが、
    既にデータが存在するレースはスキップされます。

    Args:
        collection_type: 'today', 'week', 'period'
        start_date: 期間指定の開始日
        end_date: 期間指定の終了日
    """
    # 日付範囲を計算（未来のレースを除外するため昨日まで）
    if collection_type == 'today':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday
        end_date = yesterday
    elif collection_type == 'week':
        yesterday = datetime.now().date() - timedelta(days=1)
        start_date = yesterday - timedelta(days=6)  # 昨日から遡って7日間
        end_date = yesterday
    # period の場合は引数の start_date, end_date をそのまま使用

    # 並列化版スクリプトを使用（自動的に不足データのみ取得）
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'data_collection', 'bulk_missing_data_fetch_parallel.py')

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
        st.info("🔧 データ補完を開始しました（並列化版で高速処理）。タブを移動しても処理は継続します。")
        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


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
    """不足データ取得をバックグラウンドで開始（最適化版スクリプトを使用）"""
    if not missing_dates:
        st.warning("取得対象のデータがありません")
        return

    # 日付範囲を取得
    dates = [d['日付'] for d in missing_dates]
    start_date = min(dates)
    end_date = max(dates)

    # 並列化版スクリプトを使用
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'data_collection', 'bulk_missing_data_fetch_parallel.py')

    args = [
        '--start-date', start_date,
        '--end-date', end_date
    ]

    result = start_job(
        JOB_MISSING_DATA,
        script_path,
        args=args
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


def _render_data_coverage():
    """データカバレッジの可視化"""
    with st.expander("📊 データ充足率の詳細を表示", expanded=False):
        st.markdown("### データカバレッジ分析")
        st.caption("各カテゴリのデータ取得状況を確認できます")

        try:
            checker = DataCoverageChecker(DATABASE_PATH)
            report = checker.get_coverage_report()

            # 全体スコア
            overall = report.get('overall_score', 0)
            col1, col2 = st.columns([1, 3])
            with col1:
                st.metric("全体充足率", f"{overall:.1f}%")
            with col2:
                st.progress(overall / 100)

            st.markdown("---")

            # カテゴリ別表示
            categories = report.get('categories', {})

            for category_name, category_data in categories.items():
                with st.container():
                    st.markdown(f"#### {category_name}")

                    items = category_data.get('items', [])
                    if not items:
                        st.info("データ項目なし")
                        continue

                    # カテゴリの平均充足率
                    avg_coverage = sum(item.get('coverage', 0) for item in items) / len(items) if items else 0
                    st.progress(avg_coverage, text=f"平均充足率: {avg_coverage*100:.1f}%")

                    # 項目ごとの詳細
                    for item in items:
                        name = item.get('name', '不明')
                        coverage = item.get('coverage', 0)
                        count = item.get('count', 0)
                        total = item.get('total', 0)
                        status = item.get('status', '不明')
                        importance = item.get('importance', 1)

                        # 重要度に応じて色分け
                        if importance == 3:
                            importance_badge = "🔴 必須"
                        elif importance == 2:
                            importance_badge = "🟡 推奨"
                        else:
                            importance_badge = "🟢 任意"

                        # ステータスに応じた表示
                        if coverage >= 0.95:
                            status_emoji = "✅"
                        elif coverage >= 0.5:
                            status_emoji = "⚠️"
                        else:
                            status_emoji = "❌"

                        col1, col2, col3, col4 = st.columns([3, 1, 1, 2])
                        with col1:
                            st.text(f"{status_emoji} {name}")
                        with col2:
                            st.text(importance_badge)
                        with col3:
                            st.text(f"{coverage*100:.1f}%")
                        with col4:
                            st.text(f"{count:,} / {total:,}")

                    st.markdown("")

        except Exception as e:
            st.error(f"データカバレッジの取得に失敗しました: {str(e)}")


