"""
ワークフロー管理コンポーネント
データ準備の自動化とワンクリック実行
"""
import streamlit as st
import subprocess
from datetime import datetime
from src.scraper.bulk_scraper import BulkScraper
# 並列処理版（高速化）
try:
    from src.scraper.bulk_scraper_parallel import BulkScraperParallel
    HAS_PARALLEL_SCRAPER = True
except ImportError:
    HAS_PARALLEL_SCRAPER = False


def render_workflow_manager():
    """データ準備ワークフローマネージャー"""
    st.header("🔧 データ準備ワークフロー")
    st.markdown("データ収集から学習までを自動化")

    # ワンクリック実行ボタン
    st.markdown("### 🚀 クイックスタート")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("🎯 今日の予測を生成", type="primary", use_container_width=True):
            run_today_preparation_workflow()

    with col2:
        if st.button("📚 過去データ学習", use_container_width=True):
            run_training_workflow()

    st.markdown("---")

    # 個別ステップ実行
    st.markdown("### 📋 個別ステップ実行")

    with st.expander("Step 1: 本日データ取得"):
        if st.button("▶️ 実行", key="step1"):
            fetch_today_data()

    with st.expander("Step 2: データ品質チェック"):
        if st.button("▶️ 実行", key="step2"):
            check_data_quality()

    with st.expander("Step 3: 特徴量計算"):
        if st.button("▶️ 実行", key="step3"):
            calculate_features()

    with st.expander("Step 4: 法則再解析"):
        if st.button("▶️ 実行", key="step4"):
            reanalyze_rules()


def run_today_preparation_workflow():
    """今日の予測生成ワークフロー"""
    st.info("🚀 今日の予測を生成します...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1: データ取得
    status_text.text("Step 1/4: 本日のデータを取得中...")
    progress_bar.progress(0.1)

    today_schedule = fetch_today_data()
    if not today_schedule:
        st.error("データ取得に失敗しました")
        progress_bar.empty()
        status_text.empty()
        return

    progress_bar.progress(0.3)

    # Step 2: 法則再解析
    status_text.text("Step 2/4: 法則を再解析中...")
    reanalyze_rules()
    progress_bar.progress(0.5)

    # Step 3: 予測生成
    status_text.text("Step 3/4: 予測を生成中...")
    progress_bar.progress(0.6)

    # 進捗バーとステータステキストを削除して、generate_and_save_predictions内で新しいものを使用
    progress_bar.empty()
    status_text.empty()

    generate_and_save_predictions(today_schedule)

    # generate_and_save_predictions内で完了メッセージが表示されるため、ここでは何もしない


def run_training_workflow():
    """学習ワークフロー"""
    st.info("📚 過去データ学習を開始します...")

    progress_bar = st.progress(0)
    status_text = st.empty()

    # Step 1: データ品質チェック
    status_text.text("Step 1/4: データ品質をチェック中...")
    progress_bar.progress(0.2)
    check_data_quality()

    # Step 2: 特徴量計算
    status_text.text("Step 2/4: 特徴量を計算中...")
    progress_bar.progress(0.4)
    calculate_features()

    # Step 3: 法則解析
    status_text.text("Step 3/4: 法則を解析中...")
    progress_bar.progress(0.6)
    reanalyze_rules()

    # Step 4: モデル学習
    status_text.text("Step 4/4: モデルを学習中...")
    progress_bar.progress(0.8)
    # モデル学習は別途実行
    st.info("モデル学習は「モデル学習」セクションで実行してください")

    progress_bar.progress(1.0)
    st.success("✅ データ準備が完了しました！")


def fetch_today_data():
    """本日のデータを取得"""
    from src.database.data_manager import DataManager
    from datetime import datetime
    import sqlite3
    from config.settings import DATABASE_PATH

    # 進捗表示用のコンテナ
    status_container = st.container()

    with status_container:
        # まず今日のスケジュールを取得
        from src.scraper.schedule_scraper import ScheduleScraper
        schedule_scraper = ScheduleScraper()
        today_schedule = schedule_scraper.get_today_schedule()
        schedule_scraper.close()

        if not today_schedule:
            st.warning("本日開催のレースが見つかりませんでした")
            return False

        # 予定レース数を計算（会場数 × 12レース）
        expected_races = len(today_schedule) * 12

        # 既存データを確認
        today_str = datetime.now().strftime('%Y-%m-%d')

        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM races WHERE race_date = ?", (today_str,))
        existing_count = cursor.fetchone()[0]
        conn.close()

        # 100%取得済みか確認
        completion_rate = existing_count / expected_races if expected_races > 0 else 0

        if existing_count >= expected_races:
            # データ取得スキップ - スケジュールを返す
            return today_schedule

        # データ取得が必要な場合
        progress_placeholder = st.empty()

        if existing_count > 0:
            progress_placeholder.warning(f"⚠️ データが不完全です: {existing_count}/{expected_races} 件（{completion_rate*100:.0f}%）- 不足データを取得中...")

    # データがない場合のみ取得
    try:
        with st.spinner("本日のレースデータを取得中..."):
            data_manager = DataManager()

            # 並列処理版を使用（高速化）
            if HAS_PARALLEL_SCRAPER:
                scraper = BulkScraperParallel(max_workers=3)
            else:
                scraper = BulkScraper()

            schedule_scraper = scraper.schedule_scraper
            today_schedule = schedule_scraper.get_today_schedule()

            if today_schedule:
                total_races = 0
                saved_races = 0

                fetch_progress = st.empty()

                if HAS_PARALLEL_SCRAPER:
                    # 並列処理版
                    def progress_callback(completed, total, venue_code, status):
                        fetch_progress.text(f"会場 {completed}/{total}: {venue_code} - {status}")

                    # 全会場を並列取得
                    venue_codes = list(today_schedule.keys())
                    race_dates = list(today_schedule.values())
                    race_date = race_dates[0] if race_dates else None

                    if race_date:
                        results = scraper.fetch_multiple_venues_parallel(
                            venue_codes=venue_codes,
                            race_date=race_date,
                            race_count=12,
                            progress_callback=progress_callback
                        )

                        # 結果を保存
                        for venue_code, races in results.items():
                            for race_data in races:
                                try:
                                    if not race_data or not isinstance(race_data, dict):
                                        continue
                                    if 'venue_code' not in race_data or 'race_date' not in race_data or 'race_number' not in race_data:
                                        continue

                                    total_races += 1
                                    if data_manager.save_race_data(race_data):
                                        saved_races += 1
                                except Exception as save_error:
                                    continue
                else:
                    # 従来の直列処理
                    for idx, (venue_code, race_date) in enumerate(today_schedule.items(), 1):
                        fetch_progress.text(f"会場 {idx}/{len(today_schedule)}: {venue_code} を取得中...")

                        result = scraper.fetch_multiple_venues(
                            venue_codes=[venue_code],
                            race_date=race_date,
                            race_count=12
                        )
                        if venue_code in result:
                            for race_data in result[venue_code]:
                                try:
                                    if not race_data or not isinstance(race_data, dict):
                                        continue
                                    if 'venue_code' not in race_data or 'race_date' not in race_data or 'race_number' not in race_data:
                                        continue

                                    total_races += 1
                                    if data_manager.save_race_data(race_data):
                                        saved_races += 1
                                except Exception as save_error:
                                    continue

                scraper.close()
                fetch_progress.empty()

                # スケジュールを返す（予測生成は呼び出し元で行う）
                return today_schedule
            else:
                scraper.close()
                st.warning("本日開催のレースが見つかりませんでした")
                return None

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        st.error(f"❌ データ取得エラー: {e}")
        st.code(error_detail)
        return None


def check_data_quality():
    """データ品質チェック"""
    try:
        from src.analysis.data_coverage_checker import DataCoverageChecker
        from config.settings import DATABASE_PATH

        with st.spinner("データ品質をチェック中..."):
            checker = DataCoverageChecker(DATABASE_PATH)
            report = checker.get_coverage_report()

            overall_score = report["overall_score"]
            st.metric("データ充足率", f"{overall_score*100:.1f}%")

            if overall_score >= 0.8:
                st.success("✅ データは充実しています")
            elif overall_score >= 0.5:
                st.warning("⚠️ 一部データが不足しています")
            else:
                st.error("❌ データが大幅に不足しています")
    except Exception as e:
        st.error(f"チェックエラー: {e}")


def calculate_features():
    """特徴量を計算"""
    st.info("特徴量計算は自動的に実行されます")


def reanalyze_rules():
    """法則を再解析"""
    try:
        with st.spinner("法則を再解析中..."):
            import sys
            import os

            # Pythonインタープリターのパスを取得
            python_exe = sys.executable

            # スクリプトのパスを取得
            script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            script_path = os.path.join(script_dir, 'reanalyze_all.py')

            result = subprocess.run(
                [python_exe, script_path],
                capture_output=True,
                text=True,
                timeout=900
            )

            if result.returncode == 0:
                st.success("✅ 法則の再解析が完了しました")
            else:
                st.warning("⚠️ 一部の法則解析に失敗しました")
    except Exception as e:
        st.error(f"再解析エラー: {e}")


def generate_and_save_predictions(today_schedule):
    """
    本日の全レースの予想を生成してデータベースに保存

    Args:
        today_schedule: {venue_code: race_date} の辞書
    """
    from src.analysis.race_predictor import RacePredictor
    from src.database.data_manager import DataManager
    from src.utils.date_utils import to_iso_format
    import sqlite3
    from config.settings import DATABASE_PATH

    # 進捗表示用のプレースホルダー
    progress_bar = st.progress(0)
    status_text = st.empty()

    data_manager = DataManager()
    race_predictor = RacePredictor()

    # 全レースリストを取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 会場名を取得するためのマッピング
    from config.settings import VENUES
    venue_name_map = {}
    for venue_id, venue_info in VENUES.items():
        venue_name_map[venue_info['code']] = venue_info['name']

    all_races = []
    for venue_code, race_date in today_schedule.items():
        race_date_formatted = to_iso_format(race_date)

        cursor.execute("""
            SELECT id, venue_code, race_number
            FROM races
            WHERE venue_code = ? AND race_date = ?
            ORDER BY race_number
        """, (venue_code, race_date_formatted))

        for row in cursor.fetchall():
            all_races.append({
                'race_id': row[0],
                'venue_code': row[1],
                'venue_name': venue_name_map.get(row[1], f"会場{row[1]}"),
                'race_number': row[2],
                'race_date': race_date_formatted
            })

    conn.close()

    if not all_races:
        progress_bar.empty()
        status_text.empty()
        st.warning("予想対象のレースが見つかりませんでした")
        return

    # 既に予想が存在するレースをチェック
    races_to_predict = []
    skipped_count = 0

    for race in all_races:
        existing_predictions = data_manager.get_race_predictions(race['race_id'])
        if existing_predictions:
            skipped_count += 1
        else:
            races_to_predict.append(race)

    if not races_to_predict:
        progress_bar.empty()
        status_text.empty()
        st.success(f"✅ 今日の予測が完了しました！「レース予想」タブで確認できます（{skipped_count}レース）")
        return

    success_count = 0
    error_count = 0

    for idx, race in enumerate(races_to_predict):
        try:
            # 進捗表示を更新
            progress_percentage = (idx + 1) / len(races_to_predict)
            progress_bar.progress(progress_percentage)
            status_text.text(f"予想生成中: {race['venue_name']} {race['race_number']}R ({idx + 1}/{len(races_to_predict)})")

            # 予想生成
            predictions = race_predictor.predict_race(race['race_id'])

            if predictions and len(predictions) > 0:
                # データベースに保存
                if data_manager.save_race_predictions(race['race_id'], predictions):
                    success_count += 1
                else:
                    error_count += 1
            else:
                error_count += 1

        except Exception as e:
            import logging
            logging.warning(f"予想生成エラー (race_id={race['race_id']}): {e}")
            error_count += 1
            continue

    progress_bar.empty()
    status_text.empty()

    # 最終結果のみ表示
    total_races = success_count + error_count + skipped_count
    if error_count > 0:
        st.success(f"✅ 今日の予測が完了しました！「レース予想」タブで確認できます")
        st.caption(f"📊 {total_races}レース（成功: {success_count}, スキップ: {skipped_count}, エラー: {error_count}）")
    else:
        st.success(f"✅ 今日の予測が完了しました！「レース予想」タブで確認できます（{total_races}レース）")
