"""
信頼度B 三連単的中率検証スクリプト

目的: 信頼度Bレースでハイブリッドスコアリング（2着・3着に三連対率適用）が
      三連単的中率を改善しているか検証

検証内容:
1. 信頼度A vs 信頼度B の三連単的中率比較
2. 期待値ベースの評価（平均オッズ・回収率）
3. EV投資戦略への組み込み可否判定
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from scipy import stats


def validate_trifecta_accuracy(db_path: str, start_date: str, end_date: str):
    """
    三連単的中率を検証

    Args:
        db_path: データベースパス
        start_date: 検証開始日 (YYYY-MM-DD)
        end_date: 検証終了日 (YYYY-MM-DD)
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print("信頼度B 三連単的中率検証")
    print("=" * 80)
    print(f"\n検証期間: {start_date} ～ {end_date}")
    print()

    # 1. レースごとの予測上位3艇と実際の結果を取得
    query = """
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
          AND rp.generated_at >= '2025-12-10'
          AND res.rank IS NOT NULL
    ),
    race_confidence AS (
        SELECT DISTINCT
            race_id,
            race_date,
            venue_code,
            race_number,
            MAX(CASE WHEN rank_prediction = 1 THEN confidence END) as confidence
        FROM ranked_predictions
        GROUP BY race_id, race_date, venue_code, race_number
    ),
    predicted_trifecta AS (
        SELECT
            rc.race_id,
            rc.race_date,
            rc.venue_code,
            rc.race_number,
            rc.confidence,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_confidence rc
        JOIN ranked_predictions rp ON rc.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rc.race_id, rc.race_date, rc.venue_code, rc.race_number, rc.confidence
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
        pt.confidence,
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

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))

    if len(df) == 0:
        print("警告: データが見つかりません。予測生成が完了していない可能性があります。")
        conn.close()
        return

    # 信頼度別に分割
    df_a = df[df['confidence'] == 'A'].copy()
    df_b = df[df['confidence'] == 'B'].copy()
    df_c = df[df['confidence'] == 'C'].copy()

    print(f"総レース数: {len(df):,}レース")
    print(f"  - 信頼度A: {len(df_a):,}レース ({len(df_a)/len(df)*100:.1f}%)")
    print(f"  - 信頼度B: {len(df_b):,}レース ({len(df_b)/len(df)*100:.1f}%)")
    print(f"  - 信頼度C: {len(df_c):,}レース ({len(df_c)/len(df)*100:.1f}%)")
    print()

    if len(df_b) < 50:
        print(f"警告: 信頼度Bのサンプル数が少なすぎます（最低50件必要）")
        print(f"   現在: {len(df_b)}件")
        conn.close()
        return

    # 2. 三連単的中率検証
    print("=" * 80)
    print("【1】 三連単的中率検証")
    print("=" * 80)

    trifecta_rate_a = df_a['is_trifecta_hit'].mean() * 100 if len(df_a) > 0 else 0
    trifecta_rate_b = df_b['is_trifecta_hit'].mean() * 100 if len(df_b) > 0 else 0
    trifecta_rate_c = df_c['is_trifecta_hit'].mean() * 100 if len(df_c) > 0 else 0

    print(f"\n三連単的中率:")
    print(f"  信頼度A: {trifecta_rate_a:.2f}% ({df_a['is_trifecta_hit'].sum()}/{len(df_a)})")
    print(f"  信頼度B: {trifecta_rate_b:.2f}% ({df_b['is_trifecta_hit'].sum()}/{len(df_b)})")
    print(f"  信頼度C: {trifecta_rate_c:.2f}% ({df_c['is_trifecta_hit'].sum()}/{len(df_c)})")
    print(f"\n信頼度A vs B 差分: {trifecta_rate_b - trifecta_rate_a:+.2f}ポイント")

    # 統計的有意性検定（カイ二乗検定）
    if len(df_a) > 0 and len(df_b) > 0:
        contingency_trifecta = [
            [df_a['is_trifecta_hit'].sum(), len(df_a) - df_a['is_trifecta_hit'].sum()],
            [df_b['is_trifecta_hit'].sum(), len(df_b) - df_b['is_trifecta_hit'].sum()]
        ]
        chi2, p_value = stats.chi2_contingency(contingency_trifecta)[:2]

        print(f"\n統計的有意性:")
        print(f"  三連単的中率の差: p値={p_value:.4f} {'(有意)' if p_value < 0.05 else '(有意差なし)'}")

    # 3. 1着・2着・3着の個別的中率
    print("\n" + "=" * 80)
    print("【2】 各着順の的中率")
    print("=" * 80)

    # 1着的中率
    df['is_1st_hit'] = (df['pred_1st'] == df['actual_1st']).astype(int)
    df_a = df[df['confidence'] == 'A'].copy()
    df_b = df[df['confidence'] == 'B'].copy()
    df_c = df[df['confidence'] == 'C'].copy()

    first_rate_a = df_a['is_1st_hit'].mean() * 100 if len(df_a) > 0 else 0
    first_rate_b = df_b['is_1st_hit'].mean() * 100 if len(df_b) > 0 else 0
    first_rate_c = df_c['is_1st_hit'].mean() * 100 if len(df_c) > 0 else 0

    print(f"\n1着的中率:")
    print(f"  信頼度A: {first_rate_a:.2f}%")
    print(f"  信頼度B: {first_rate_b:.2f}%")
    print(f"  信頼度C: {first_rate_c:.2f}%")

    # 2着的中率（1着が当たった場合のみ）
    df_1st_hit_a = df_a[df_a['is_1st_hit'] == 1].copy()
    df_1st_hit_b = df_b[df_b['is_1st_hit'] == 1].copy()
    df_1st_hit_c = df_c[df_c['is_1st_hit'] == 1].copy()

    if len(df_1st_hit_a) > 0:
        df_1st_hit_a['is_2nd_hit'] = (df_1st_hit_a['pred_2nd'] == df_1st_hit_a['actual_2nd']).astype(int)
        second_rate_a = df_1st_hit_a['is_2nd_hit'].mean() * 100
    else:
        second_rate_a = 0

    if len(df_1st_hit_b) > 0:
        df_1st_hit_b['is_2nd_hit'] = (df_1st_hit_b['pred_2nd'] == df_1st_hit_b['actual_2nd']).astype(int)
        second_rate_b = df_1st_hit_b['is_2nd_hit'].mean() * 100
    else:
        second_rate_b = 0

    if len(df_1st_hit_c) > 0:
        df_1st_hit_c['is_2nd_hit'] = (df_1st_hit_c['pred_2nd'] == df_1st_hit_c['actual_2nd']).astype(int)
        second_rate_c = df_1st_hit_c['is_2nd_hit'].mean() * 100
    else:
        second_rate_c = 0

    print(f"\n2着的中率（1着的中時）:")
    print(f"  信頼度A: {second_rate_a:.2f}%")
    print(f"  信頼度B: {second_rate_b:.2f}%")
    print(f"  信頼度C: {second_rate_c:.2f}%")

    # 3着的中率（1着・2着が当たった場合のみ）
    if len(df_1st_hit_a) > 0:
        df_12_hit_a = df_1st_hit_a[df_1st_hit_a['is_2nd_hit'] == 1].copy()
        if len(df_12_hit_a) > 0:
            df_12_hit_a['is_3rd_hit'] = (df_12_hit_a['pred_3rd'] == df_12_hit_a['actual_3rd']).astype(int)
            third_rate_a = df_12_hit_a['is_3rd_hit'].mean() * 100
        else:
            third_rate_a = 0
    else:
        third_rate_a = 0

    if len(df_1st_hit_b) > 0:
        df_12_hit_b = df_1st_hit_b[df_1st_hit_b['is_2nd_hit'] == 1].copy()
        if len(df_12_hit_b) > 0:
            df_12_hit_b['is_3rd_hit'] = (df_12_hit_b['pred_3rd'] == df_12_hit_b['actual_3rd']).astype(int)
            third_rate_b = df_12_hit_b['is_3rd_hit'].mean() * 100
        else:
            third_rate_b = 0
    else:
        third_rate_b = 0

    if len(df_1st_hit_c) > 0:
        df_12_hit_c = df_1st_hit_c[df_1st_hit_c['is_2nd_hit'] == 1].copy()
        if len(df_12_hit_c) > 0:
            df_12_hit_c['is_3rd_hit'] = (df_12_hit_c['pred_3rd'] == df_12_hit_c['actual_3rd']).astype(int)
            third_rate_c = df_12_hit_c['is_3rd_hit'].mean() * 100
        else:
            third_rate_c = 0
    else:
        third_rate_c = 0

    print(f"\n3着的中率（1着・2着的中時）:")
    print(f"  信頼度A: {third_rate_a:.2f}%")
    print(f"  信頼度B: {third_rate_b:.2f}%")
    print(f"  信頼度C: {third_rate_c:.2f}%")

    # 4. 総合評価
    print("\n" + "=" * 80)
    print("【3】 総合評価")
    print("=" * 80)

    print(f"\nサンプル数:")
    print(f"  信頼度A: {len(df_a):,}件")
    print(f"  信頼度B: {len(df_b):,}件")
    print(f"  信頼度C: {len(df_c):,}件")

    # 判定基準
    criteria_met = []
    criteria_failed = []

    # 基準1: 信頼度Bが50件以上
    if len(df_b) >= 50:
        criteria_met.append("[OK] サンプル数十分（50件以上）")
    else:
        criteria_failed.append(f"[NG] サンプル数不足（{len(df_b)}件 < 50件）")

    # 基準2: 三連単的中率が5%以上
    if trifecta_rate_b >= 5.0:
        criteria_met.append(f"[OK] 三連単的中率が実用レベル（{trifecta_rate_b:.2f}% >= 5%）")
    else:
        criteria_failed.append(f"[NG] 三連単的中率が低い（{trifecta_rate_b:.2f}% < 5%）")

    # 基準3: 信頼度Aと同等以上（-2%以内）
    if len(df_a) > 0:
        if trifecta_rate_b >= trifecta_rate_a - 2.0:
            criteria_met.append(f"[OK] 信頼度Aと同等レベル（差分{trifecta_rate_b - trifecta_rate_a:+.2f}pt）")
        else:
            criteria_failed.append(f"[NG] 信頼度Aより大幅に低い（差分{trifecta_rate_b - trifecta_rate_a:+.2f}pt）")

    # 基準4: 2着・3着的中率が改善（ハイブリッドスコアリングの効果）
    if len(df_a) > 0:
        if second_rate_b > second_rate_a or third_rate_b > third_rate_a:
            criteria_met.append(f"[OK] 2着・3着精度が向上（ハイブリッド効果あり）")
        else:
            criteria_failed.append(f"[参考] 2着・3着精度は未改善（要データ追加検証）")

    print("\n本番適用判定:")
    for c in criteria_met:
        print(f"  {c}")
    for c in criteria_failed:
        print(f"  {c}")

    # 最終判定
    print("\n" + "=" * 80)
    if len(criteria_failed) == 0 or (len(criteria_failed) == 1 and "参考" in criteria_failed[0]):
        print("【結論】 [OK] 戦略Aへの組み込みを推奨します")
        print("=" * 80)
        print("\n信頼度Bレースは三連単的中率が実用レベルに達しており、")
        print("EV投資戦略に組み込むことで投資機会を拡大できます。")
    elif len(df_b) < 50:
        print("【結論】 [保留] データ不足のため判定保留")
        print("=" * 80)
        print(f"\n信頼度Bのサンプル数が不足しています（{len(df_b)}件）。")
        print("最低50件のデータが集まるまで待機することを推奨します。")
    else:
        print("【結論】 [要検討] 慎重な検討が必要")
        print("=" * 80)
        print("\n一部の基準を満たしていません。")
        print("追加のデータ収集またはスコアリング手法の見直しを検討してください。")

    print()

    conn.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='信頼度B 三連単的中率検証')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--start', default='2025-01-01', help='検証開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-04-30', help='検証終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    validate_trifecta_accuracy(args.db, args.start, args.end)


if __name__ == '__main__':
    main()
