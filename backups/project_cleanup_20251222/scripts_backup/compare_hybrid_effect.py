"""
ハイブリッドスコアリング効果比較スクリプト

目的: 旧版（2025-12-08）と新版（2025-12-10）の信頼度B予測を比較し
      2着・3着精度改善効果を検証

比較内容:
1. 信頼度Bの三連単的中率（旧 vs 新）
2. 2着・3着の個別的中率（旧 vs 新）
3. 統計的有意性の検定
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from scipy import stats


def compare_hybrid_effect(db_path: str, start_date: str, end_date: str):
    """
    ハイブリッドスコアリング効果を比較

    Args:
        db_path: データベースパス
        start_date: 検証開始日 (YYYY-MM-DD)
        end_date: 検証終了日 (YYYY-MM-DD)
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print("ハイブリッドスコアリング効果比較（旧版 vs 新版）")
    print("=" * 80)
    print(f"\n検証期間: {start_date} ～ {end_date}")
    print("旧版: 2025-12-08 生成（ハイブリッドなし）")
    print("新版: 2025-12-10 生成（ハイブリッドあり）")
    print()

    # 1. 旧版データ取得（2025-12-08生成、信頼度Bのみ）
    query_old = """
    WITH ranked_predictions AS (
        SELECT
            rp.race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            rp.pit_number,
            rp.rank_prediction,
            rp.confidence,
            rp.total_score,
            res.rank as actual_rank
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND rp.pit_number = res.pit_number
        WHERE r.race_date >= ?
          AND r.race_date <= ?
          AND rp.generated_at >= '2025-12-08'
          AND rp.generated_at < '2025-12-09'
          AND rp.confidence = 'B'
          AND res.rank IS NOT NULL
    ),
    race_predictions_ranked AS (
        SELECT DISTINCT
            race_id,
            race_date,
            venue_code,
            race_number
        FROM ranked_predictions
        GROUP BY race_id, race_date, venue_code, race_number
    ),
    predicted_trifecta AS (
        SELECT
            rpr.race_id,
            rpr.race_date,
            rpr.venue_code,
            rpr.race_number,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_predictions_ranked rpr
        JOIN ranked_predictions rp ON rpr.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rpr.race_id, rpr.race_date, rpr.venue_code, rpr.race_number
    ),
    actual_trifecta AS (
        SELECT
            race_id,
            MAX(CASE WHEN actual_rank = '1' THEN pit_number END) as actual_1st,
            MAX(CASE WHEN actual_rank = '2' THEN pit_number END) as actual_2nd,
            MAX(CASE WHEN actual_rank = '3' THEN pit_number END) as actual_3rd
        FROM ranked_predictions
        WHERE actual_rank IN ('1', '2', '3')
        GROUP BY race_id
    )
    SELECT
        pt.race_id,
        pt.race_date,
        pt.venue_code,
        pt.race_number,
        pt.pred_1st,
        pt.pred_2nd,
        pt.pred_3rd,
        at.actual_1st,
        at.actual_2nd,
        at.actual_3rd,
        CASE
            WHEN pt.pred_1st = at.actual_1st
             AND pt.pred_2nd = at.actual_2nd
             AND pt.pred_3rd = at.actual_3rd
            THEN 1
            ELSE 0
        END as is_trifecta_hit
    FROM predicted_trifecta pt
    LEFT JOIN actual_trifecta at ON pt.race_id = at.race_id
    WHERE pt.pred_1st IS NOT NULL
      AND pt.pred_2nd IS NOT NULL
      AND pt.pred_3rd IS NOT NULL
      AND at.actual_1st IS NOT NULL
      AND at.actual_2nd IS NOT NULL
      AND at.actual_3rd IS NOT NULL
    ORDER BY pt.race_date, pt.race_id
    """

    # 2. 新版データ取得（2025-12-10生成、信頼度Bのみ）
    query_new = query_old.replace("AND rp.generated_at >= '2025-12-08'", "AND rp.generated_at >= '2025-12-10'")
    query_new = query_new.replace("AND rp.generated_at < '2025-12-09'", "AND rp.generated_at < '2025-12-11'")

    df_old = pd.read_sql_query(query_old, conn, params=(start_date, end_date))
    df_new = pd.read_sql_query(query_new, conn, params=(start_date, end_date))

    if len(df_old) == 0 or len(df_new) == 0:
        print("警告: 比較データが不足しています。")
        print(f"旧版: {len(df_old)}件")
        print(f"新版: {len(df_new)}件")
        conn.close()
        return

    print(f"信頼度Bレース数:")
    print(f"  旧版（ハイブリッドなし）: {len(df_old):,}レース")
    print(f"  新版（ハイブリッドあり）: {len(df_new):,}レース")
    print()

    # 3. 三連単的中率比較
    print("=" * 80)
    print("【1】 三連単的中率比較")
    print("=" * 80)

    trifecta_rate_old = df_old['is_trifecta_hit'].mean() * 100
    trifecta_rate_new = df_new['is_trifecta_hit'].mean() * 100

    print(f"\n三連単的中率:")
    print(f"  旧版: {trifecta_rate_old:.2f}% ({df_old['is_trifecta_hit'].sum()}/{len(df_old)})")
    print(f"  新版: {trifecta_rate_new:.2f}% ({df_new['is_trifecta_hit'].sum()}/{len(df_new)})")
    print(f"  改善: {trifecta_rate_new - trifecta_rate_old:+.2f}ポイント")

    # 統計的有意性検定
    contingency_trifecta = [
        [df_old['is_trifecta_hit'].sum(), len(df_old) - df_old['is_trifecta_hit'].sum()],
        [df_new['is_trifecta_hit'].sum(), len(df_new) - df_new['is_trifecta_hit'].sum()]
    ]
    chi2, p_value = stats.chi2_contingency(contingency_trifecta)[:2]

    print(f"\n統計的有意性:")
    print(f"  p値={p_value:.4f} {'(有意)' if p_value < 0.05 else '(有意差なし)'}")

    # 4. 1着・2着・3着の個別的中率比較
    print("\n" + "=" * 80)
    print("【2】 各着順の的中率比較")
    print("=" * 80)

    # 1着的中率
    df_old['is_1st_hit'] = (df_old['pred_1st'] == df_old['actual_1st']).astype(int)
    df_new['is_1st_hit'] = (df_new['pred_1st'] == df_new['actual_1st']).astype(int)

    first_rate_old = df_old['is_1st_hit'].mean() * 100
    first_rate_new = df_new['is_1st_hit'].mean() * 100

    print(f"\n1着的中率:")
    print(f"  旧版: {first_rate_old:.2f}%")
    print(f"  新版: {first_rate_new:.2f}%")
    print(f"  差分: {first_rate_new - first_rate_old:+.2f}ポイント")

    # 2着的中率（1着が当たった場合のみ）
    df_1st_hit_old = df_old[df_old['is_1st_hit'] == 1].copy()
    df_1st_hit_new = df_new[df_new['is_1st_hit'] == 1].copy()

    if len(df_1st_hit_old) > 0 and len(df_1st_hit_new) > 0:
        df_1st_hit_old['is_2nd_hit'] = (df_1st_hit_old['pred_2nd'] == df_1st_hit_old['actual_2nd']).astype(int)
        df_1st_hit_new['is_2nd_hit'] = (df_1st_hit_new['pred_2nd'] == df_1st_hit_new['actual_2nd']).astype(int)

        second_rate_old = df_1st_hit_old['is_2nd_hit'].mean() * 100
        second_rate_new = df_1st_hit_new['is_2nd_hit'].mean() * 100

        print(f"\n2着的中率（1着的中時）:")
        print(f"  旧版: {second_rate_old:.2f}% ({df_1st_hit_old['is_2nd_hit'].sum()}/{len(df_1st_hit_old)})")
        print(f"  新版: {second_rate_new:.2f}% ({df_1st_hit_new['is_2nd_hit'].sum()}/{len(df_1st_hit_new)})")
        print(f"  改善: {second_rate_new - second_rate_old:+.2f}ポイント")

        # 3着的中率（1着・2着が当たった場合のみ）
        df_12_hit_old = df_1st_hit_old[df_1st_hit_old['is_2nd_hit'] == 1].copy()
        df_12_hit_new = df_1st_hit_new[df_1st_hit_new['is_2nd_hit'] == 1].copy()

        if len(df_12_hit_old) > 0 and len(df_12_hit_new) > 0:
            df_12_hit_old['is_3rd_hit'] = (df_12_hit_old['pred_3rd'] == df_12_hit_old['actual_3rd']).astype(int)
            df_12_hit_new['is_3rd_hit'] = (df_12_hit_new['pred_3rd'] == df_12_hit_new['actual_3rd']).astype(int)

            third_rate_old = df_12_hit_old['is_3rd_hit'].mean() * 100
            third_rate_new = df_12_hit_new['is_3rd_hit'].mean() * 100

            print(f"\n3着的中率（1着・2着的中時）:")
            print(f"  旧版: {third_rate_old:.2f}% ({df_12_hit_old['is_3rd_hit'].sum()}/{len(df_12_hit_old)})")
            print(f"  新版: {third_rate_new:.2f}% ({df_12_hit_new['is_3rd_hit'].sum()}/{len(df_12_hit_new)})")
            print(f"  改善: {third_rate_new - third_rate_old:+.2f}ポイント")
        else:
            print(f"\n3着的中率: サンプル不足（旧版{len(df_12_hit_old)}件、新版{len(df_12_hit_new)}件）")
    else:
        print(f"\n2着・3着的中率: サンプル不足（1着的中数: 旧版{len(df_1st_hit_old)}件、新版{len(df_1st_hit_new)}件）")

    # 5. 総合評価
    print("\n" + "=" * 80)
    print("【3】 総合評価")
    print("=" * 80)

    print(f"\nハイブリッドスコアリングの効果:")

    improvements = []
    no_changes = []

    # 三連単的中率
    if trifecta_rate_new > trifecta_rate_old:
        improvements.append(f"[改善] 三連単的中率が向上（{trifecta_rate_new - trifecta_rate_old:+.2f}pt）")
    elif trifecta_rate_new < trifecta_rate_old:
        no_changes.append(f"[悪化] 三連単的中率が低下（{trifecta_rate_new - trifecta_rate_old:+.2f}pt）")
    else:
        no_changes.append("[変化なし] 三連単的中率は同じ")

    # 1着的中率（変化しないはず）
    if abs(first_rate_new - first_rate_old) < 1.0:
        no_changes.append(f"[想定通り] 1着的中率は変化なし（{first_rate_new - first_rate_old:+.2f}pt）")
    else:
        no_changes.append(f"[注意] 1着的中率に変化（{first_rate_new - first_rate_old:+.2f}pt）")

    # 2着・3着的中率
    if len(df_1st_hit_old) > 0 and len(df_1st_hit_new) > 0:
        if second_rate_new > second_rate_old:
            improvements.append(f"[改善] 2着的中率が向上（{second_rate_new - second_rate_old:+.2f}pt）")
        elif second_rate_new < second_rate_old:
            no_changes.append(f"[要確認] 2着的中率が低下（{second_rate_new - second_rate_old:+.2f}pt）")

        if len(df_12_hit_old) > 0 and len(df_12_hit_new) > 0:
            if third_rate_new > third_rate_old:
                improvements.append(f"[改善] 3着的中率が向上（{third_rate_new - third_rate_old:+.2f}pt）")
            elif third_rate_new < third_rate_old:
                no_changes.append(f"[要確認] 3着的中率が低下（{third_rate_new - third_rate_old:+.2f}pt）")

    print()
    for item in improvements:
        print(f"  {item}")
    for item in no_changes:
        print(f"  {item}")

    # 最終判定
    print("\n" + "=" * 80)
    if len(improvements) > 0:
        print("【結論】 [OK] ハイブリッドスコアリングは効果的")
        print("=" * 80)
        print("\n2着・3着に三連対率を適用することで、")
        print("信頼度Bレースの三連単的中率が改善されています。")
    else:
        print("【結論】 [要検討] 効果が確認できない")
        print("=" * 80)
        print("\n現時点ではハイブリッドスコアリングの明確な効果が確認できません。")
        print("ただし、サンプル数が少ない可能性があります。")

    print()

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='ハイブリッドスコアリング効果比較')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--start', default='2025-01-01', help='検証開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-04-30', help='検証終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    compare_hybrid_effect(args.db, args.start, args.end)


if __name__ == '__main__':
    main()
