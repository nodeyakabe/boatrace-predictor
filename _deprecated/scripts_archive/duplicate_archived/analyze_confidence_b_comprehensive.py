"""
信頼度B予想の包括的詳細分析

1. スコアリング精度
   - 的中/不的中問わず、上位スコア艇で決着しているか
   - スコア下位艇が3連単に絡む確率
   - 買い目にスコア下位艇を含んでいるか

2. 不的中レースの特徴
   - 払戻金（荒れたレースか）
   - 1号艇の成績
   - スコア1位艇の実際の着順

3. その他の分析
   - スコア分布と的中率の関係
   - 的中時と不的中時のスコア差
   - 予想外の艇が上位に来た場合の傾向
"""
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"


def load_confidence_b_data():
    """信頼度Bデータを取得"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2024-01-01' AND r.race_date < '2026-01-01'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    data_list = []

    for race in races:
        race_id = race['race_id']

        # 予測情報（信頼度B）
        cursor.execute('''
            SELECT pit_number, confidence, total_score, rank_prediction,
                   course_score, racer_score, motor_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        if confidence != 'B':
            continue

        # 予想上位3艇
        predicted_pits = [preds[0]['pit_number'], preds[1]['pit_number'], preds[2]['pit_number']]
        predicted_combo = f"{predicted_pits[0]}-{predicted_pits[1]}-{predicted_pits[2]}"

        # 全6艇のスコア情報
        score_info = {}
        for p in preds:
            score_info[p['pit_number']] = {
                'total_score': p['total_score'] or 0,
                'rank_prediction': p['rank_prediction'],
                'course_score': p['course_score'] or 0,
                'racer_score': p['racer_score'] or 0,
                'motor_score': p['motor_score'] or 0
            }

        # スコア順位
        score_ranking = sorted(score_info.items(), key=lambda x: x[1]['total_score'], reverse=True)
        score_rank_map = {pit: rank+1 for rank, (pit, _) in enumerate(score_ranking)}

        # 実際の結果
        cursor.execute('''
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        actual_pits = [results[0]['pit_number'], results[1]['pit_number'], results[2]['pit_number']]
        actual_combo = f"{actual_pits[0]}-{actual_pits[1]}-{actual_pits[2]}"

        # 三連単オッズ
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, actual_combo))
        odds_row = cursor.fetchone()
        actual_odds = odds_row['odds'] if odds_row else None

        # 予想オッズ
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, predicted_combo))
        pred_odds_row = cursor.fetchone()
        predicted_odds = pred_odds_row['odds'] if pred_odds_row else None

        # 的中判定
        is_hit = (predicted_combo == actual_combo)

        # 実際の上位3艇のスコア順位
        actual_score_ranks = [score_rank_map.get(pit, 7) for pit in actual_pits]

        # スコア下位艇（4-6位）が3連単に絡んだか
        low_score_pits = [pit for pit, rank in score_rank_map.items() if rank >= 4]
        low_score_in_result = len(set(low_score_pits) & set(actual_pits))

        # 予想にスコア下位艇を含んでいるか
        low_score_in_prediction = len(set(low_score_pits) & set(predicted_pits))

        # 1号艇の情報
        pit1_score_rank = score_rank_map.get(1, 7)
        pit1_actual_rank = next((i+1 for i, pit in enumerate(actual_pits) if pit == 1), None)
        if pit1_actual_rank is None:
            pit1_actual_rank = 99  # 3着圏外

        # スコア1位艇の実際の順位
        top_score_pit = score_ranking[0][0]
        top_score_actual_rank = next((i+1 for i, pit in enumerate(actual_pits) if pit == top_score_pit), None)
        if top_score_actual_rank is None:
            top_score_actual_rank = 99  # 3着圏外

        # スコア差（1位と6位の差）
        score_gap = score_ranking[0][1]['total_score'] - score_ranking[-1][1]['total_score']

        # スコア差（予想1位と予想4位の差）
        pred1_score = score_info[predicted_pits[0]]['total_score']
        pred4_pit = [pit for pit, info in score_info.items() if info['rank_prediction'] == 4][0]
        pred4_score = score_info[pred4_pit]['total_score']
        pred_score_gap = pred1_score - pred4_score

        data_list.append({
            'race_id': race_id,
            'race_date': race['race_date'],
            'venue_code': race['venue_code'],
            'race_number': race['race_number'],
            'predicted_combo': predicted_combo,
            'actual_combo': actual_combo,
            'is_hit': is_hit,
            'actual_odds': actual_odds,
            'predicted_odds': predicted_odds,
            'actual_rank1_score_rank': actual_score_ranks[0],
            'actual_rank2_score_rank': actual_score_ranks[1],
            'actual_rank3_score_rank': actual_score_ranks[2],
            'low_score_in_result': low_score_in_result,
            'low_score_in_prediction': low_score_in_prediction,
            'pit1_score_rank': pit1_score_rank,
            'pit1_actual_rank': pit1_actual_rank,
            'top_score_pit': top_score_pit,
            'top_score_actual_rank': top_score_actual_rank,
            'score_gap': score_gap,
            'pred_score_gap': pred_score_gap
        })

    conn.close()
    return pd.DataFrame(data_list)


def analyze_scoring_accuracy(df):
    """スコアリング精度を分析"""
    print("="*80)
    print("1. スコアリング精度分析")
    print("="*80)

    total = len(df)

    # 実際の1-3位のスコア順位分布
    print("\n【実際の着順艇のスコア順位】")
    print("\n1位艇のスコア順位:")
    for rank in range(1, 7):
        count = (df['actual_rank1_score_rank'] == rank).sum()
        pct = count / total * 100
        print(f"  スコア{rank}位: {count:3d}レース ({pct:5.1f}%)")

    print("\n2位艇のスコア順位:")
    for rank in range(1, 7):
        count = (df['actual_rank2_score_rank'] == rank).sum()
        pct = count / total * 100
        print(f"  スコア{rank}位: {count:3d}レース ({pct:5.1f}%)")

    print("\n3位艇のスコア順位:")
    for rank in range(1, 7):
        count = (df['actual_rank3_score_rank'] == rank).sum()
        pct = count / total * 100
        print(f"  スコア{rank}位: {count:3d}レース ({pct:5.1f}%)")

    # スコア上位3艇で決着した割合
    top3_score_races = df[
        (df['actual_rank1_score_rank'] <= 3) &
        (df['actual_rank2_score_rank'] <= 3) &
        (df['actual_rank3_score_rank'] <= 3)
    ]
    print(f"\nスコア上位3艇で決着: {len(top3_score_races)}/{total} ({len(top3_score_races)/total*100:.1f}%)")

    # スコア下位艇（4-6位）が3連単に絡む確率
    print(f"\n【スコア下位艇（4-6位）の影響】")
    print(f"\n3連単にスコア下位艇が含まれる:")
    for count in range(4):
        races = df[df['low_score_in_result'] == count]
        pct = len(races) / total * 100
        print(f"  {count}艇: {len(races):3d}レース ({pct:5.1f}%)")

    # 予想にスコア下位艇を含んでいるか
    print(f"\n予想にスコア下位艇を含む:")
    for count in range(4):
        races = df[df['low_score_in_prediction'] == count]
        pct = len(races) / total * 100
        if count == 0:
            print(f"  {count}艇（スコア上位3艇のみ）: {len(races):3d}レース ({pct:5.1f}%)")
        else:
            print(f"  {count}艇: {len(races):3d}レース ({pct:5.1f}%)")


def analyze_miss_characteristics(df):
    """不的中レースの特徴を分析"""
    print("\n" + "="*80)
    print("2. 不的中レースの特徴分析")
    print("="*80)

    hit_df = df[df['is_hit'] == True]
    miss_df = df[df['is_hit'] == False]

    print(f"\n的中レース: {len(hit_df)}レース")
    print(f"不的中レース: {len(miss_df)}レース")
    print(f"的中率: {len(hit_df)/len(df)*100:.2f}%")

    # 払戻金の比較
    print(f"\n【払戻金（オッズ）の比較】")

    hit_odds = hit_df['actual_odds'].dropna()
    miss_odds = miss_df['actual_odds'].dropna()

    print(f"\n的中時の実際のオッズ:")
    print(f"  平均: {hit_odds.mean():.2f}倍")
    print(f"  中央値: {hit_odds.median():.2f}倍")

    print(f"\n不的中時の実際のオッズ:")
    print(f"  平均: {miss_odds.mean():.2f}倍")
    print(f"  中央値: {miss_odds.median():.2f}倍")

    print(f"\n不的中時のオッズ分布:")
    print(f"  10倍未満: {(miss_odds < 10).sum():3d}レース ({(miss_odds < 10).sum()/len(miss_odds)*100:5.1f}%)")
    print(f"  10-30倍: {((miss_odds >= 10) & (miss_odds < 30)).sum():3d}レース ({((miss_odds >= 10) & (miss_odds < 30)).sum()/len(miss_odds)*100:5.1f}%)")
    print(f"  30-100倍: {((miss_odds >= 30) & (miss_odds < 100)).sum():3d}レース ({((miss_odds >= 30) & (miss_odds < 100)).sum()/len(miss_odds)*100:5.1f}%)")
    print(f"  100倍以上: {(miss_odds >= 100).sum():3d}レース ({(miss_odds >= 100).sum()/len(miss_odds)*100:5.1f}%)")

    # 予想オッズの比較
    print(f"\n【予想オッズの比較】")
    hit_pred_odds = hit_df['predicted_odds'].dropna()
    miss_pred_odds = miss_df['predicted_odds'].dropna()

    print(f"\n的中時の予想オッズ: {hit_pred_odds.mean():.2f}倍（平均）")
    print(f"不的中時の予想オッズ: {miss_pred_odds.mean():.2f}倍（平均）")

    # 1号艇の傾向
    print(f"\n【1号艇の傾向】")
    print(f"\n的中時の1号艇実着順:")
    for rank in range(1, 4):
        count = (hit_df['pit1_actual_rank'] == rank).sum()
        pct = count / len(hit_df) * 100 if len(hit_df) > 0 else 0
        print(f"  {rank}着: {count:3d}レース ({pct:5.1f}%)")

    print(f"\n不的中時の1号艇実着順:")
    for rank in range(1, 4):
        count = (miss_df['pit1_actual_rank'] == rank).sum()
        pct = count / len(miss_df) * 100 if len(miss_df) > 0 else 0
        print(f"  {rank}着: {count:3d}レース ({pct:5.1f}%)")
    count_out = (miss_df['pit1_actual_rank'] == 99).sum()
    pct_out = count_out / len(miss_df) * 100 if len(miss_df) > 0 else 0
    print(f"  3着圏外: {count_out:3d}レース ({pct_out:5.1f}%)")

    # スコア1位艇の実際の順位
    print(f"\n【スコア1位艇の実際の着順】")
    print(f"\n的中時:")
    for rank in range(1, 4):
        count = (hit_df['top_score_actual_rank'] == rank).sum()
        pct = count / len(hit_df) * 100 if len(hit_df) > 0 else 0
        print(f"  {rank}着: {count:3d}レース ({pct:5.1f}%)")

    print(f"\n不的中時:")
    for rank in range(1, 4):
        count = (miss_df['top_score_actual_rank'] == rank).sum()
        pct = count / len(miss_df) * 100 if len(miss_df) > 0 else 0
        print(f"  {rank}着: {count:3d}レース ({pct:5.1f}%)")
    count_out = (miss_df['top_score_actual_rank'] == 99).sum()
    pct_out = count_out / len(miss_df) * 100 if len(miss_df) > 0 else 0
    print(f"  3着圏外: {count_out:3d}レース ({pct_out:5.1f}%)")


def analyze_score_distribution(df):
    """スコア分布と的中率の関係"""
    print("\n" + "="*80)
    print("3. スコア分布と的中率の関係")
    print("="*80)

    # スコア差と的中率
    print(f"\n【スコア1位と6位の差】")
    print(f"全体平均スコア差: {df['score_gap'].mean():.2f}")
    print(f"的中時の平均スコア差: {df[df['is_hit']]['score_gap'].mean():.2f}")
    print(f"不的中時の平均スコア差: {df[~df['is_hit']]['score_gap'].mean():.2f}")

    # スコア差で分類
    df['score_gap_category'] = pd.cut(df['score_gap'],
                                       bins=[0, 50, 100, 150, 1000],
                                       labels=['小(0-50)', '中(50-100)', '大(100-150)', '特大(150+)'])

    print(f"\nスコア差別の的中率:")
    for cat in ['小(0-50)', '中(50-100)', '大(100-150)', '特大(150+)']:
        cat_df = df[df['score_gap_category'] == cat]
        if len(cat_df) > 0:
            hit_rate = (cat_df['is_hit']).sum() / len(cat_df) * 100
            print(f"  {cat}: {(cat_df['is_hit']).sum()}/{len(cat_df)} ({hit_rate:.1f}%)")

    # 予想1位と4位のスコア差
    print(f"\n【予想1位と4位のスコア差】")
    print(f"全体平均: {df['pred_score_gap'].mean():.2f}")
    print(f"的中時の平均: {df[df['is_hit']]['pred_score_gap'].mean():.2f}")
    print(f"不的中時の平均: {df[~df['is_hit']]['pred_score_gap'].mean():.2f}")


def analyze_upset_patterns(df):
    """波乱パターンの分析"""
    print("\n" + "="*80)
    print("4. 波乱パターンの分析")
    print("="*80)

    # スコア下位艇が上位に来たパターン
    low_score_upset = df[df['low_score_in_result'] >= 1]
    print(f"\nスコア下位艇（4-6位）が3連単に絡んだレース: {len(low_score_upset)}/{len(df)} ({len(low_score_upset)/len(df)*100:.1f}%)")
    print(f"  的中率: {(low_score_upset['is_hit']).sum()}/{len(low_score_upset)} ({(low_score_upset['is_hit']).sum()/len(low_score_upset)*100:.1f}%)")
    if len(low_score_upset) > 0:
        print(f"  平均オッズ: {low_score_upset['actual_odds'].mean():.2f}倍")

    # スコア上位3艇で決着したレース
    top3_score = df[df['low_score_in_result'] == 0]
    print(f"\nスコア上位3艇で決着したレース: {len(top3_score)}/{len(df)} ({len(top3_score)/len(df)*100:.1f}%)")
    print(f"  的中率: {(top3_score['is_hit']).sum()}/{len(top3_score)} ({(top3_score['is_hit']).sum()/len(top3_score)*100:.1f}%)")
    if len(top3_score) > 0:
        print(f"  平均オッズ: {top3_score['actual_odds'].mean():.2f}倍")


def main():
    print("="*80)
    print("信頼度B予想の包括的詳細分析")
    print("="*80)

    # データ読み込み
    df = load_confidence_b_data()
    print(f"\n対象レース数: {len(df):,}レース\n")

    if len(df) == 0:
        print("信頼度Bのデータがありません")
        return

    # 各種分析
    analyze_scoring_accuracy(df)
    analyze_miss_characteristics(df)
    analyze_score_distribution(df)
    analyze_upset_patterns(df)

    # CSVに保存
    output_dir = Path(__file__).parent.parent / "results"
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    csv_path = output_dir / f"confidence_b_comprehensive_{timestamp}.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n詳細データ保存: {csv_path.relative_to(Path(__file__).parent.parent)}")

    print("\n" + "="*80)
    print("分析完了")
    print("="*80)


if __name__ == "__main__":
    main()
