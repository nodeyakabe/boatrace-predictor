"""
今日の予測生成 - バックグラウンド実行スクリプト

ワークフローの各ステップを実行し、進捗をファイルに記録
"""
import os
import sys
import sqlite3
import concurrent.futures
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

from src.utils.job_manager import update_job_progress, complete_job

JOB_NAME = 'today_prediction'


def update_progress(step: str, message: str, progress: int):
    """進捗を更新"""
    update_job_progress(JOB_NAME, {
        'status': 'running',
        'step': step,
        'message': message,
        'progress': progress
    })
    print(f"[{progress}%] {step}: {message}")


def fetch_today_data():
    """Step 1: 本日のデータを取得（既存データがあればスキップ）"""
    update_progress("Step 1/6", "本日のデータを確認中...", 5)

    today = datetime.now().strftime('%Y-%m-%d')

    # 既存データをチェック
    conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'data/boatrace.db'))
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT venue_code FROM races WHERE race_date = ?
    """, (today,))
    existing_venues = {row[0] for row in cursor.fetchall()}

    cursor.execute("""
        SELECT COUNT(*) FROM races WHERE race_date = ?
    """, (today,))
    existing_race_count = cursor.fetchone()[0]
    conn.close()

    # 既に十分なデータがあればスキップ（12レース×会場数の80%以上）
    if existing_race_count >= len(existing_venues) * 12 * 0.8 and len(existing_venues) >= 1:
        update_progress("Step 1/6", f"既存データ使用 ({len(existing_venues)}会場, {existing_race_count}レース)", 15)
        # 既存会場をスケジュールとして返す
        today_schedule = {vc: today.replace('-', '') for vc in existing_venues}
        return today_schedule

    # データが不足している場合のみスクレイピング
    from src.scraper.bulk_scraper import BulkScraper

    scraper = BulkScraper()
    today_schedule = {}

    # 今日のスケジュールを取得（schedule_scraper経由）
    schedule = scraper.schedule_scraper.get_today_schedule()

    if schedule:
        # scheduleは {venue_code: race_date} の辞書形式
        for venue_code in schedule.keys():
            today_schedule[venue_code] = today.replace('-', '')

        # 未取得の会場のみ取得
        venues_to_fetch = [vc for vc in today_schedule.keys() if vc not in existing_venues]

        if not venues_to_fetch:
            update_progress("Step 1/6", f"全会場取得済み ({len(today_schedule)}会場)", 15)
            return today_schedule

        total_venues = len(venues_to_fetch)
        for i, venue_code in enumerate(venues_to_fetch, 1):
            pct = 5 + int((i / total_venues) * 10)
            update_progress("Step 1/6", f"会場 {venue_code} を取得中... ({i}/{total_venues})", pct)

            try:
                scraper.fetch_multiple_venues(
                    venue_codes=[venue_code],
                    race_date=today,
                    race_count=12
                )
            except Exception as e:
                print(f"会場 {venue_code} 取得エラー: {e}")

    update_progress("Step 1/6", f"データ取得完了 ({len(today_schedule)}会場)", 15)
    return today_schedule


def update_db_views():
    """Step 2: DBビューを更新"""
    update_progress("Step 2/6", "DBビューを更新中...", 20)

    try:
        from src.database.views import create_all_views
        conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'data/boatrace.db'))
        create_all_views(conn)
        conn.close()
        update_progress("Step 2/6", "DBビュー更新完了", 25)
    except Exception as e:
        print(f"DBビュー更新エラー: {e}")


def fetch_odds(today_schedule):
    """Step 3: オッズを取得（並列処理）"""
    update_progress("Step 3/6", "オッズを取得中...", 30)

    from src.scraper.odds_scraper import OddsScraper

    conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'data/boatrace.db'))
    cursor = conn.cursor()

    all_races = []
    for venue_code, race_date in today_schedule.items():
        race_date_iso = f"{race_date[:4]}-{race_date[4:6]}-{race_date[6:8]}"
        cursor.execute("""
            SELECT id, race_number FROM races
            WHERE venue_code = ? AND race_date = ?
            ORDER BY race_number
        """, (venue_code, race_date_iso))
        for row in cursor.fetchall():
            all_races.append({
                'race_id': row[0],
                'venue_code': venue_code,
                'race_date': race_date,
                'race_number': row[1]
            })
    conn.close()

    if not all_races:
        update_progress("Step 3/6", "オッズ取得対象なし", 45)
        return

    def fetch_single_odds(race_info):
        try:
            scraper = OddsScraper(delay=0.1, max_retries=1)
            odds = scraper.get_trifecta_odds(
                race_info['venue_code'],
                race_info['race_date'],
                race_info['race_number']
            )
            scraper.close()

            if odds and len(odds) > 50:
                conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'data/boatrace.db'))
                cursor = conn.cursor()
                cursor.execute("DELETE FROM trifecta_odds WHERE race_id = ?", (race_info['race_id'],))
                for combo, odds_val in odds.items():
                    cursor.execute(
                        "INSERT INTO trifecta_odds (race_id, combination, odds) VALUES (?, ?, ?)",
                        (race_info['race_id'], combo, odds_val)
                    )
                conn.commit()
                conn.close()
                return True
            return False
        except Exception:
            return False

    success_count = 0
    total = len(all_races)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_single_odds, race): race for race in all_races}

        for i, future in enumerate(concurrent.futures.as_completed(futures, timeout=300), 1):
            if future.result():
                success_count += 1

            if i % 10 == 0:
                pct = 30 + int((i / total) * 15)
                update_progress("Step 3/6", f"オッズ取得中... ({i}/{total})", pct)

    update_progress("Step 3/6", f"オッズ取得完了 ({success_count}/{total}レース)", 45)


def reanalyze_rules():
    """Step 4: 法則を再解析"""
    update_progress("Step 4/6", "法則を再解析中...", 50)

    try:
        from src.analysis.pattern_analyzer import PatternAnalyzer

        analyzer = PatternAnalyzer(
            db_path=os.path.join(PROJECT_ROOT, 'data/boatrace.db')
        )
        analyzer.analyze_all_patterns(
            min_samples=20,
            min_confidence=0.15
        )
        update_progress("Step 4/6", "法則再解析完了", 55)
    except Exception as e:
        print(f"法則再解析エラー: {e}")


def generate_predictions(today_schedule):
    """Step 5: 予測を生成"""
    update_progress("Step 5/6", "予測を生成中...", 60)

    from src.utils.date_utils import to_iso_format

    if not today_schedule:
        update_progress("Step 5/6", "予測対象なし", 85)
        return

    target_date = to_iso_format(list(today_schedule.values())[0])

    # 高速予想生成スクリプトを呼び出し
    import subprocess
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'fast_prediction_generator.py')

    if os.path.exists(script_path):
        try:
            result = subprocess.run(
                [sys.executable, script_path, target_date],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=600
            )
            if result.returncode == 0:
                update_progress("Step 5/6", "予測生成完了", 85)
            else:
                print(f"予測生成エラー: {result.stderr}")
        except subprocess.TimeoutExpired:
            print("予測生成タイムアウト")
    else:
        print(f"スクリプトが見つかりません: {script_path}")


def update_prediction_stats():
    """Step 6: 統計を更新"""
    update_progress("Step 6/6", "統計を更新中...", 90)

    try:
        conn = sqlite3.connect(os.path.join(PROJECT_ROOT, 'data/boatrace.db'))
        cursor = conn.cursor()

        today = datetime.now().strftime('%Y-%m-%d')

        # 今日の予測数を確認
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) FROM predictions
            WHERE DATE(created_at) = ?
        """, (today,))
        prediction_count = cursor.fetchone()[0]

        # 今日のオッズ数を確認
        cursor.execute("""
            SELECT COUNT(DISTINCT race_id) FROM trifecta_odds to_
            JOIN races r ON to_.race_id = r.id
            WHERE r.race_date = ?
        """, (today,))
        odds_count = cursor.fetchone()[0]

        conn.close()

        update_progress("Step 6/6", f"完了: 予測{prediction_count}レース, オッズ{odds_count}レース", 100)
    except Exception as e:
        print(f"統計更新エラー: {e}")


def main():
    """メイン処理"""
    print("=" * 60)
    print("今日の予測生成 - バックグラウンド処理")
    print("=" * 60)

    try:
        # Step 1: データ取得
        today_schedule = fetch_today_data()

        # Step 2: DBビュー更新
        update_db_views()

        # Step 3: オッズ取得
        if today_schedule:
            fetch_odds(today_schedule)

        # Step 4: 法則再解析
        reanalyze_rules()

        # Step 5: 予測生成
        if today_schedule:
            generate_predictions(today_schedule)

        # Step 6: 統計更新
        update_prediction_stats()

        # 完了
        complete_job(JOB_NAME, success=True, message='今日の予測生成が完了しました')
        print("=" * 60)
        print("処理完了")
        print("=" * 60)

    except Exception as e:
        complete_job(JOB_NAME, success=False, message=f'エラー: {str(e)}')
        print(f"エラー発生: {e}")
        raise


if __name__ == '__main__':
    main()
