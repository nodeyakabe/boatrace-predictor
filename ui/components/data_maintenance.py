"""
データメンテナンスUI

データ取得作業を一元化して分かりやすくする
- 不足データの検出
- 過去データの再取得
- オリジナル展示の定期収集

バックグラウンドジョブ対応版:
- タブ移動しても処理継続
- 重複実行防止
- 進捗ポーリング
"""
import streamlit as st
import subprocess
import os
import sys
import json
from datetime import datetime, timedelta
import sqlite3
from typing import List, Dict, Tuple
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH
from src.utils.job_manager import (
    is_job_running, start_job, get_job_progress,
    cancel_job, get_all_jobs
)

# ジョブ名定数
JOB_TENJI = 'tenji_collection'
JOB_MISSING_DATA = 'missing_data_fetch'


def render_data_maintenance():
    """データメンテナンスUIのメインレンダリング"""
    st.header("🔧 データメンテナンス")

    # 実行中ジョブの状況表示
    _render_job_status_bar()

    st.markdown("""
    データ取得作業を一元管理します。タブで作業を選択してください。
    """)

    tab1, tab2, tab3 = st.tabs([
        "🔍 不足データ検出・取得",
        "🎯 オリジナル展示",
        "📥 一括取得"
    ])

    with tab1:
        _render_missing_data_detector()

    with tab2:
        _render_original_tenji()

    with tab3:
        _render_bulk_collector()


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
                if st.button("キャンセル", key=f"cancel_{job_name}"):
                    cancel_job(job_name)
                    st.rerun()

        # 自動更新ボタン
        if st.button("🔄 状況を更新", key="refresh_jobs"):
            st.rerun()

        st.markdown("---")

    # 完了したジョブの通知
    recent_completed = {k: v for k, v in jobs.items()
                        if v.get('status') in ['completed', 'failed', 'cancelled']
                        and not v.get('is_running')}

    for job_name, progress in recent_completed.items():
        status = progress.get('status')
        message = progress.get('message', '')
        completed_at = progress.get('completed_at', '')

        # 5分以内に完了したジョブのみ表示
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


def _render_recent_data_status():
    """直近7日間のデータ状況を表示"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    today = datetime.now().date()
    data_status = []

    for i in range(7):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%Y-%m-%d')

        # レース数
        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (date_str,))
        race_count = cursor.fetchone()[0]

        # 結果データ数
        cursor.execute("""
            SELECT COUNT(*) FROM results r
            JOIN races ra ON r.race_id = ra.id
            WHERE ra.race_date = ?
        """, (date_str,))
        result_count = cursor.fetchone()[0]

        # レース詳細数
        cursor.execute("""
            SELECT COUNT(*) FROM race_details rd
            JOIN races ra ON rd.race_id = ra.id
            WHERE ra.race_date = ?
        """, (date_str,))
        detail_count = cursor.fetchone()[0]

        # オリジナル展示数
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

        # ステータス判定
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


def _render_missing_data_detector():
    """不足データ検出・取得"""
    st.subheader("不足データの検出と取得")

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

    # データ状況サマリー
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        cursor.execute("SELECT MIN(race_date), MAX(race_date) FROM races")
        result = cursor.fetchone()
        if result[0]:
            st.metric("データ期間", f"{result[0][:10]}")
            st.caption(f"～ {result[1][:10]}")
        else:
            st.metric("データ期間", "なし")

    with col2:
        cursor.execute("SELECT COUNT(*) FROM races")
        total_races = cursor.fetchone()[0]
        st.metric("総レース数", f"{total_races:,}")

    with col3:
        cursor.execute("SELECT COUNT(DISTINCT race_date) FROM races")
        total_days = cursor.fetchone()[0]
        st.metric("データ日数", f"{total_days:,}日")

    with col4:
        try:
            cursor.execute("SELECT COUNT(*) FROM original_exhibition")
            tenji_count = cursor.fetchone()[0]
        except:
            tenji_count = 0
        st.metric("オリジナル展示", f"{tenji_count:,}")

    conn.close()

    st.markdown("---")

    # 直近7日間の状況
    st.markdown("**直近7日間のデータ状況**")
    _render_recent_data_status()

    st.markdown("---")
    st.markdown("**期間指定で不足データを検出・取得**")

    # 期間選択
    col1, col2 = st.columns(2)

    with col1:
        # デフォルトは30日前から
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

    # 検出タイプ（2カテゴリ設計）
    st.markdown("""
    **取得対象を選択:**

    📋 **直前情報取得** - レース前に取得可能なデータ
    - 展示タイム・チルト・部品交換
    - 天候・風向・潮位
    - オッズ（当日レースのみ）

    ✅ **当日確定情報** - レース後に確定するデータ
    - レース基本情報・結果・ST・進入コース
    - 決まり手・払戻金
    """)

    check_types = st.multiselect(
        "取得対象",
        ["直前情報取得", "当日確定情報"],
        default=["当日確定情報"]
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

        # 詳細表示
        with st.expander("不足データ詳細", expanded=True):
            import pandas as pd
            df = pd.DataFrame(missing_dates)
            st.dataframe(df, use_container_width=True, hide_index=True)

        # 取得ボタン（バックグラウンド実行のみ）
        if st.button("📥 不足データを取得", type="primary", use_container_width=True):
            _start_missing_data_job(
                missing_dates,
                st.session_state.get('missing_check_types', [])
            )

    elif 'missing_dates' in st.session_state:
        st.success("✅ 不足データはありません！")


def _detect_missing_data(start_date, end_date, check_types: List[str]) -> List[Dict]:
    """不足データを検出（2カテゴリ設計）"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    missing = []
    current_date = start_date

    is_beforeinfo_mode = "直前情報取得" in check_types
    is_confirmed_mode = "当日確定情報" in check_types

    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')

        # レース数を取得
        cursor.execute("""
            SELECT COUNT(*) FROM races WHERE race_date = ?
        """, (date_str,))
        race_count = cursor.fetchone()[0]

        issues = []

        # ========================================
        # 【当日確定情報】モードのチェック
        # ========================================
        if is_confirmed_mode:
            # レース基本情報（常にチェック）
            if race_count == 0:
                issues.append("レース情報なし")

            # 結果データ
            if race_count > 0:
                cursor.execute("""
                    SELECT COUNT(*) FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    WHERE ra.race_date = ?
                """, (date_str,))
                result_count = cursor.fetchone()[0]
                expected = race_count * 6
                if result_count < expected * 0.8:
                    issues.append(f"結果不足({result_count}/{expected})")

            # 払戻データ
            if race_count > 0:
                cursor.execute("""
                    SELECT COUNT(DISTINCT p.race_id) FROM payouts p
                    JOIN races ra ON p.race_id = ra.id
                    WHERE ra.race_date = ?
                """, (date_str,))
                payout_count = cursor.fetchone()[0]
                if payout_count < race_count * 0.8:
                    issues.append(f"払戻不足({payout_count}/{race_count})")

        # ========================================
        # 【直前情報取得】モードのチェック
        # ========================================
        if is_beforeinfo_mode and race_count > 0:
            # 直前情報（展示タイム）
            cursor.execute("""
                SELECT COUNT(*) FROM race_details rd
                JOIN races ra ON rd.race_id = ra.id
                WHERE ra.race_date = ? AND rd.exhibition_time IS NOT NULL
            """, (date_str,))
            exhibition_count = cursor.fetchone()[0]
            expected = race_count * 6
            if exhibition_count < expected * 0.5:
                issues.append(f"直前情報不足({exhibition_count}/{expected})")

            # 天候・風向
            cursor.execute("""
                SELECT COUNT(*) FROM race_conditions rc
                JOIN races ra ON rc.race_id = ra.id
                WHERE ra.race_date = ? AND rc.wind_speed IS NOT NULL
            """, (date_str,))
            weather_count = cursor.fetchone()[0]
            if weather_count < race_count * 0.5:
                issues.append(f"天候不足({weather_count}/{race_count})")

            # 潮位（海水場のみ）
            SEAWATER_VENUES = ['15', '16', '17', '18', '20', '22', '24']
            cursor.execute("""
                SELECT COUNT(DISTINCT r.venue_code) FROM races r
                WHERE r.race_date = ? AND r.venue_code IN ({})
            """.format(','.join(['?']*len(SEAWATER_VENUES))),
            (date_str,) + tuple(SEAWATER_VENUES))
            seawater_venue_count = cursor.fetchone()[0]

            if seawater_venue_count > 0:
                # tideテーブルが存在するかチェック
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='tide'
                """)
                if cursor.fetchone():
                    cursor.execute("""
                        SELECT COUNT(DISTINCT t.venue_code) FROM tide t
                        WHERE t.tide_date = ? AND t.venue_code IN ({})
                    """.format(','.join(['?']*len(SEAWATER_VENUES))),
                    (date_str,) + tuple(SEAWATER_VENUES))
                    tide_count = cursor.fetchone()[0]
                    if tide_count < seawater_venue_count * 0.5:
                        issues.append(f"潮位不足({tide_count}/{seawater_venue_count}海水場)")

            # オッズ（当日レースのみ）
            today = datetime.now().strftime('%Y-%m-%d')
            if date_str == today:
                # oddsテーブルが存在するかチェック
                cursor.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name='odds'
                """)
                if cursor.fetchone():
                    cursor.execute("""
                        SELECT COUNT(DISTINCT o.race_id) FROM odds o
                        JOIN races ra ON o.race_id = ra.id
                        WHERE ra.race_date = ?
                    """, (date_str,))
                    odds_count = cursor.fetchone()[0]
                    if odds_count < race_count * 0.5:
                        issues.append(f"オッズ不足({odds_count}/{race_count})")

        if issues:
            missing.append({
                '日付': date_str,
                'レース': race_count,
                '問題': ', '.join(issues)
            })

        current_date += timedelta(days=1)

    conn.close()
    return missing


def _start_missing_data_job(missing_dates: List[Dict], check_types: List[str]):
    """不足データ取得をバックグラウンドで開始"""
    # 設定ファイルを作成
    jobs_dir = os.path.join(PROJECT_ROOT, 'temp', 'jobs')
    os.makedirs(jobs_dir, exist_ok=True)

    config_path = os.path.join(jobs_dir, f'{JOB_MISSING_DATA}_config.json')
    config = {
        'missing_dates': missing_dates,
        'check_types': check_types
    }

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # ワーカースクリプトを起動
    worker_path = os.path.join(PROJECT_ROOT, 'scripts', 'worker_missing_data.py')

    result = start_job(
        JOB_MISSING_DATA,
        worker_path,
        args=['--config', config_path]
    )

    if result['success']:
        st.success(f"✅ {result['message']}")
        st.info("タブを移動しても処理は継続します。「状況を更新」ボタンで進捗を確認できます。")

        # セッションステートをクリア
        if 'missing_dates' in st.session_state:
            del st.session_state['missing_dates']

        time.sleep(1)
        st.rerun()
    else:
        st.error(f"❌ {result['message']}")


def _render_original_tenji():
    """オリジナル展示データ収集"""
    st.subheader("オリジナル展示データ収集")

    # ジョブ実行中チェック
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

    # クイックボタン
    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📅 今日", key="tenji_today", type="primary", use_container_width=True):
            _start_tenji_job(0)

    with col2:
        if st.button("📅 昨日", key="tenji_yesterday", use_container_width=True):
            _start_tenji_job(-1)

    st.caption("※ オリジナル展示データは今日と昨日のみ取得可能です")

    # 収集状況
    st.markdown("---")
    st.subheader("収集状況")

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 直近7日間の展示データ数
    today = datetime.now().date()
    tenji_status = []

    for i in range(7):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime('%Y-%m-%d')

        count = 0
        try:
            cursor.execute("""
                SELECT COUNT(*) FROM original_exhibition oe
                JOIN races ra ON oe.race_id = ra.id
                WHERE ra.race_date = ?
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


def _render_bulk_collector():
    """一括取得（従来機能）"""
    st.subheader("過去データ一括取得")

    st.markdown("""
    最終保存日から今日までの全レースデータを一括取得します。

    **取得されるデータ:**
    - レース基本情報・結果
    - 決まり手データ
    - レース詳細データ（展示タイム、モーター・ボート）
    - 天候データ
    - 風向データ
    """)

    # 最終保存日を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT MAX(race_date) FROM races")
    result = cursor.fetchone()

    if result and result[0]:
        last_saved_date = datetime.strptime(result[0], '%Y-%m-%d')
        start_date = last_saved_date + timedelta(days=1)
    else:
        start_date = datetime(2024, 1, 1)
        last_saved_date = None

    end_date = datetime.now()
    conn.close()

    # 対象期間表示
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("最終保存日", last_saved_date.strftime('%Y-%m-%d') if last_saved_date else "なし")
    with col2:
        st.metric("取得開始日", start_date.strftime('%Y-%m-%d'))
    with col3:
        target_days = (end_date - start_date).days + 1
        st.metric("対象日数", f"{target_days}日" if target_days > 0 else "0日")

    if target_days <= 0:
        st.success("✅ データは最新です！")
        return

    st.warning(f"📊 {target_days}日分 × 全24会場のデータを取得します")

    # 取得オプション
    st.markdown("---")

    tasks = {
        "レース基本情報・結果": True,
        "決まり手データ": True,
        "レース詳細データ": True,
        "天候データ": True,
        "風向データ": True,
    }

    selected_tasks = []
    for task_name, default in tasks.items():
        if st.checkbox(task_name, value=default, key=f"bulk_{task_name}"):
            selected_tasks.append(task_name)

    if st.button("🚀 一括取得開始", type="primary", use_container_width=True):
        if not selected_tasks:
            st.error("取得するデータを選択してください")
            return

        # 従来のbulk_data_collectorの処理を呼び出し
        from ui.components.bulk_data_collector import render_bulk_data_collector
        render_bulk_data_collector(None, None)
