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
    status_text.text("Step 1/5: 本日のデータを取得中...")
    progress_bar.progress(0.1)

    today_schedule = fetch_today_data()
    if not today_schedule:
        st.error("データ取得に失敗しました")
        progress_bar.empty()
        status_text.empty()
        return

    progress_bar.progress(0.2)

    # Step 2: オッズ取得
    status_text.text("Step 2/5: 本日のオッズを取得中...")
    progress_bar.progress(0.25)
    fetch_today_odds(today_schedule)
    progress_bar.progress(0.4)

    # Step 3: 法則再解析
    status_text.text("Step 3/5: 法則を再解析中...")
    reanalyze_rules()
    progress_bar.progress(0.5)

    # Step 4: 予測生成
    status_text.text("Step 4/5: 予測を生成中...")
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
            from config.settings import DATABASE_PATH
            data_manager = DataManager(DATABASE_PATH)

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


def fetch_today_odds(today_schedule):
    """
    本日の全レースのオッズを取得

    Args:
        today_schedule: {venue_code: race_date} の辞書
    """
    try:
        from src.scraper.auto_odds_fetcher import AutoOddsFetcher

        with st.spinner("オッズを取得中..."):
            fetcher = AutoOddsFetcher(delay=1.0)
            result = fetcher.fetch_odds_for_today(today_schedule)
            fetcher.close()

            if result['success_count'] > 0:
                st.success(f"✅ オッズ取得: {result['success_count']}/{result['total_races']} レース")
            else:
                st.warning("⚠️ オッズ取得に失敗しました（レース開始前の可能性があります）")

    except Exception as e:
        st.warning(f"⚠️ オッズ取得エラー: {e}")
        st.info("オッズは後から「オッズ自動取得」で取得できます")


def generate_and_save_predictions(today_schedule):
    """
    本日の全レースの予想を生成してデータベースに保存（高速版）

    Args:
        today_schedule: {venue_code: race_date} の辞書
    """
    import os
    import sys
    from src.utils.date_utils import to_iso_format

    # 対象日を取得（最初の会場の日付を使用）
    if not today_schedule:
        st.warning("予想対象のレースが見つかりませんでした")
        return

    target_date = to_iso_format(list(today_schedule.values())[0])

    # プロジェクトルート
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))

    # 高速予想生成スクリプトのパス
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'fast_prediction_generator.py')

    if not os.path.exists(script_path):
        st.error("高速予想生成スクリプトが見つかりません")
        return

    with st.spinner(f"予想を高速生成中... ({target_date})"):
        try:
            result = subprocess.run(
                [sys.executable, script_path, '--date', target_date],
                capture_output=True,
                text=True,
                timeout=600,  # 10分タイムアウト
                cwd=PROJECT_ROOT,
                encoding='cp932',  # Windowsコンソール出力用
                errors='replace'  # デコードエラーを無視
            )

            if result.returncode == 0:
                # 成功メッセージを抽出
                output_lines = result.stdout.split('\n') if result.stdout else []
                success_info = []
                for line in output_lines:
                    if '生成成功:' in line or '総処理時間:' in line or '平均処理時間:' in line:
                        success_info.append(line.strip())

                st.success("予想生成が完了しました！")
                if success_info:
                    st.info('\n'.join(success_info))

                # 出力の最後の部分を表示
                with st.expander("詳細ログを表示"):
                    st.code(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
            else:
                st.error("予想生成中にエラーが発生しました")
                with st.expander("エラー詳細"):
                    st.code(result.stderr if result.stderr else result.stdout)

        except subprocess.TimeoutExpired:
            st.error("予想生成がタイムアウトしました（10分経過）")
        except Exception as e:
            st.error(f"予想生成エラー: {e}")
