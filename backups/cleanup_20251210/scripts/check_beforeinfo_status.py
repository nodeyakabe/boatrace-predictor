# -*- coding: utf-8 -*-
"""直前情報の実装状況確認

現在の実装状況を把握し、重複実装を避ける
"""

import sys
import sqlite3
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def main():
    db_path = ROOT_DIR / "data" / "boatrace.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    print("=" * 80)
    print("直前情報実装状況の確認")
    print("=" * 80)
    print()

    # 1. テーブル構造の確認
    print("【1】データベーステーブル")
    print("-" * 80)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()

    beforeinfo_tables = [t['name'] for t in tables if 'before' in t['name'].lower()]

    if beforeinfo_tables:
        print("直前情報関連テーブル:")
        for table in beforeinfo_tables:
            cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
            count = cursor.fetchone()['cnt']
            print(f"  - {table}: {count:,}件")

            # カラム確認
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            print(f"    カラム数: {len(columns)}")
            for col in columns[:5]:  # 最初の5カラムのみ
                print(f"      - {col['name']} ({col['type']})")
            if len(columns) > 5:
                print(f"      ... 他{len(columns)-5}カラム")
    else:
        print("直前情報関連テーブル: なし")

    print()

    # 2. 直前情報データの収集状況
    print("【2】直前情報データ収集状況")
    print("-" * 80)

    if beforeinfo_tables:
        for table in beforeinfo_tables:
            # サンプルデータ確認
            cursor.execute(f"SELECT * FROM {table} LIMIT 1")
            sample = cursor.fetchone()
            if sample:
                print(f"{table} サンプル:")
                for key in sample.keys()[:10]:  # 最初の10フィールド
                    print(f"  {key}: {sample[key]}")
                print()

    # 3. 2025年データでの直前情報取得状況
    print("【3】2025年レースでの直前情報取得状況")
    print("-" * 80)

    cursor.execute('''
        SELECT
            COUNT(*) as total_races,
            strftime('%Y-%m', race_date) as month
        FROM races
        WHERE race_date >= '2025-01-01' AND race_date <= '2025-12-31'
        GROUP BY month
        ORDER BY month
    ''')
    race_counts = cursor.fetchall()

    print("月別レース数:")
    for row in race_counts:
        print(f"  {row['month']}: {row['total_races']:,}レース")

    print()

    # 直前情報が存在する2025年レース
    if beforeinfo_tables:
        main_table = beforeinfo_tables[0]
        cursor.execute(f'''
            SELECT COUNT(*) as cnt
            FROM {main_table} b
            JOIN races r ON b.race_id = r.id
            WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ''')
        beforeinfo_2025_count = cursor.fetchone()['cnt']
        print(f"2025年レースで直前情報あり: {beforeinfo_2025_count:,}件")

    print()

    # 4. BeforeInfoScorerの実装確認
    print("【4】BeforeInfoScorerの実装確認")
    print("-" * 80)

    beforeinfo_scorer_path = ROOT_DIR / "src" / "analysis" / "beforeinfo_scorer.py"
    if beforeinfo_scorer_path.exists():
        print(f"[OK] BeforeInfoScorer実装済み: {beforeinfo_scorer_path}")
        with open(beforeinfo_scorer_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            print(f"   行数: {len(lines)}")

            # 主要メソッドの確認
            print("   主要メソッド:")
            for i, line in enumerate(lines):
                if 'def ' in line and 'self' in line:
                    method_name = line.strip().split('(')[0].replace('def ', '')
                    if i < 20 or 'calculate' in method_name or 'score' in method_name:
                        print(f"     - {method_name}")
    else:
        print("[NG] BeforeInfoScorer未実装")

    print()

    # 5.[NG] RacePredictorでの統合状況
    print("【5】RacePredictorでの統合状況")
    print("-" * 80)

    race_predictor_path = ROOT_DIR / "src" / "analysis" / "race_predictor.py"
    if race_predictor_path.exists():
        with open(race_predictor_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'BeforeInfoScorer' in content:
            print("[OK] BeforeInfoScorerが統合済み")
            print(f"   出現箇所: {content.count('BeforeInfoScorer')}回")

            # 統合式の確認
            if 'PRE_SCORE' in content and 'BEFORE_SCORE' in content:
                print("[OK] 統合スコア計算式あり")
            else:
                print("[WARN] 統合スコア計算式が見つからない")
        else:
            print("[NG] BeforeInfoScorerが未統合")
    else:
        print("[NG][NG] RacePredictor未実装")

    print()

    # 6. BetTargetEvaluatorでの直前情報活用状況
    print("【6】BetTargetEvaluatorでの直前情報活用状況")
    print("-" * 80)

    bet_evaluator_path = ROOT_DIR / "src" / "betting" / "bet_target_evaluator.py"
    if bet_evaluator_path.exists():
        with open(bet_evaluator_path, 'r', encoding='utf-8') as f:
            content = f.read()

        if 'has_beforeinfo' in content:
            print("[OK] has_beforeinfoパラメータあり")

            # 実際に使われているか
            if 'if has_beforeinfo' in content or 'if not has_beforeinfo' in content:
                print("[OK] 直前情報の有無で処理分岐あり")
            else:
                print("[WARN] has_beforeinfoパラメータは存在するが未使用")
        else:
            print("[NG] 直前情報対応なし")

    print()

    # 7. 実運用での直前情報活用状況（バックテスト可否）
    print("【7】バックテスト実施可否")
    print("-" * 80)

    # 2025年データで直前情報 + 結果が両方あるレース数
    if beforeinfo_tables:
        cursor.execute(f'''
            SELECT COUNT(DISTINCT r.id) as cnt
            FROM races r
            JOIN {beforeinfo_tables[0]} b ON r.id = b.race_id
            JOIN results res ON r.id = res.race_id
            WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
            AND res.rank = 1
        ''')
        backtest_available = cursor.fetchone()['cnt']

        print(f"バックテスト可能レース数（直前情報 + 結果あり）: {backtest_available:,}")

        if backtest_available > 0:
            print("[OK] 直前情報フィルターのバックテスト実施可能")
        else:
            print("[NG][OK] バックテスト不可（データ不足）")
    else:
        print("[NG] 直前情報データなし")

    print()

    # 8. 結論
    print("=" * 80)
    print("【結論】実装状況サマリー")
    print("=" * 80)

    if beforeinfo_tables and beforeinfo_scorer_path.exists():
        print("[OK] 直前情報機能は既に実装済み")
        print()
        print("実装済み機能:")
        print("  1. BeforeInfoScorer（スコアリングエンジン）")
        print("  2.[NG] RacePredictorへの統合（事前 + 直前スコア）")
        print("  3. データベーステーブル")
        print("  4. データ収集スクリプト")
        print()

        if backtest_available > 0:
            print(f"バックテスト: {backtest_available:,}レースで実施可能")
        else:
            print("バックテスト: データ不足（2025年の直前情報収集が必要）")

        print()
        print("次のアクション:")
        print("  - 直前情報の追加実装は不要")
        print("  - BetTargetEvaluatorで直前情報フィルター活用を検討")
        print("  - 2025年データでの精度検証を実施")
    else:
        print("[WARN] 直前情報機能の実装が不完全")
        print()
        print("実装が必要:")
        if not beforeinfo_tables:
            print("  - データベーステーブル")
        if not beforeinfo_scorer_path.exists():
            print("  - BeforeInfoScorer")

    print("=" * 80)

    conn.close()


if __name__ == '__main__':
    main()
