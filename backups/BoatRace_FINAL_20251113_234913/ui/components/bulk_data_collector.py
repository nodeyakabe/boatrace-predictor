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
    st.markdown("選択した日付・会場のレースデータを確実に取得します")

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
        """)

    # 対象日付と会場の表示
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"📅 対象日: {target_date.strftime('%Y-%m-%d')}")
    with col2:
        st.info(f"🏟️ 対象会場: {len(selected_venues)}会場")

    if len(selected_venues) == 0:
        st.warning("会場を選択してください（サイドバー）")
        return

    # 既存データ確認
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM races
        WHERE race_date = ?
    """, (target_date.strftime('%Y-%m-%d'),))
    existing_count = cursor.fetchone()[0]

    if existing_count > 0:
        st.warning(f"⚠️ {existing_count}件のレースデータが既に存在します（上書きされます）")

    conn.close()

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
            "script": "補完_決まり手データ_改善版.py"
        },
        "3. レース詳細データv4": {
            "description": "展示タイム、モーター・ボート情報等",
            "default": True,
            "script": "補完_レース詳細データ_改善版v4.py"
        },
        "4. 天候データ": {
            "description": "気温・水温・波高",
            "default": True,
            "script": "補完_天候データ_改善版.py"
        },
        "5. 風向データ": {
            "description": "風速・風向",
            "default": True,
            "script": "補完_風向データ_改善版.py"
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

                try:
                    from src.scraper.bulk_scraper import BulkScraper
                    scraper = BulkScraper()

                    result = scraper.fetch_date_range(
                        target_date.strftime("%Y-%m-%d"),
                        target_date.strftime("%Y-%m-%d")
                    )

                    add_log(f"✅ レース基本情報・結果: 取得完了")
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
                    python_exe = os.path.join(PROJECT_ROOT, 'venv', 'Scripts', 'python.exe')
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

            date_str = target_date.strftime('%Y-%m-%d')

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                cursor.execute("""
                    SELECT COUNT(*) FROM races WHERE race_date = ?
                """, (date_str,))
                race_count = cursor.fetchone()[0]
                st.metric("レース数", f"{race_count:,}")

            with col2:
                cursor.execute("""
                    SELECT COUNT(*) FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    WHERE ra.race_date = ?
                """, (date_str,))
                result_count = cursor.fetchone()[0]
                st.metric("結果データ", f"{result_count:,}")

            with col3:
                cursor.execute("""
                    SELECT COUNT(*) FROM race_details rd
                    JOIN races ra ON rd.race_id = ra.id
                    WHERE ra.race_date = ?
                """, (date_str,))
                detail_count = cursor.fetchone()[0]
                st.metric("レース詳細", f"{detail_count:,}")

            with col4:
                cursor.execute("""
                    SELECT COUNT(*) FROM results r
                    JOIN races ra ON r.race_id = ra.id
                    WHERE ra.race_date = ? AND r.kimarite IS NOT NULL
                """, (date_str,))
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
