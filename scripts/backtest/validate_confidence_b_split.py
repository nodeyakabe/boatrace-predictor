"""
信頼度B細分化検証スクリプト

目的: B+（70-74点）とB（65-69点）の性能差を検証

分析内容:
1. B+（70-74点）の三連単的中率
2. B（65-69点）の三連単的中率
3. 統計的有意差検定
4. 細分化の推奨可否判定

出力:
- テキストレポート（標準出力）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import sqlite3
import pandas as pd
import numpy as np
from scipy import stats


def validate_confidence_b_split(db_path: str, threshold: int = 70, start_date: str = '2025-01-01', end_date: str = '2025-12-31'):
    """
    信頼度B細分化検証

    Args:
        db_path: データベースパス
        threshold: 細分化閾値（デフォルト: 70点）
        start_date: 検証開始日
        end_date: 検証終了日
    """
    conn = sqlite3.connect(db_path)

    print("=" * 80)
    print(f"信頼度B細分化検証（閾値: {threshold}点）")
    print("=" * 80)
    print(f"\n検証期間: {start_date} ～ {end_date}")
    print(f"B+定義: {threshold}-74点")
    print(f"B定義: 65-{threshold-1}点")
    print()

    # データ取得（信頼度Bの1着予測艇のスコアを使用）
    query = """
    WITH ranked_predictions AS (
        SELECT
            rp.race_id,
            r.race_date,
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
    race_scores AS (
        SELECT
            race_id,
            race_date,
            MAX(CASE WHEN rank_prediction = 1 AND confidence = 'B' THEN total_score END) as max_score
        FROM ranked_predictions
        WHERE confidence = 'B' AND rank_prediction = 1
        GROUP BY race_id, race_date
        HAVING max_score IS NOT NULL
    ),
    predicted_trifecta AS (
        SELECT
            rs.race_id,
            rs.race_date,
            rs.max_score,
            MAX(CASE WHEN rp.rank_prediction = 1 THEN rp.pit_number END) as pred_1st,
            MAX(CASE WHEN rp.rank_prediction = 2 THEN rp.pit_number END) as pred_2nd,
            MAX(CASE WHEN rp.rank_prediction = 3 THEN rp.pit_number END) as pred_3rd
        FROM race_scores rs
        JOIN ranked_predictions rp ON rs.race_id = rp.race_id
        WHERE rp.rank_prediction <= 3
        GROUP BY rs.race_id, rs.race_date, rs.max_score
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
        pt.max_score,
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
    ORDER BY pt.race_date
    """

    df = pd.read_sql_query(query, conn, params=(start_date, end_date))
    conn.close()

    if len(df) == 0:
        print("警告: 信頼度Bのデータが見つかりません。")
        return

    # 細分化
    df['sub_confidence'] = df['max_score'].apply(lambda x: 'B+' if x >= threshold else 'B')

    df_bplus = df[df['sub_confidence'] == 'B+'].copy()
    df_b = df[df['sub_confidence'] == 'B'].copy()

    print(f"総レース数: {len(df):,}レース")
    print(f"  B+（{threshold}-74点）: {len(df_bplus):,}レース ({len(df_bplus)/len(df)*100:.1f}%)")
    print(f"  B（65-{threshold-1}点）: {len(df_b):,}レース ({len(df_b)/len(df)*100:.1f}%)")
    print()

    # 最小サンプル数チェック
    if len(df_bplus) < 30 or len(df_b) < 30:
        print("警告: サンプル数が少なすぎます（最低30件必要）")
        print(f"  B+: {len(df_bplus)}件")
        print(f"  B: {len(df_b)}件")
        print()
        print("判定: [保留] データ不足のため細分化検証は保留")
        return

    # 三連単的中率計算
    trifecta_rate_bplus = df_bplus['is_trifecta_hit'].mean() * 100
    trifecta_rate_b = df_b['is_trifecta_hit'].mean() * 100

    print("=" * 80)
    print("【1】 三連単的中率比較")
    print("=" * 80)
    print()
    print(f"B+（{threshold}-74点）: {trifecta_rate_bplus:.2f}% ({df_bplus['is_trifecta_hit'].sum()}/{len(df_bplus)})")
    print(f"B（65-{threshold-1}点）: {trifecta_rate_b:.2f}% ({df_b['is_trifecta_hit'].sum()}/{len(df_b)})")
    print(f"差分: {trifecta_rate_bplus - trifecta_rate_b:+.2f}ポイント")
    print()

    # 統計的有意性検定
    contingency_trifecta = [
        [df_bplus['is_trifecta_hit'].sum(), len(df_bplus) - df_bplus['is_trifecta_hit'].sum()],
        [df_b['is_trifecta_hit'].sum(), len(df_b) - df_b['is_trifecta_hit'].sum()]
    ]
    chi2, p_value = stats.chi2_contingency(contingency_trifecta)[:2]

    print("=" * 80)
    print("【2】 統計的有意性")
    print("=" * 80)
    print()
    print(f"カイ二乗値: {chi2:.4f}")
    print(f"p値: {p_value:.4f}")
    print(f"有意水準5%での判定: {'有意差あり' if p_value < 0.05 else '有意差なし'}")
    print()

    # スコア分布
    print("=" * 80)
    print("【3】 スコア分布")
    print("=" * 80)
    print()
    print(f"B+の平均スコア: {df_bplus['max_score'].mean():.2f}点")
    print(f"Bの平均スコア: {df_b['max_score'].mean():.2f}点")
    print()

    # 判定
    print("=" * 80)
    print("【4】 細分化推奨判定")
    print("=" * 80)
    print()

    criteria_met = []
    criteria_failed = []

    # 基準1: サンプル数
    if len(df_bplus) >= 50 and len(df_b) >= 50:
        criteria_met.append(f"[OK] サンプル数十分（B+: {len(df_bplus)}件、B: {len(df_b)}件）")
    else:
        criteria_failed.append(f"[NG] サンプル数不足（B+: {len(df_bplus)}件、B: {len(df_b)}件）")

    # 基準2: 的中率の差
    rate_diff = trifecta_rate_bplus - trifecta_rate_b
    if rate_diff >= 2.0:
        criteria_met.append(f"[OK] B+の的中率が有意に高い（+{rate_diff:.2f}pt）")
    elif rate_diff >= 1.0:
        criteria_met.append(f"[参考] B+の的中率がやや高い（+{rate_diff:.2f}pt）")
    else:
        criteria_failed.append(f"[NG] B+の的中率の優位性が小さい（+{rate_diff:.2f}pt）")

    # 基準3: 統計的有意性
    if p_value < 0.05:
        criteria_met.append(f"[OK] 統計的に有意な差あり（p={p_value:.4f}）")
    else:
        criteria_failed.append(f"[NG] 統計的に有意な差なし（p={p_value:.4f}）")

    # 結果表示
    for c in criteria_met:
        print(f"  {c}")
    for c in criteria_failed:
        print(f"  {c}")

    print()
    print("=" * 80)

    # 最終判定
    if len(criteria_failed) == 0:
        print("[推奨] 信頼度Bの細分化（B+ / B）を推奨します")
        print("=" * 80)
        print()
        print(f"B+（{threshold}-74点）は統計的に有意に的中率が高く、")
        print("信頼度を細分化することで、より精緻な投資判断が可能になります。")
    elif len(df_bplus) < 50 or len(df_b) < 50:
        print("[保留] データ不足のため判定保留")
        print("=" * 80)
        print()
        print("サンプル数が不足しています。")
        print("各50件以上のデータが集まるまで待機することを推奨します。")
    else:
        print("[非推奨] 現時点での細分化は推奨しません")
        print("=" * 80)
        print()
        print("B+とBの的中率に統計的に有意な差が確認できませんでした。")
        print("現在の信頼度B（65-74点）を統一的に扱うことを推奨します。")

    print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description='信頼度B細分化検証')
    parser.add_argument('--db', default='data/boatrace.db', help='データベースパス')
    parser.add_argument('--threshold', type=int, default=70, help='細分化閾値（デフォルト: 70点）')
    parser.add_argument('--start', default='2025-01-01', help='検証開始日 (YYYY-MM-DD)')
    parser.add_argument('--end', default='2025-12-31', help='検証終了日 (YYYY-MM-DD)')

    args = parser.parse_args()

    try:
        validate_confidence_b_split(args.db, args.threshold, args.start, args.end)
        print()
        print("=" * 80)
        print("[OK] 信頼度B細分化検証が正常に完了しました")
        print("=" * 80)
    except Exception as e:
        print()
        print("=" * 80)
        print("[ERROR] 信頼度B細分化検証でエラーが発生しました")
        print("=" * 80)
        print(f"\nエラー内容: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
