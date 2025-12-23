#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
バックテスト実行準備スクリプト

実行前チェック:
1. 2024年データの完全性
2. advance予測データの存在
3. 払戻金データの整合性
4. バックテストスクリプトの動作確認

実行後:
- バックテスト実行コマンドを提示
- 推定実行時間を表示
"""
import sys
import os
import io
import sqlite3

# Windows環境でのUTF-8出力設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH

def check_backtest_readiness():
    """バックテスト実行準備の確認"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 80)
    print("バックテスト実行準備チェック")
    print("=" * 80)

    checks = []

    # 1. 2024年レース数
    cursor.execute("""
        SELECT COUNT(*)
        FROM races
        WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
    """)
    total_races = cursor.fetchone()[0]
    print(f"\n[1/6] 2024年レース数: {total_races:,}")
    checks.append(('レース数', total_races >= 12000, f"{total_races:,} >= 12,000"))

    # 2. advance予測データ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM race_predictions
        WHERE prediction_type = 'advance'
        AND race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    advance_races = cursor.fetchone()[0]
    advance_coverage = advance_races / total_races * 100 if total_races > 0 else 0
    print(f"[2/6] advance予測: {advance_races:,}レース ({advance_coverage:.1f}%)")
    checks.append(('advance予測', advance_coverage >= 95, f"{advance_coverage:.1f}% >= 95%"))

    # 3. 結果データ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM results
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    result_races = cursor.fetchone()[0]
    result_coverage = result_races / total_races * 100 if total_races > 0 else 0
    print(f"[3/6] 結果データ: {result_races:,}レース ({result_coverage:.1f}%)")
    checks.append(('結果データ', result_coverage >= 95, f"{result_coverage:.1f}% >= 95%"))

    # 4. 払戻金データ
    cursor.execute("""
        SELECT COUNT(DISTINCT race_id)
        FROM payouts
        WHERE race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    payout_races = cursor.fetchone()[0]
    payout_coverage = payout_races / total_races * 100 if total_races > 0 else 0
    print(f"[4/6] 払戻金データ: {payout_races:,}レース ({payout_coverage:.1f}%)")
    checks.append(('払戻金データ', payout_coverage >= 95, f"{payout_coverage:.1f}% >= 95%"))

    # 5. 予測と結果の整合性
    cursor.execute("""
        SELECT COUNT(*)
        FROM race_predictions rp
        JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE rp.prediction_type = 'advance'
        AND rp.race_id IN (
            SELECT id FROM races
            WHERE race_date >= '2024-01-01' AND race_date < '2025-01-01'
        )
    """)
    matching_predictions = cursor.fetchone()[0]
    print(f"[5/6] 予測-結果マッチング: {matching_predictions:,}件")
    checks.append(('予測-結果整合性', matching_predictions > 50000, f"{matching_predictions:,} > 50,000"))

    # 6. バックテストスクリプトの存在
    backtest_script = os.path.join(PROJECT_ROOT, 'scripts', 'run_2024_backtest.py')
    script_exists = os.path.exists(backtest_script)
    print(f"[6/6] バックテストスクリプト: {'✅ 存在' if script_exists else '🔴 不在'}")
    checks.append(('スクリプト存在', script_exists, backtest_script))

    # 結果サマリー
    print("\n" + "=" * 80)
    print("チェック結果")
    print("=" * 80)

    all_passed = True
    for name, passed, detail in checks:
        status = "✅ OK" if passed else "🔴 NG"
        print(f"  {name:<20} {status:<8} ({detail})")
        if not passed:
            all_passed = False

    print("\n" + "=" * 80)

    if all_passed:
        print("✅ バックテスト実行可能")
        print("\n" + "=" * 80)
        print("バックテスト実行コマンド")
        print("=" * 80)
        print("\n【基本実行】")
        print("python scripts/run_2024_backtest.py")
        print("\n【戦略指定】")
        print("python scripts/run_2024_backtest.py --strategy baseline")
        print("python scripts/run_2024_backtest.py --strategy strategy_b")
        print("\n【期間指定】")
        print("python scripts/run_2024_backtest.py --start-date 2024-01-01 --end-date 2024-03-31")
        print("\n【信頼度フィルタ】")
        print("python scripts/run_2024_backtest.py --min-confidence B")

        # 推定実行時間
        estimated_time = total_races * 0.01  # 1レースあたり0.01秒と仮定
        print(f"\n推定実行時間: {estimated_time:.0f}秒 ({estimated_time/60:.1f}分)")

        # 次のステップ
        print("\n" + "=" * 80)
        print("推奨実行順序")
        print("=" * 80)
        print("1. ベースライン検証:")
        print("   python scripts/run_2024_backtest.py --strategy baseline")
        print("\n2. 戦略B検証:")
        print("   python scripts/run_2024_backtest.py --strategy strategy_b")
        print("\n3. 信頼度別分析:")
        print("   python scripts/analyze_confidence_levels.py")
        print("\n4. 月別推移分析:")
        print("   python scripts/analyze_monthly_performance.py")

    else:
        print("🔴 バックテスト実行不可")
        print("\n必要な対応:")
        for name, passed, detail in checks:
            if not passed:
                if 'advance予測' in name:
                    print(f"\n  {name}が不足:")
                    print(f"    python scripts/generate_predictions_2024_all.py --type advance")
                elif '結果データ' in name or '払戻金データ' in name:
                    print(f"\n  {name}が不足:")
                    print(f"    python scripts/collect_2024_missing_data.py")
                elif 'スクリプト' in name:
                    print(f"\n  {name}:")
                    print(f"    バックテストスクリプトを作成してください")

    print("\n" + "=" * 80)

    conn.close()
    return all_passed

if __name__ == "__main__":
    try:
        success = check_backtest_readiness()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n🔴 エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
