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
    """クイック収集タブ"""
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
    st.markdown("#### 過去データ収集")

    if st.button("📅 今週のデータ（バックグラウンド）", use_container_width=True, type="primary"):
        _start_week_data_collection_background()

    st.caption("※ 過去1週間分のレースデータをバックグラウンドで収集します")

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


def _collect_today_data():
    """今日のデータを収集"""
    st.info("📥 今日のデータを収集中...")

    try:
        from src.scraper.bulk_scraper import BulkScraper

        scraper = BulkScraper()
        schedule_scraper = scraper.schedule_scraper
        today_schedule = schedule_scraper.get_today_schedule()

        if not today_schedule:
            st.warning("本日開催のレースが見つかりませんでした")
            return

        progress_bar = st.progress(0)
        status_text = st.empty()

        total_venues = len(today_schedule)
        total_races = 0

        for i, (venue_code, race_date) in enumerate(today_schedule.items(), 1):
            status_text.text(f"会場 {venue_code} を収集中... ({i}/{total_venues})")

            result = scraper.fetch_multiple_venues(
                venue_codes=[venue_code],
                race_date=race_date,
                race_count=12
            )

            if venue_code in result:
                total_races += len(result[venue_code])

            progress_bar.progress(i / total_venues)

        st.success(f"✅ 完了！ {total_venues}会場 {total_races}レース取得しました")

        # 補完データも取得
        if st.session_state.get('quick_include_supplements', False):
            _run_all_supplement_scripts()

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def _collect_tomorrow_data():
    """明日のデータを収集"""
    st.info("📥 明日のデータを収集中...")

    try:
        from src.scraper.bulk_scraper import BulkScraper

        tomorrow = datetime.now() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        scraper = BulkScraper()

        total_races = 0
        successful_venues = []

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i in range(1, 25):
            venue_code = f"{i:02d}"
            status_text.text(f"会場 {venue_code} を確認中... ({i}/24)")

            try:
                result = scraper.fetch_multiple_venues(
                    venue_codes=[venue_code],
                    race_date=tomorrow_str,
                    race_count=12
                )

                if venue_code in result and result[venue_code]:
                    total_races += len(result[venue_code])
                    successful_venues.append(venue_code)

            except Exception:
                pass

            progress_bar.progress(i / 24)

        if successful_venues:
            st.success(f"✅ 完了！ {len(successful_venues)}会場 {total_races}レース取得しました")
        else:
            st.warning("明日開催のレースが見つかりませんでした")

    except Exception as e:
        st.error(f"❌ エラー: {e}")


def _start_week_data_collection_background():
    """今週のデータ収集をバックグラウンドで開始"""
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'background_data_collection.py')

    result = start_job(
        JOB_DATA_COLLECTION,
        script_path,
        args=['--type', 'week']
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("タブを移動しても処理は継続します。ヘッダーの進捗バーで状況を確認できます。")
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
            st.text(progress.get('message', '処理中...'))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 状況を更新", key="refresh_missing"):
                    st.rerun()
            with col2:
                if st.button("⏹️ キャンセル", key="cancel_missing"):
                    cancel_job(JOB_MISSING_DATA)
                    st.rerun()
        return

    # 直近7日間の状況
    st.markdown("**直近7日間のデータ状況**")
    _render_recent_data_status()

    st.markdown("---")
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

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📥 バックグラウンドで取得", type="primary"):
                _start_missing_data_job(
                    missing_dates,
                    st.session_state.get('missing_check_types', [])
                )

        with col2:
            if st.button("📥 フォアグラウンドで取得"):
                _fetch_missing_data_foreground(
                    missing_dates,
                    st.session_state.get('missing_check_types', [])
                )

    elif 'missing_dates' in st.session_state:
        st.success("✅ 不足データはありません！")


def _render_recent_data_status():
    """直近7日間のデータ状況を表示（DataCoverageChecker統合版）"""
    try:
        checker = DataCoverageChecker(DATABASE_PATH)
        report = checker.get_coverage_report()
        missing_items = checker.get_missing_items()
    except Exception as e:
        st.warning(f"データチェッカーのエラー: {e}")
        missing_items = []

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    today = datetime.now().date()
    data_status = []

    for i in range(7):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%Y-%m-%d')

        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (date_str,))
        race_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.race_date = ?
        """, (date_str,))
        result_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            WHERE ra.race_date = ?
        """, (date_str,))
        detail_count = cursor.fetchone()[0]

        tenji_count = 0
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM original_exhibition oe
                JOIN races ra ON oe.race_id = ra.id
                WHERE ra.race_date = ?
            """, (date_str,))
            tenji_count = cursor.fetchone()[0]
        except Exception:
            pass

        if race_count == 0:
            status = "⚪ 未取得"
        elif result_count < race_count * 5:
            status = "🟡 結果不足"
        elif detail_count < race_count * 5:
            status = "🟡 詳細不足"
        elif tenji_count == 0:
            status = "🟠 展示なし"
        else:
            status = "🟢 完了"

        data_status.append({
            '日付': date_str,
            '曜日': ['月', '火', '水', '木', '金', '土', '日'][target_date.weekday()],
            'レース': race_count,
            '結果': result_count,
            '詳細': detail_count,
            '展示': tenji_count,
            'ステータス': status
        })

    conn.close()

    import pandas as pd
    df = pd.DataFrame(data_status)
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 全体の不足データサマリーを表示
    if missing_items:
        st.markdown("---")
        st.markdown("**⚠️ 全体で不足しているデータ（重要度順）**")
        top_missing = missing_items[:10]
        for item in top_missing:
            importance_stars = "★" * item["importance"]
            st.text(f"{importance_stars} [{item['category']}] {item['name']} - {item['coverage']*100:.1f}% ({item['status']})")
    else:
        st.success("✅ 全てのデータ項目が充足しています！")


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
    # 当日確定情報が必要なカテゴリ
    confirmed_categories = {"レース基本情報", "選手データ", "モーター・ボート", "結果データ", "払戻データ"}

    if any(cat in check_types for cat in beforeinfo_categories):
        workflow_check_types.append("直前情報取得")
    if any(cat in check_types for cat in confirmed_categories):
        workflow_check_types.append("当日確定情報")

    # デフォルトで当日確定情報を含める（結果データ取得のため）
    if not workflow_check_types:
        workflow_check_types = ["当日確定情報"]

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


def _fetch_missing_data_foreground(missing_dates: List[Dict], check_types: List[str]):
    """
    不足データを取得（フォアグラウンド）
    全カテゴリ対応版 - 改善版

    補完スクリプトは全期間のデータを一括処理するため、
    期間全体で1回だけ実行すれば良い。
    """
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_placeholder = st.empty()
    logs = []

    def add_log(msg):
        logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {msg}")
        log_placeholder.text_area("実行ログ", "\n".join(logs[-20:]), height=300)

    # カテゴリ別の補完スクリプトマッピング
    CATEGORY_SCRIPTS = {
        "レース基本情報": [],  # 基本情報は直接スクレイピング
        "選手データ": [],  # 基本情報取得時に一緒に取得される
        "モーター・ボート": [],  # 基本情報取得時に一緒に取得される
        "天候・気象": [("補完_天候データ_改善版.py", "天候データ"), ("補完_風向データ_改善版.py", "風向データ")],
        "水面・潮汐": [],  # 潮汐APIが未実装
        "レース展開": [("補完_展示タイム_全件_高速化.py", "展示タイム")],
        "オッズ・人気": [],  # オッズ取得は別途実装が必要
        "結果データ": [("補完_レース詳細データ_改善版v4.py", "レース詳細"), ("補完_決まり手データ_改善版.py", "決まり手")],
        "直前情報": [("補完_展示タイム_全件_高速化.py", "直前情報")],
        "払戻データ": [("補完_払戻金データ.py", "払戻金")]
    }

    add_log(f"=== 不足データ取得開始 ===")
    add_log(f"対象カテゴリ: {', '.join(check_types)}")
    add_log(f"対象期間: {len(missing_dates)}日分")
    add_log("")

    # フェーズ1: レース基本情報の取得
    status_text.text("フェーズ 1/2: レース基本情報の取得")
    progress_bar.progress(0.1)

    if "レース基本情報" in check_types:
        add_log("【フェーズ1】 レース基本情報の取得")
        missing_race_dates = [item for item in missing_dates if item.get('レース', 0) == 0]

        if missing_race_dates:
            add_log(f"  {len(missing_race_dates)}日分のレース情報が不足")
            from src.scraper.bulk_scraper import BulkScraper
            scraper = BulkScraper()

            for idx, item in enumerate(missing_race_dates):
                date_str = item['日付']
                add_log(f"  {date_str} のレース情報を取得中...")

                try:
                    venue_codes = [f"{i:02d}" for i in range(1, 25)]
                    result = scraper.fetch_multiple_venues(
                        venue_codes=venue_codes,
                        race_date=date_str,
                        race_count=12
                    )
                    total_races = sum(len(races) for races in result.values())
                    if total_races > 0:
                        add_log(f"  ✅ {total_races}レース取得")
                    else:
                        add_log(f"  ⚠️ レースなし（休催日）")
                except Exception as e:
                    add_log(f"  ❌ エラー: {str(e)[:60]}")

                progress = 0.1 + (0.4 * (idx + 1) / len(missing_race_dates))
                progress_bar.progress(progress)
        else:
            add_log("  スキップ: レース基本情報は充足")
    else:
        add_log("【フェーズ1】 スキップ（対象外）")

    # フェーズ2: 補完スクリプトの実行
    status_text.text("フェーズ 2/2: 詳細データの補完")
    progress_bar.progress(0.5)
    add_log("")
    add_log("【フェーズ2】 詳細データの補完")

    # 実行する補完スクリプトを収集（重複排除）
    scripts_to_run = []
    for category in check_types:
        if category in CATEGORY_SCRIPTS:
            for script_name, label in CATEGORY_SCRIPTS[category]:
                if script_name and (script_name, label, category) not in [(s[0], s[1], s[2]) for s in scripts_to_run]:
                    scripts_to_run.append((script_name, label, category))

    if scripts_to_run:
        add_log(f"  実行する補完スクリプト: {len(scripts_to_run)}個")
        add_log("")

        for idx, (script_name, label, category) in enumerate(scripts_to_run):
            script_path = os.path.join(PROJECT_ROOT, script_name)

            if os.path.exists(script_path):
                add_log(f"  [{category}] {label} 補完中...")
                status_text.text(f"フェーズ 2/2: {label} 補完中 ({idx+1}/{len(scripts_to_run)})")

                try:
                    result = subprocess.run(
                        [sys.executable, script_path],
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=600,
                        encoding='utf-8',
                        errors='ignore'
                    )
                    if result.returncode == 0:
                        add_log(f"  ✅ {label} 完了")
                    else:
                        add_log(f"  ⚠️ {label} 終了（警告あり）")
                        if result.stderr:
                            error_lines = result.stderr.strip().split('\n')[-3:]
                            for line in error_lines:
                                add_log(f"     {line[:70]}")
                except subprocess.TimeoutExpired:
                    add_log(f"  ⏱️ {label} タイムアウト（10分超過）")
                except Exception as e:
                    add_log(f"  ❌ {label} エラー: {str(e)[:60]}")
            else:
                add_log(f"  ⚠️ [{category}] {label} スクリプト未実装 ({script_name})")

            progress = 0.5 + (0.5 * (idx + 1) / len(scripts_to_run))
            progress_bar.progress(progress)
    else:
        add_log("  実行する補完スクリプトなし")
        progress_bar.progress(1.0)

    status_text.text("✅ 処理完了！")
    progress_bar.progress(1.0)
    add_log("")
    add_log("="*50)
    add_log(f"全ての処理が完了しました")

    if 'missing_dates' in st.session_state:
        del st.session_state['missing_dates']

    st.success("✅ 不足データの取得が完了しました！")


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
    run_mode = st.radio(
        "実行モード",
        ["バックグラウンド（推奨）", "フォアグラウンド"],
        horizontal=True,
        help="バックグラウンド: タブ移動しても継続 / フォアグラウンド: 完了まで待機"
    )

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📅 今日", key="tenji_today", type="primary", use_container_width=True):
            if "バックグラウンド" in run_mode:
                _start_tenji_job(0)
            else:
                _run_tenji_collection_foreground(0)

    with col2:
        if st.button("📅 昨日", key="tenji_yesterday", use_container_width=True):
            if "バックグラウンド" in run_mode:
                _start_tenji_job(-1)
            else:
                _run_tenji_collection_foreground(-1)

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


def _run_tenji_collection_foreground(days_offset: int):
    """オリジナル展示収集を実行（フォアグラウンド）"""
    target_date = datetime.now().date() + timedelta(days=days_offset)

    with st.spinner(f"オリジナル展示データを収集中... ({target_date})"):
        try:
            script_path = os.path.join(PROJECT_ROOT, 'fetch_original_tenji_daily.py')

            if not os.path.exists(script_path):
                st.error(f"スクリプトが見つかりません: {script_path}")
                return

            if days_offset == 0:
                date_args = ['--today']
            else:
                target_date_str = target_date.strftime('%Y-%m-%d')
                date_args = ['--date', target_date_str]

            result = subprocess.run(
                [sys.executable, script_path] + date_args,
                capture_output=True,
                text=True,
                timeout=600,
                cwd=PROJECT_ROOT,
                encoding='utf-8'
            )

            if result.returncode == 0:
                st.success(f"✅ {target_date} のオリジナル展示データ収集完了！")
                with st.expander("詳細ログ"):
                    st.code(result.stdout)
            else:
                st.error("❌ 収集に失敗しました")
                st.code(result.stderr)

        except subprocess.TimeoutExpired:
            st.error("❌ タイムアウト（10分経過）")
        except Exception as e:
            st.error(f"❌ エラー: {e}")


# 期間指定収集機能は「不足データ検出」に統合されたため削除


def _deprecated_render_period_collection():
    """期間指定収集タブ"""
    st.subheader("📅 期間指定収集")

    # 最終保存日を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(race_date) FROM races")
    result = cursor.fetchone()
    conn.close()

    if result and result[0]:
        last_saved_date = datetime.strptime(result[0], '%Y-%m-%d')
        default_start = last_saved_date + timedelta(days=1)
    else:
        last_saved_date = None
        default_start = datetime.now() - timedelta(days=7)

    if last_saved_date:
        st.info(f"📊 最終保存日: **{last_saved_date.strftime('%Y-%m-%d')}**")
    else:
        st.warning("📊 データベースにデータがありません")

    # 期間設定
    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "開始日",
            default_start.date() if isinstance(default_start, datetime) else default_start,
            key="period_start_date"
        )

    with col2:
        end_date = st.date_input(
            "終了日",
            datetime.now().date(),
            key="period_end_date"
        )

    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    target_days = (end_date - start_date).days + 1

    if target_days <= 0:
        st.success("✅ データは最新です！取得する必要はありません。")
        return

    # 会場選択
    st.markdown("#### 対象会場")
    venue_selection = st.radio(
        "会場選択",
        ["すべての会場（24会場）", "特定の会場を選択"],
        horizontal=True,
        key="period_venue_selection",
        label_visibility="collapsed"
    )

    selected_venues = None
    if venue_selection == "特定の会場を選択":
        venue_options = {f"{info['code']} - {info['name']}": info['code']
                        for venue_id, info in VENUES.items()}
        selected_names = st.multiselect(
            "会場を選択",
            list(venue_options.keys()),
            default=[],
            key="period_venue_multiselect"
        )
        selected_venues = [venue_options[name] for name in selected_names]

    # 取得データ選択
    st.markdown("#### 取得データ")

    col1, col2 = st.columns(2)
    with col1:
        get_basic = st.checkbox("レース基本情報・結果", value=True, key="period_basic")
    with col2:
        get_supplements = st.checkbox("補完データ（決まり手、詳細、天候、風向）", value=True, key="period_supplements")

    # 確認表示
    venue_count = len(selected_venues) if selected_venues else 24
    st.warning(f"📊 取得対象: **{target_days}日分** × **{venue_count}会場**")

    # 実行ボタン
    if st.button("🚀 データ収集を開始", type="primary", use_container_width=True, key="period_start"):
        _collect_period_data(
            start_date,
            end_date,
            selected_venues,
            get_basic,
            get_supplements
        )


def _collect_period_data(start_date, end_date, venue_codes, get_basic, get_supplements):
    """期間指定でデータを収集"""
    st.info(f"📥 {start_date} から {end_date} のデータを収集中...")

    progress_bar = st.progress(0)
    status_text = st.empty()
    log_placeholder = st.empty()
    logs = []

    def add_log(message):
        logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
        log_placeholder.text_area("実行ログ", "\n".join(logs[-20:]), height=200)

    try:
        if get_basic:
            from src.scraper.bulk_scraper import BulkScraper
            scraper = BulkScraper()

            date_range = []
            current_date = start_date
            while current_date <= end_date:
                date_range.append(current_date.strftime("%Y-%m-%d"))
                current_date += timedelta(days=1)

            if not venue_codes:
                venue_codes = [f"{i:02d}" for i in range(1, 25)]

            total_tasks = len(date_range) * len(venue_codes)
            completed_tasks = 0
            total_races = 0

            add_log(f"期間: {start_date} ～ {end_date}")
            add_log(f"対象: {len(venue_codes)}会場 × {len(date_range)}日")

            for date_str in date_range:
                for venue_code in venue_codes:
                    status_text.text(
                        f"{date_str} - 会場 {venue_code} を収集中... "
                        f"({completed_tasks}/{total_tasks})"
                    )

                    try:
                        result = scraper.fetch_multiple_venues(
                            venue_codes=[venue_code],
                            race_date=date_str,
                            race_count=12
                        )

                        if venue_code in result:
                            total_races += len(result[venue_code])

                    except Exception:
                        pass

                    completed_tasks += 1
                    progress_bar.progress(completed_tasks / total_tasks)

            add_log(f"✅ レース基本情報: {total_races}レース取得完了")

        if get_supplements:
            add_log("補完データの取得を開始...")
            _run_all_supplement_scripts(add_log, status_text)

        status_text.text("✅ すべての処理が完了しました！")
        add_log("🎉 データ取得完了！")

        _show_period_data_summary(start_date, end_date)

        st.success("✅ データ取得が完了しました！")

    except Exception as e:
        st.error(f"❌ エラー: {e}")
        add_log(f"❌ 致命的エラー: {str(e)}")


def _run_all_supplement_scripts(add_log=None, status_text=None):
    """すべての補完スクリプトを実行"""
    tasks = [
        ("決まり手データ", "補完_決まり手データ_改善版.py"),
        ("レース詳細データv4", "補完_レース詳細データ_改善版v4.py"),
        ("天候データ", "補完_天候データ_改善版.py"),
        ("風向データ", "補完_風向データ_改善版.py"),
    ]

    if add_log is None:
        add_log = lambda x: None
    if status_text is None:
        status_text = st.empty()

    for task_name, script_name in tasks:
        status_text.text(f"{task_name}を処理中...")
        add_log(f"{task_name}の処理を開始")

        try:
            script_path = os.path.join(PROJECT_ROOT, script_name)

            if not os.path.exists(script_path):
                add_log(f"⚠️ {task_name}: スクリプトが見つかりません")
                continue

            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=600,
                encoding='utf-8'
            )

            if result.returncode == 0:
                add_log(f"✅ {task_name}: 完了")
            else:
                add_log(f"⚠️ {task_name}: 警告あり")

        except subprocess.TimeoutExpired:
            add_log(f"⏱️ {task_name}: タイムアウト")
        except Exception as e:
            add_log(f"❌ {task_name}: エラー - {str(e)[:100]}")


def _show_period_data_summary(start_date, end_date):
    """期間データのサマリーを表示"""
    st.subheader("📊 取得データ確認")

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        start_str = start_date.strftime('%Y-%m-%d') if hasattr(start_date, 'strftime') else str(start_date)
        end_str = end_date.strftime('%Y-%m-%d') if hasattr(end_date, 'strftime') else str(end_date)

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            cursor.execute("""
                SELECT COUNT(*) FROM races
                WHERE race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            race_count = cursor.fetchone()[0]
            st.metric("レース数", f"{race_count:,}")

        with col2:
            cursor.execute("""
                SELECT COUNT(*) FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            result_count = cursor.fetchone()[0]
            st.metric("結果データ", f"{result_count:,}")

        with col3:
            cursor.execute("""
                SELECT COUNT(*) FROM race_details rd
                JOIN races ra ON rd.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ?
            """, (start_str, end_str))
            detail_count = cursor.fetchone()[0]
            st.metric("レース詳細", f"{detail_count:,}")

        with col4:
            cursor.execute("""
                SELECT COUNT(*) FROM results r
                JOIN races ra ON r.race_id = ra.id
                WHERE ra.race_date BETWEEN ? AND ? AND r.kimarite IS NOT NULL
            """, (start_str, end_str))
            kimarite_count = cursor.fetchone()[0]
            if result_count > 0:
                ratio = kimarite_count / result_count * 100
                st.metric("決まり手", f"{ratio:.1f}%")
            else:
                st.metric("決まり手", "0%")

        conn.close()

    except Exception as e:
        st.error(f"データ確認エラー: {e}")
