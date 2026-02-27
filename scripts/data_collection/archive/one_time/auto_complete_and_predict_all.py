"""
全データ補完＆予測生成 完全自動実行スクリプト

処理フロー:
  1. 現在実行中の補完完了待機
  2. 2020-2023年 prev_race_rank収集
  3. 2024-2025年 決まり手+ST time補完（必要に応じて）
  4. 2024-2025年 prev_race_rank収集
  5. 全期間 予測生成（before予想）
  6. 全期間 予測生成（アドバンス予想）

使用方法:
  python scripts/data_collection/auto_complete_and_predict_all.py

特徴:
- 完全放置実行可能（推定24-30時間）
- 詳細ログ出力
- エラー時も可能な限り継続
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
import sqlite3

PROJECT_ROOT = Path(__file__).parent.parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
MASTER_LOG_FILE = LOG_DIR / f'auto_complete_predict_{timestamp}.log'

def log_print(message):
    """コンソールとログファイルに同時出力"""
    print(message)
    with open(MASTER_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(message + '\n')

def get_latest_multi_year_log():
    """最新のmulti_year_completionログを取得"""
    log_files = list(LOG_DIR.glob("multi_year_completion_*.log"))
    if not log_files:
        return None
    return max(log_files, key=lambda f: f.stat().st_mtime)

def wait_for_current_completion():
    """現在実行中のデータ補完の完了を待つ"""
    log_print("\n" + "="*80)
    log_print("Phase 0: 現在実行中のデータ補完完了待機")
    log_print("="*80)

    log_file = get_latest_multi_year_log()
    if not log_file:
        log_print("[INFO] 実行中のデータ補完が見つかりません（スキップ）")
        return True

    log_print(f"監視対象: {log_file}")

    last_size = 0
    stable_count = 0

    while True:
        if not log_file.exists():
            log_print("[INFO] ログファイルが削除されました（完了とみなす）")
            return True

        current_size = log_file.stat().st_size

        if current_size == last_size:
            stable_count += 1
            if stable_count >= 3:  # 30秒間変化なし
                # 最終レポート確認
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
                        content = f.read()
                        if '最終レポート' in content or '全体完了時刻' in content:
                            log_print("\n[OK] データ補完が完了しました")
                            return True
                except:
                    pass
        else:
            stable_count = 0
            last_size = current_size

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 待機中... (ログサイズ: {current_size:,} bytes)", end='\r')
        time.sleep(10)

def run_subprocess(cmd, phase_name, timeout_hours=12):
    """サブプロセス実行（リアルタイム出力付き）"""
    log_print(f"\n{'='*80}")
    log_print(f"{phase_name}")
    log_print(f"{'='*80}")
    log_print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"実行コマンド: {' '.join(cmd)}")
    log_print(f"{'='*80}\n")

    start_time = time.time()

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        # リアルタイム出力
        for line in process.stdout:
            print(line, end='')
            with open(MASTER_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(line)

        process.wait()
        elapsed = time.time() - start_time

        log_print(f"\n{'='*80}")
        if process.returncode == 0:
            log_print(f"✅ {phase_name} 完了")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"{'='*80}\n")
            return True
        else:
            log_print(f"❌ {phase_name} 失敗（終了コード: {process.returncode}）")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"{'='*80}\n")
            return False

    except Exception as e:
        elapsed = time.time() - start_time
        log_print(f"\n{'='*80}")
        log_print(f"❌ {phase_name} エラー")
        log_print(f"エラー内容: {str(e)}")
        log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
        log_print(f"{'='*80}\n")
        return False

def check_data_coverage(years):
    """指定年度のデータ充足率を確認"""
    db_path = PROJECT_ROOT / "data" / "boatrace.db"
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    results = {}
    for year in years:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        # 決まり手充足率
        cursor.execute(f'''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN kimarite IS NOT NULL THEN 1 ELSE 0 END) as has_kimarite
            FROM results r
            JOIN races rc ON r.race_id = rc.id
            WHERE rc.race_date BETWEEN '{start_date}' AND '{end_date}'
                AND r.rank = '1'
        ''')
        total, has_kimarite = cursor.fetchone()
        kimarite_rate = (has_kimarite / total * 100) if total > 0 else 0

        # ST time充足率
        cursor.execute(f'''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN st_time IS NOT NULL THEN 1 ELSE 0 END) as has_st
            FROM race_details rd
            JOIN races rc ON rd.race_id = rc.id
            WHERE rc.race_date BETWEEN '{start_date}' AND '{end_date}'
        ''')
        total, has_st = cursor.fetchone()
        st_rate = (has_st / total * 100) if total > 0 else 0

        # prev_race_rank充足率
        cursor.execute(f'''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN prev_race_rank IS NOT NULL THEN 1 ELSE 0 END) as has_prev
            FROM race_details rd
            JOIN races rc ON rd.race_id = rc.id
            WHERE rc.race_date BETWEEN '{start_date}' AND '{end_date}'
        ''')
        total, has_prev = cursor.fetchone()
        prev_rank_rate = (has_prev / total * 100) if total > 0 else 0

        results[year] = {
            'kimarite': kimarite_rate,
            'st_time': st_rate,
            'prev_race_rank': prev_rank_rate
        }

    conn.close()
    return results

def main():
    log_print("="*80)
    log_print("全データ補完＆予測生成 完全自動実行スクリプト")
    log_print("="*80)
    log_print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"マスターログ: {MASTER_LOG_FILE}")
    log_print("="*80)

    overall_start = time.time()
    results = []

    # Phase 0: 現在実行中の補完完了待機（スキップ：すでに完了済み）
    log_print("\n[INFO] Phase 0をスキップ（既存の補完は完了済み）")

    # if not wait_for_current_completion():
    #     log_print("[ERROR] 現在実行中の補完待機でタイムアウト")
    #     return 1
    # time.sleep(5)  # ファイルクローズ等の待機

    # Phase 1: 2020-2023年 prev_race_rank収集（CSV方式）
    csv_output_dir = PROJECT_ROOT / "data" / "csv" / "beforeinfo" / "2020-2023"
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "data_collection" / "collect_beforeinfo_to_csv_parallel.py"),
        "--start", "2020-01-01",
        "--end", "2023-12-31",
        "--output", str(csv_output_dir),
        "--workers", "12"
    ]
    success = run_subprocess(cmd, "Phase 1-A: 2020-2023年 prev_race_rank収集（CSV）")
    results.append(("Phase 1-A: prev_race_rank CSV収集 (2020-2023)", success))

    # Phase 1-B: CSV→DB投入
    if success:
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "data_collection" / "import_beforeinfo_csv_to_db.py"),
            "--input", str(csv_output_dir)
        ]
        success = run_subprocess(cmd, "Phase 1-B: 2020-2023年 prev_race_rank DB投入")
        results.append(("Phase 1-B: prev_race_rank DB投入 (2020-2023)", success))
    else:
        log_print("[ERROR] Phase 1-A失敗のためPhase 1-Bをスキップ")
        results.append(("Phase 1-B: prev_race_rank DB投入 (2020-2023)", False))

    # Phase 2: 2024-2025年データ充足率確認
    log_print("\n" + "="*80)
    log_print("Phase 2: 2024-2025年データ充足率確認")
    log_print("="*80)

    coverage = check_data_coverage([2024, 2025])
    need_2024_2025 = False

    if coverage:
        for year, rates in coverage.items():
            log_print(f"\n{year}年:")
            log_print(f"  決まり手: {rates['kimarite']:.1f}%")
            log_print(f"  ST time: {rates['st_time']:.1f}%")
            log_print(f"  prev_race_rank: {rates['prev_race_rank']:.1f}%")

            if rates['kimarite'] < 95 or rates['st_time'] < 95 or rates['prev_race_rank'] < 95:
                need_2024_2025 = True

    # Phase 3: 2024-2025年 決まり手+ST time補完（必要な場合）
    if need_2024_2025:
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "data_collection" / "補完_複数年度_自動実行.py"),
            "--years", "2024", "2025"
        ]
        success = run_subprocess(cmd, "Phase 3: 2024-2025年 決まり手+ST time補完")
        results.append(("Phase 3: 決まり手+ST補完 (2024-2025)", success))
    else:
        log_print("\n[INFO] 2024-2025年のデータは充足しているためスキップ")
        results.append(("Phase 3: 決まり手+ST補完 (2024-2025)", True))

    # Phase 4: 2024-2025年 prev_race_rank収集（CSV方式）
    csv_output_dir = PROJECT_ROOT / "data" / "csv" / "beforeinfo" / "2024-2025"
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "data_collection" / "collect_beforeinfo_to_csv_parallel.py"),
        "--start", "2024-01-01",
        "--end", "2025-12-31",
        "--output", str(csv_output_dir),
        "--workers", "12"
    ]
    success = run_subprocess(cmd, "Phase 4-A: 2024-2025年 prev_race_rank収集（CSV）")
    results.append(("Phase 4-A: prev_race_rank CSV収集 (2024-2025)", success))

    # Phase 4-B: CSV→DB投入
    if success:
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "data_collection" / "import_beforeinfo_csv_to_db.py"),
            "--input", str(csv_output_dir)
        ]
        success = run_subprocess(cmd, "Phase 4-B: 2024-2025年 prev_race_rank DB投入")
        results.append(("Phase 4-B: prev_race_rank DB投入 (2024-2025)", success))
    else:
        log_print("[ERROR] Phase 4-A失敗のためPhase 4-Bをスキップ")
        results.append(("Phase 4-B: prev_race_rank DB投入 (2024-2025)", False))

    # Phase 5: 全期間 予測生成（before予想）
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "prediction" / "generate_predictions.py"),
        "--years", "2020,2021,2022,2023,2024,2025",
        "--type", "before"
    ]
    success = run_subprocess(cmd, "Phase 5: 全期間 予測生成（before予想）")
    results.append(("Phase 5: before予想生成", success))

    # Phase 6: 全期間 予測生成（アドバンス予想）
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "prediction" / "generate_predictions.py"),
        "--years", "2020,2021,2022,2023,2024,2025",
        "--type", "advance"
    ]
    success = run_subprocess(cmd, "Phase 6: 全期間 予測生成（アドバンス予想）")
    results.append(("Phase 6: アドバンス予想生成", success))

    # 最終レポート
    overall_elapsed = time.time() - overall_start

    log_print("\n" + "="*80)
    log_print("最終レポート")
    log_print("="*80)
    log_print(f"全体完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"総処理時間: {overall_elapsed/3600:.2f}時間（{overall_elapsed/60:.1f}分）")
    log_print("\n" + "-"*80)
    log_print("フェーズ別結果")
    log_print("-"*80)

    success_count = sum(1 for _, success in results if success)
    failed_count = len(results) - success_count

    for phase_name, success in results:
        status_icon = "✅" if success else "❌"
        log_print(f"  {status_icon} {phase_name}")

    log_print("\n" + "-"*80)
    log_print("サマリー")
    log_print("-"*80)
    log_print(f"  総フェーズ数: {len(results)}")
    log_print(f"  成功: {success_count} ✅")
    log_print(f"  失敗: {failed_count} ❌")

    if success_count == len(results):
        log_print(f"\n🎉 すべてのフェーズが正常に完了しました！")
    else:
        log_print(f"\n⚠️ 一部のフェーズで問題が発生しました。詳細はログを確認してください。")

    log_print("\n" + "="*80)
    log_print(f"マスターログファイル: {MASTER_LOG_FILE}")
    log_print("="*80)

    return 0 if failed_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
