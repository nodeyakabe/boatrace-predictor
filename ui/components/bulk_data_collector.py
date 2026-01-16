"""
過去データ一括取得UI - 改善版

これまでのトライ&エラーで得た知見を反映
"""
import streamlit as st
import subprocess
import os
import sys
from datetime import datetime, timedelta
import sqlite3


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def render_bulk_data_collector(target_date, selected_venues):
    """過去データ一括取得UIのレンダリング"""
    st.header("📥 過去データ一括取得")
    st.markdown("最終保存日から実行日までの全レースデータを自動取得します")

    # 知見の表示
    with st.expander("💡 これまでの知見", expanded=False):
        st.markdown("""
        **取得可能なデータ:**
        - ✅ レース基本情報（公式サイト）
        - ✅ 結果データ（公式サイト）
        - ✅ 決まり手データ（改善版スクレイピング）
        - ✅ レース詳細データv4（展示タイム、モーター・ボート情報）
        - ✅ 天候データ（気温・水温・波高）
        - ✅ 風向データ（風速・風向）

        **別途取得が必要:**
        - 🌊 潮位データ（RDMDB収集スクリプト）
        - 🎯 オリジナル展示データ（毎日手動実行）

        **改善ポイント:**
        - エラーハンドリング強化
        - リトライロジック実装
        - 進捗表示の改善
        - 最終保存日から自動取得
        - 全会場を常に対象
        """)

    # 最終保存日を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT MAX(race_date) FROM races
    """)
    result = cursor.fetchone()

    if result and result[0]:
        last_saved_date = datetime.strptime(result[0], '%Y-%m-%d')
        start_date = last_saved_date + timedelta(days=1)
    else:
        start_date = datetime(2016, 1, 1)
        last_saved_date = None

    end_date = datetime.now()

    conn.close()

    # 対象期間の表示
    st.info("🔍 取得対象期間（自動設定）")

    col1, col2, col3 = st.columns(3)
    with col1:
        if last_saved_date:
            st.metric("最終保存日", last_saved_date.strftime('%Y-%m-%d'))
        else:
            st.metric("最終保存日", "データなし")
    with col2:
        st.metric("開始日", start_date.strftime('%Y-%m-%d'))
    with col3:
        st.metric("終了日（今日）", end_date.strftime('%Y-%m-%d'))

    # 対象日数を計算
    target_days = (end_date - start_date).days + 1

    if target_days <= 0:
        st.success("✅ データは最新です！取得する必要はありません。")
        return

    st.warning(f"📊 取得対象: **{target_days}日分** × **全24会場** のレースデータ")

    # 既存データ確認は不要（常に最新日から取得するため）

    # 取得手順の選択
    st.subheader("🔧 取得手順")

    tasks = {
        "1. レース基本情報・結果": {
            "description": "公式サイトからレース基本情報と結果を取得",
            "default": True,
            "script": None,  # BulkScraperを使用
        },
        "2. 決まり手データ": {
            "description": "決まり手情報を補完（改善版）",
            "default": True,
            "script": "scripts/data_collection/補完_決まり手データ_改善版.py"
        },
        "3. レース詳細データv4": {
            "description": "展示タイム、モーター・ボート情報等",
            "default": True,
            "script": "scripts/data_collection/補完_レース詳細データ_改善版v4.py"
        },
        "4. 気象データ": {
            "description": "気温・水温・波高・風速・風向",
            "default": True,
            "script": "scripts/data_collection/fill_missing_weather_data.py"
        },
    }

    selected_tasks = []
    for task_name, task_info in tasks.items():
        if st.checkbox(task_name, value=task_info["default"], help=task_info["description"]):
            selected_tasks.append((task_name, task_info))

    # 実行ボタン
    st.markdown("---")

    if st.button("🚀 データ取得開始", type="primary", use_container_width=True):
        if len(selected_tasks) == 0:
            st.error("取得するデータを選択してください")
            return

        # プログレスバー
        progress_bar = st.progress(0)
        status_text = st.empty()

        total_tasks = len(selected_tasks)
        completed = 0

        # 実行ログ
        log_placeholder = st.empty()
        logs = []

        def add_log(message):
            logs.append(f"{datetime.now().strftime('%H:%M:%S')} - {message}")
            log_placeholder.text_area("実行ログ", "\n".join(logs[-20:]), height=300)

        try:
            # タスク1: レース基本情報・結果（BulkScraperを使用）
            if any(name == "1. レース基本情報・結果" for name, _ in selected_tasks):
                status_text.text("レース基本情報・結果を取得中...")
                add_log("レース基本情報・結果の取得を開始")
                add_log(f"期間: {start_date.strftime('%Y-%m-%d')} ～ {end_date.strftime('%Y-%m-%d')}")
                add_log("対象: 全24会場")

                try:
                    from src.scraper.bulk_scraper import BulkScraper
                    scraper = BulkScraper()

                    # 日付範囲をループ
                    current_date = start_date
                    total_races = 0
                    while current_date <= end_date:
                        date_str = current_date.strftime("%Y%m%d")
                        add_log(f"  {current_date.strftime('%Y-%m-%d')} のデータを取得中...")

                        # 全24会場を試行
                        venue_codes = [f"{i:02d}" for i in range(1, 25)]
                        result = scraper.fetch_multiple_venues(
                            venue_codes=venue_codes,
                            race_date=date_str,
                            race_count=12
                        )

                        # 取得件数をカウント
                        for venue_code, races in result.items():
                            total_races += len(races)

                        current_date += timedelta(days=1)

                    add_log(f"✅ レース基本情報・結果: 取得完了 ({total_races}レース)")
                except Exception as e:
                    add_log(f"❌ レース基本情報・結果: エラー - {str(e)[:100]}")

                completed += 1
                progress_bar.progress(completed / total_tasks)

            # タスク2以降: 補完スクリプトを実行
            for task_name, task_info in selected_tasks:
                if task_info["script"] is None:
                    continue

                status_text.text(f"{task_name}を処理中...")
                add_log(f"{task_name}の処理を開始")

                try:
                    # 現在実行中のPythonインタープリタを使用
                    python_exe = sys.executable
                    script_path = os.path.join(PROJECT_ROOT, task_info["script"])

                    result = subprocess.run(
                        [python_exe, script_path],
                        capture_output=True,
                        text=True,
                        cwd=PROJECT_ROOT,
                        timeout=600,  # 10分タイムアウト
                        encoding='utf-8'
                    )

                    if result.returncode == 0:
                        add_log(f"✅ {task_name}: 完了")
                    else:
                        add_log(f"⚠️ {task_name}: 警告あり")
                        if result.stderr:
                            add_log(f"   詳細: {result.stderr[:200]}")

                except subprocess.TimeoutExpired:
                    add_log(f"⏱️ {task_name}: タイムアウト（10分経過）")
                except Exception as e:
                    add_log(f"❌ {task_name}: エラー - {str(e)[:100]}")

                completed += 1
                progress_bar.progress(completed / total_tasks)

            # 完了
            status_text.text("✅ すべての処理が完了しました！")
            add_log("="*50)
            add_log("🎉 データ取得完了！")

            # 取得データの確認
            st.subheader("📊 取得データ確認")

            conn = sqlite3.connect(DATABASE_PATH)
            cursor = conn.cursor()

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                cursor.execute("""
                    SELECT COUNT(*) FROM races
                    WHERE race_date BETWEEN ? AND ?
                """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                race_count = cursor.fetchone()[0]
                st.metric("レース数", f"{race_count:,}")

            with col2:
                cursor.execute("""
                    SELECT COUNT(*) FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    WHERE ra.race_date BETWEEN ? AND ?
                """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                result_count = cursor.fetchone()[0]
                st.metric("結果データ", f"{result_count:,}")

            with col3:
                cursor.execute("""
                    SELECT COUNT(*) FROM race_details rd
                    JOIN races ra ON rd.race_id = ra.id
                    WHERE ra.race_date BETWEEN ? AND ?
                """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                detail_count = cursor.fetchone()[0]
                st.metric("レース詳細", f"{detail_count:,}")

            with col4:
                cursor.execute("""
                    SELECT COUNT(*) FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    WHERE ra.race_date BETWEEN ? AND ? AND r.kimarite IS NOT NULL
                """, (start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
                kimarite_count = cursor.fetchone()[0]
                if result_count > 0:
                    ratio = kimarite_count / result_count * 100
                    st.metric("決まり手", f"{ratio:.1f}%")
                else:
                    st.metric("決まり手", "0%")

            conn.close()

            st.success("✅ データ取得が完了しました！")

        except Exception as e:
            st.error(f"❌ エラーが発生しました: {e}")
            add_log(f"❌ 致命的エラー: {str(e)}")
