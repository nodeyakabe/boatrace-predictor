"""
全信頼度レベルの比較分析スクリプト

信頼度A/B/C/D/Eそれぞれの的中率、ROI、スコア分布を比較
信頼度Bの6.75%が妥当かどうかを検証
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def load_all_predictions_data():
    """2024年・2025年の全信頼度データを抽出"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 2024-2025年の全レースを取得
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
        venue_code = race['venue_code']
        race_date = race['race_date']
        race_number = race['race_number']

        # 予測情報を取得（全信頼度）
        cursor.execute('''
            SELECT pit_number, confidence, total_score, course_score, racer_score,
                   motor_score, kimarite_score, grade_score, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 3:
            continue

        confidence = preds[0]['confidence']

        # 信頼度がNULLまたは空の場合はスキップ
        if not confidence:
            continue

        predicted_rank_1 = preds[0]['pit_number']
        predicted_rank_2 = preds[1]['pit_number']
        predicted_rank_3 = preds[2]['pit_number']
        total_score = preds[0]['total_score']

        # 各スコアの合計（全6艇分）
        total_course_score = sum([p['course_score'] or 0 for p in preds])
        total_racer_score = sum([p['racer_score'] or 0 for p in preds])
        total_motor_score = sum([p['motor_score'] or 0 for p in preds])

        pred_combo = f"{predicted_rank_1}-{predicted_rank_2}-{predicted_rank_3}"

        # オッズを取得
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, pred_combo))
        odds_row = cursor.fetchone()
        predicted_odds = odds_row['odds'] if odds_row else None

        # トップ予想艇の級別を取得
        cursor.execute('''
            SELECT racer_rank FROM entries
            WHERE race_id = ? AND pit_number = ?
        ''', (race_id, predicted_rank_1))
        top_entry = cursor.fetchone()
        top_racer_class = top_entry['racer_rank'] if top_entry else None

        # レース結果を取得
        cursor.execute('''
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            rank_1 = results[0]['pit_number']
            rank_2 = results[1]['pit_number']
            rank_3 = results[2]['pit_number']
            actual_combo = f"{rank_1}-{rank_2}-{rank_3}"

            # 的中判定（三連単）
            hit_trifecta = (pred_combo == actual_combo)

            # 1位的中判定
            hit_rank1 = (predicted_rank_1 == rank_1)

            # 1-3位に入っているか
            top3_actual = [rank_1, rank_2, rank_3]
            predicted_in_top3 = (
                predicted_rank_1 in top3_actual and
                predicted_rank_2 in top3_actual and
                predicted_rank_3 in top3_actual
            )

            # 払戻金を取得
            cursor.execute('''
                SELECT amount FROM payouts
                WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
            ''', (race_id, actual_combo))
            payout_row = cursor.fetchone()
            trifecta_payout = payout_row['amount'] if payout_row else None
        else:
            rank_1 = None
            rank_2 = None
            rank_3 = None
            hit_trifecta = False
            hit_rank1 = False
            predicted_in_top3 = False
            trifecta_payout = None

        # データを追加
        data_list.append({
            'race_date': race_date,
            'venue_code': venue_code,
            'race_number': race_number,
            'confidence': confidence,
            'predicted_rank_1': predicted_rank_1,
            'predicted_rank_2': predicted_rank_2,
            'predicted_rank_3': predicted_rank_3,
            'predicted_odds': predicted_odds,
            'total_score': total_score,
            'total_course_score': total_course_score,
            'total_racer_score': total_racer_score,
            'total_motor_score': total_motor_score,
            'top_racer_class': top_racer_class,
            'rank_1': rank_1,
            'rank_2': rank_2,
            'rank_3': rank_3,
            'hit_trifecta': hit_trifecta,
            'hit_rank1': hit_rank1,
            'predicted_in_top3': predicted_in_top3,
            'trifecta_payout': trifecta_payout
        })

    conn.close()

    df = pd.DataFrame(data_list)
    return df

def analyze_by_confidence(df):
    """信頼度別の基本統計"""
    print("=" * 80)
    print("【信頼度別 基本統計】")
    print("=" * 80)

    # 信頼度別にグループ化
    grouped = df.groupby('confidence')

    results = []
    for confidence, group in grouped:
        count = len(group)
        hit_trifecta = group['hit_trifecta'].sum()
        hit_rank1 = group['hit_rank1'].sum()
        hit_top3 = group['predicted_in_top3'].sum()

        hit_rate_trifecta = (hit_trifecta / count * 100) if count > 0 else 0
        hit_rate_rank1 = (hit_rank1 / count * 100) if count > 0 else 0
        hit_rate_top3 = (hit_top3 / count * 100) if count > 0 else 0

        # 払戻金計算
        hit_group = group[group['hit_trifecta'] == True]
        bet_amount = 300
        total_bet = count * bet_amount
        total_return = (hit_group['trifecta_payout'] * bet_amount / 100).sum() if len(hit_group) > 0 else 0
        profit = total_return - total_bet
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        # スコアの平均
        avg_total_score = group['total_score'].mean()
        avg_odds = group['predicted_odds'].mean()

        results.append({
            '信頼度': confidence,
            'レース数': count,
            '三連単的中数': hit_trifecta,
            '三連単的中率%': round(hit_rate_trifecta, 2),
            '1位的中数': hit_rank1,
            '1位的中率%': round(hit_rate_rank1, 2),
            'Top3的中数': hit_top3,
            'Top3的中率%': round(hit_rate_top3, 2),
            '平均スコア': round(avg_total_score, 1),
            '平均オッズ': round(avg_odds, 1),
            '総購入額': total_bet,
            '総払戻額': int(total_return),
            '収支': int(profit),
            'ROI%': round(roi, 1)
        })

    summary = pd.DataFrame(results)
    summary = summary.sort_values('信頼度')

    print("\n" + summary.to_string(index=False))

    return summary

def analyze_score_distribution(df):
    """信頼度別のスコア分布"""
    print("\n" + "=" * 80)
    print("【信頼度別 スコア分布】")
    print("=" * 80)

    for confidence in sorted(df['confidence'].unique()):
        group = df[df['confidence'] == confidence]

        print(f"\n■ 信頼度{confidence} (n={len(group)})")
        print(f"total_score: min={group['total_score'].min():.1f}, "
              f"25%={group['total_score'].quantile(0.25):.1f}, "
              f"50%={group['total_score'].quantile(0.50):.1f}, "
              f"75%={group['total_score'].quantile(0.75):.1f}, "
              f"max={group['total_score'].max():.1f}")

def analyze_yearly_trend(df):
    """年別・信頼度別の推移"""
    print("\n" + "=" * 80)
    print("【年別・信頼度別 推移】")
    print("=" * 80)

    df['year'] = pd.to_datetime(df['race_date']).dt.year

    # 年別・信頼度別の集計
    grouped = df.groupby(['year', 'confidence'])

    results = []
    for (year, confidence), group in grouped:
        count = len(group)
        hit_trifecta = group['hit_trifecta'].sum()
        hit_rate_trifecta = (hit_trifecta / count * 100) if count > 0 else 0

        results.append({
            '年': year,
            '信頼度': confidence,
            'レース数': count,
            '三連単的中数': hit_trifecta,
            '三連単的中率%': round(hit_rate_trifecta, 2)
        })

    yearly = pd.DataFrame(results)
    yearly = yearly.sort_values(['信頼度', '年'])

    print("\n" + yearly.to_string(index=False))

def analyze_confidence_b_detail(df):
    """信頼度Bの詳細分析"""
    print("\n" + "=" * 80)
    print("【信頼度B 詳細分析】")
    print("=" * 80)

    df_b = df[df['confidence'] == 'B']

    print(f"\n総レース数: {len(df_b)}")
    print(f"三連単的中数: {df_b['hit_trifecta'].sum()}")
    print(f"三連単的中率: {(df_b['hit_trifecta'].sum() / len(df_b) * 100):.2f}%")
    print(f"1位的中数: {df_b['hit_rank1'].sum()}")
    print(f"1位的中率: {(df_b['hit_rank1'].sum() / len(df_b) * 100):.2f}%")
    print(f"Top3的中数: {df_b['predicted_in_top3'].sum()}")
    print(f"Top3的中率: {(df_b['predicted_in_top3'].sum() / len(df_b) * 100):.2f}%")

    # 1位が外れた場合の実際の順位
    print("\n【1位予想が外れた場合の実際の順位】")
    df_b_miss = df_b[df_b['hit_rank1'] == False]

    # 1位予想艇の実際の順位を取得（簡易版）
    rank1_actual_dist = []
    for _, row in df_b_miss.iterrows():
        pred1 = row['predicted_rank_1']
        actual = [row['rank_1'], row['rank_2'], row['rank_3']]
        if pred1 in actual:
            rank1_actual_dist.append(actual.index(pred1) + 1)
        else:
            rank1_actual_dist.append(4)  # 4位以下

    rank_counts = pd.Series(rank1_actual_dist).value_counts().sort_index()
    print(f"1位予想が外れたレース: {len(df_b_miss)}")
    print("実際の順位分布:")
    for rank, count in rank_counts.items():
        pct = count / len(df_b_miss) * 100
        rank_label = f"{rank}位" if rank <= 3 else "4位以下"
        print(f"  {rank_label}: {count}回 ({pct:.1f}%)")

def compare_with_random(df):
    """ランダム予想との比較"""
    print("\n" + "=" * 80)
    print("【ランダム予想との比較】")
    print("=" * 80)

    # 理論的な確率
    # 三連単: 6P3 = 120通り → 1/120 = 0.833%
    # 1位: 1/6 = 16.67%
    # Top3全て的中: 3/6 * 2/5 * 1/4 = 0.05 = 5.0%

    random_trifecta = 1 / 120 * 100  # 0.833%
    random_rank1 = 1 / 6 * 100  # 16.67%
    random_top3_all = 3/6 * 2/5 * 1/4 * 100  # 5.0%

    print(f"\n理論値（完全ランダム）:")
    print(f"  三連単的中率: {random_trifecta:.2f}%")
    print(f"  1位的中率: {random_rank1:.2f}%")
    print(f"  予想3艇全てTop3的中率: {random_top3_all:.2f}%")

    print(f"\n各信頼度との比較:")

    for confidence in sorted(df['confidence'].unique()):
        group = df[df['confidence'] == confidence]
        count = len(group)

        trifecta_rate = group['hit_trifecta'].sum() / count * 100
        rank1_rate = group['hit_rank1'].sum() / count * 100
        top3_rate = group['predicted_in_top3'].sum() / count * 100

        trifecta_ratio = trifecta_rate / random_trifecta
        rank1_ratio = rank1_rate / random_rank1
        top3_ratio = top3_rate / random_top3_all

        print(f"\n  信頼度{confidence}:")
        print(f"    三連単: {trifecta_rate:.2f}% (ランダムの{trifecta_ratio:.1f}倍)")
        print(f"    1位: {rank1_rate:.2f}% (ランダムの{rank1_ratio:.1f}倍)")
        print(f"    Top3全て: {top3_rate:.2f}% (ランダムの{top3_ratio:.1f}倍)")

def main():
    """メイン処理"""
    print("全信頼度レベル比較分析を開始します...")
    print(f"データベース: {DB_PATH}")

    # データ読み込み
    print("\nデータ読み込み中...")
    df = load_all_predictions_data()

    if len(df) == 0:
        print("ERROR: データが見つかりません")
        return

    print(f"{len(df)} 件のレースを取得しました")
    print(f"信頼度の種類: {sorted(df['confidence'].unique())}")

    # 分析実行
    summary = analyze_by_confidence(df)
    analyze_score_distribution(df)
    analyze_yearly_trend(df)
    analyze_confidence_b_detail(df)
    compare_with_random(df)

    # 結果をCSVに保存
    output_path = Path(__file__).parent.parent / "results" / f"all_confidence_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n分析結果を保存しました: {output_path}")

    # サマリーも保存
    summary_path = Path(__file__).parent.parent / "results" / f"all_confidence_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    summary.to_csv(summary_path, index=False, encoding='utf-8-sig')
    print(f"サマリーを保存しました: {summary_path}")

if __name__ == "__main__":
    main()
