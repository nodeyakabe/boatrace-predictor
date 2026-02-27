"""
複数年度データ補完の自動連続実行スクリプト

指定した複数の年度を順次自動実行します（完全放置対応）

使用方法:
  # デフォルト（2022, 2024, 2025年を順次実行）
  python scripts/data_collection/補完_複数年度_自動実行.py

  # カスタム年度指定
  python scripts/data_collection/補完_複数年度_自動実行.py --years 2020 2021 2022

  # 特定期間指定
  python scripts/data_collection/補完_複数年度_自動実行.py --start 2020-01-01 --end 2023-12-31

特徴:
- 複数年度を順次自動実行（完全放置可能）
- 各年度の詳細ログ出力
- エラーが発生しても次の年度に継続
- 最終的な全体レポート生成
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import os
import subprocess
import argparse
from datetime import datetime
import time

# プロジェクトルートを取得
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')

# ログディレクトリの作成
os.makedirs(LOG_DIR, exist_ok=True)

# マスターログファイル
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
MASTER_LOG_FILE = os.path.join(LOG_DIR, f'multi_year_completion_{timestamp}.log')

def log_print(message):
    """コンソールとログファイルに同時出力"""
    print(message)
    with open(MASTER_LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(message + '\n')

def run_year_completion(start_date, end_date, year_label):
    """指定期間のデータ補完を実行"""
    script_path = os.path.join(PROJECT_ROOT, 'scripts', 'data_collection', '補完_統合版_決まり手_レース詳細.py')

    log_print(f"\n{'='*80}")
    log_print(f"{year_label}年度 データ補完開始")
    log_print(f"{'='*80}")
    log_print(f"開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"対象期間: {start_date} ～ {end_date}")
    log_print(f"{'='*80}\n")

    start_time = time.time()

    try:
        # サブプロセスで実行
        cmd = [
            sys.executable,
            script_path,
            '--start-date', start_date,
            '--end-date', end_date
        ]

        log_print(f"実行コマンド: {' '.join(cmd)}\n")

        # リアルタイム出力
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',  # デコードエラーを無視
            bufsize=1,
            universal_newlines=True
        )

        # 出力を逐次表示
        for line in process.stdout:
            print(line, end='')
            with open(MASTER_LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(line)

        process.wait()
        elapsed = time.time() - start_time

        if process.returncode == 0:
            log_print(f"\n{'='*80}")
            log_print(f"{year_label}年度 データ補完完了 ✅")
            log_print(f"{'='*80}")
            log_print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"{'='*80}\n")
            return {'year': year_label, 'status': 'success', 'elapsed': elapsed, 'returncode': 0}
        else:
            log_print(f"\n{'='*80}")
            log_print(f"{year_label}年度 データ補完失敗 ❌")
            log_print(f"{'='*80}")
            log_print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
            log_print(f"終了コード: {process.returncode}")
            log_print(f"{'='*80}\n")
            return {'year': year_label, 'status': 'failed', 'elapsed': elapsed, 'returncode': process.returncode}

    except Exception as e:
        elapsed = time.time() - start_time
        log_print(f"\n{'='*80}")
        log_print(f"{year_label}年度 データ補完エラー ❌")
        log_print(f"{'='*80}")
        log_print(f"エラー内容: {str(e)}")
        log_print(f"終了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_print(f"処理時間: {elapsed/3600:.2f}時間（{elapsed/60:.1f}分）")
        log_print(f"{'='*80}\n")
        return {'year': year_label, 'status': 'error', 'elapsed': elapsed, 'error': str(e)}

def main():
    parser = argparse.ArgumentParser(description='複数年度データ補完の自動連続実行')
    parser.add_argument('--years', nargs='+', type=int, help='補完する年度のリスト（例: 2020 2021 2022）')
    parser.add_argument('--start', type=str, help='開始日 (YYYY-MM-DD形式、--yearsと併用不可)')
    parser.add_argument('--end', type=str, help='終了日 (YYYY-MM-DD形式、--yearsと併用不可)')

    args = parser.parse_args()

    log_print("="*80)
    log_print("複数年度データ補完 自動連続実行スクリプト")
    log_print("="*80)
    log_print(f"実行開始: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"マスターログ: {MASTER_LOG_FILE}")
    log_print("="*80)

    overall_start = time.time()
    results = []

    # 実行プランの決定
    if args.start and args.end:
        # 特定期間指定
        log_print(f"\n実行モード: 特定期間指定")
        log_print(f"対象期間: {args.start} ～ {args.end}\n")

        result = run_year_completion(args.start, args.end, f"{args.start}～{args.end}")
        results.append(result)

    elif args.years:
        # 年度リスト指定
        log_print(f"\n実行モード: 年度リスト指定")
        log_print(f"対象年度: {', '.join(map(str, args.years))}年\n")

        for year in args.years:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
            result = run_year_completion(start_date, end_date, str(year))
            results.append(result)

    else:
        # デフォルト: 2022, 2024, 2025年
        default_years = [2022, 2024, 2025]
        log_print(f"\n実行モード: デフォルト")
        log_print(f"対象年度: {', '.join(map(str, default_years))}年\n")

        for year in default_years:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"
            result = run_year_completion(start_date, end_date, str(year))
            results.append(result)

    overall_elapsed = time.time() - overall_start

    # 最終レポート
    log_print("\n" + "="*80)
    log_print("最終レポート")
    log_print("="*80)
    log_print(f"全体完了時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log_print(f"総処理時間: {overall_elapsed/3600:.2f}時間（{overall_elapsed/60:.1f}分）")
    log_print("\n" + "-"*80)
    log_print("年度別結果")
    log_print("-"*80)

    success_count = 0
    failed_count = 0
    error_count = 0

    for result in results:
        status_icon = "✅" if result['status'] == 'success' else "❌"
        log_print(f"\n  {result['year']}年度: {status_icon} {result['status'].upper()}")
        log_print(f"    処理時間: {result['elapsed']/60:.1f}分")

        if result['status'] == 'success':
            success_count += 1
        elif result['status'] == 'failed':
            failed_count += 1
            log_print(f"    終了コード: {result['returncode']}")
        else:
            error_count += 1
            log_print(f"    エラー: {result.get('error', 'Unknown')}")

    log_print("\n" + "-"*80)
    log_print("サマリー")
    log_print("-"*80)
    log_print(f"  総年度数: {len(results)}年度")
    log_print(f"  成功: {success_count}年度 ✅")
    log_print(f"  失敗: {failed_count}年度 ❌")
    log_print(f"  エラー: {error_count}年度 ❌")

    if success_count == len(results):
        log_print(f"\n🎉 全年度のデータ補完が正常に完了しました！")
    else:
        log_print(f"\n⚠️ 一部の年度で問題が発生しました。詳細はログを確認してください。")

    log_print("\n" + "="*80)
    log_print(f"マスターログファイル: {MASTER_LOG_FILE}")
    log_print("="*80)

    # 終了コード
    if failed_count > 0 or error_count > 0:
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
