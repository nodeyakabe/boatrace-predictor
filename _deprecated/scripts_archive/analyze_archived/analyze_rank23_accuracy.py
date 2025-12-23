"""
2位・3位予想精度の詳細分析スクリプト

問題: 1位的中率65.86%に対して、三連単的中率6.75%と大きく落ちる
原因: 2位・3位の予想精度が低い可能性
目的: 2位・3位の予想精度を詳しく分析し、改善点を見つける
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def load_predictions_with_results():
    """予想と結果を詳細に取得"""
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

        # 予測情報を取得
        cursor.execute('''
            SELECT pit_number, confidence, total_score, rank_prediction
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'advance'
            ORDER BY rank_prediction
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']
        if not confidence:
            continue

        # 予想1-6位
        pred_1 = preds[0]['pit_number']
        pred_2 = preds[1]['pit_number']
        pred_3 = preds[2]['pit_number']
        pred_4 = preds[3]['pit_number']
        pred_5 = preds[4]['pit_number']
        pred_6 = preds[5]['pit_number']

        # 各艇のスコア
        scores = {p['pit_number']: p['total_score'] for p in preds}

        # レース結果を取得
        cursor.execute('''
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 6:
            continue

        # 実際の1-6位
        actual_1 = results[0]['pit_number']
        actual_2 = results[1]['pit_number']
        actual_3 = results[2]['pit_number']
        actual_4 = results[3]['pit_number'] if len(results) > 3 else None
        actual_5 = results[4]['pit_number'] if len(results) > 4 else None
        actual_6 = results[5]['pit_number'] if len(results) > 5 else None

        # 的中判定
        hit_1 = (pred_1 == actual_1)
        hit_2 = (pred_2 == actual_2)
        hit_3 = (pred_3 == actual_3)
        hit_trifecta = (hit_1 and hit_2 and hit_3)

        # 1位が的中した場合の2位・3位
        if hit_1:
            hit_2_given_1 = hit_2
            hit_3_given_1 = hit_3
            hit_23_given_1 = (hit_2 and hit_3)
        else:
            hit_2_given_1 = None
            hit_3_given_1 = None
            hit_23_given_1 = None

        # 予想2位の実際の順位
        pred_2_actual_rank = None
        for i, res in enumerate(results[:6], 1):
            if res['pit_number'] == pred_2:
                pred_2_actual_rank = i
                break

        # 予想3位の実際の順位
        pred_3_actual_rank = None
        for i, res in enumerate(results[:6], 1):
            if res['pit_number'] == pred_3:
                pred_3_actual_rank = i
                break

        # 実際の2位を予想で何位にしていたか
        actual_2_pred_rank = None
        pred_list = [pred_1, pred_2, pred_3, pred_4, pred_5, pred_6]
        if actual_2 in pred_list:
            actual_2_pred_rank = pred_list.index(actual_2) + 1

        # 実際の3位を予想で何位にしていたか
        actual_3_pred_rank = None
        if actual_3 in pred_list:
            actual_3_pred_rank = pred_list.index(actual_3) + 1

        # スコア差分（1位と2位のスコア差）
        score_diff_1_2 = scores.get(pred_1, 0) - scores.get(pred_2, 0)
        score_diff_2_3 = scores.get(pred_2, 0) - scores.get(pred_3, 0)

        data_list.append({
            'race_date': race['race_date'],
            'venue_code': race['venue_code'],
            'race_number': race['race_number'],
            'confidence': confidence,
            'pred_1': pred_1,
            'pred_2': pred_2,
            'pred_3': pred_3,
            'actual_1': actual_1,
            'actual_2': actual_2,
            'actual_3': actual_3,
            'hit_1': hit_1,
            'hit_2': hit_2,
            'hit_3': hit_3,
            'hit_trifecta': hit_trifecta,
            'hit_2_given_1': hit_2_given_1,
            'hit_3_given_1': hit_3_given_1,
            'hit_23_given_1': hit_23_given_1,
            'pred_2_actual_rank': pred_2_actual_rank,
            'pred_3_actual_rank': pred_3_actual_rank,
            'actual_2_pred_rank': actual_2_pred_rank,
            'actual_3_pred_rank': actual_3_pred_rank,
            'score_diff_1_2': score_diff_1_2,
            'score_diff_2_3': score_diff_2_3,
            'score_1': scores.get(pred_1, 0),
            'score_2': scores.get(pred_2, 0),
            'score_3': scores.get(pred_3, 0),
        })

    conn.close()

    df = pd.DataFrame(data_list)
    return df

def analyze_rank_accuracy(df):
    """各順位の予想精度を分析"""
    print("=" * 80)
    print("【各順位の予想精度】")
    print("=" * 80)

    for confidence in sorted(df['confidence'].unique()):
        conf_df = df[df['confidence'] == confidence]
        count = len(conf_df)

        hit_1 = conf_df['hit_1'].sum()
        hit_2 = conf_df['hit_2'].sum()
        hit_3 = conf_df['hit_3'].sum()

        rate_1 = (hit_1 / count * 100) if count > 0 else 0
        rate_2 = (hit_2 / count * 100) if count > 0 else 0
        rate_3 = (hit_3 / count * 100) if count > 0 else 0

        print(f"\n信頼度{confidence} (n={count})")
        print(f"  1位的中率: {rate_1:.2f}% ({hit_1}/{count})")
        print(f"  2位的中率: {rate_2:.2f}% ({hit_2}/{count})")
        print(f"  3位的中率: {rate_3:.2f}% ({hit_3}/{count})")

        # 理論値との比較
        random_rate = 1/6 * 100  # 16.67%
        print(f"  1位: ランダムの{rate_1/random_rate:.1f}倍")
        print(f"  2位: ランダムの{rate_2/random_rate:.1f}倍")
        print(f"  3位: ランダムの{rate_3/random_rate:.1f}倍")

def analyze_conditional_accuracy(df):
    """条件付き精度（1位的中時の2位・3位精度）"""
    print("\n" + "=" * 80)
    print("【1位的中時の2位・3位の精度】")
    print("=" * 80)

    for confidence in sorted(df['confidence'].unique()):
        conf_df = df[df['confidence'] == confidence]

        # 1位が的中したレースのみ
        hit1_df = conf_df[conf_df['hit_1'] == True]
        count_hit1 = len(hit1_df)

        if count_hit1 == 0:
            continue

        hit_2_given_1 = hit1_df['hit_2_given_1'].sum()
        hit_3_given_1 = hit1_df['hit_3_given_1'].sum()
        hit_23_given_1 = hit1_df['hit_23_given_1'].sum()

        rate_2_given_1 = (hit_2_given_1 / count_hit1 * 100)
        rate_3_given_1 = (hit_3_given_1 / count_hit1 * 100)
        rate_23_given_1 = (hit_23_given_1 / count_hit1 * 100)

        print(f"\n信頼度{confidence} (1位的中={count_hit1}レース)")
        print(f"  2位的中率（1位的中時）: {rate_2_given_1:.2f}%")
        print(f"  3位的中率（1位的中時）: {rate_3_given_1:.2f}%")
        print(f"  2位&3位的中率（1位的中時）: {rate_23_given_1:.2f}%")

        # 理論値（残り5艇から2位・3位を当てる）
        # 2位を当てる: 1/5 = 20%
        # 3位を当てる（2位的中前提）: 1/4 = 25%
        # 両方当てる: 1/5 * 1/4 = 5%
        random_2 = 1/5 * 100  # 20%
        random_3 = 1/4 * 100  # 25%
        random_23 = 1/5 * 1/4 * 100  # 5%

        print(f"  理論値: 2位={random_2:.1f}%, 3位={random_3:.1f}%, 2位&3位={random_23:.1f}%")
        print(f"  実績/理論: 2位={rate_2_given_1/random_2:.2f}倍, 3位={rate_3_given_1/random_3:.2f}倍, 2位&3位={rate_23_given_1/random_23:.2f}倍")

def analyze_prediction_vs_actual(df):
    """予想順位と実際の順位のズレ"""
    print("\n" + "=" * 80)
    print("【予想2位・3位の実際の順位分布】")
    print("=" * 80)

    for confidence in ['B']:  # 信頼度Bに絞る
        conf_df = df[df['confidence'] == confidence]

        print(f"\n信頼度{confidence}")

        # 予想2位の実際の順位
        print("\n【予想2位の実際の順位】")
        pred2_ranks = conf_df['pred_2_actual_rank'].value_counts().sort_index()
        total = len(conf_df)
        for rank, count in pred2_ranks.items():
            pct = count / total * 100
            print(f"  {rank}位: {count}回 ({pct:.1f}%)")

        # 予想3位の実際の順位
        print("\n【予想3位の実際の順位】")
        pred3_ranks = conf_df['pred_3_actual_rank'].value_counts().sort_index()
        for rank, count in pred3_ranks.items():
            pct = count / total * 100
            print(f"  {rank}位: {count}回 ({pct:.1f}%)")

def analyze_actual_vs_prediction(df):
    """実際の2位・3位を予想で何位にしていたか"""
    print("\n" + "=" * 80)
    print("【実際の2位・3位を予想で何位にしていたか】")
    print("=" * 80)

    for confidence in ['B']:
        conf_df = df[df['confidence'] == confidence]

        print(f"\n信頼度{confidence}")

        # 実際の2位を予想で何位にしていたか
        print("\n【実際の2位を予想で何位にしていたか】")
        actual2_pred_ranks = conf_df['actual_2_pred_rank'].value_counts().sort_index()
        total = len(conf_df)
        for rank, count in actual2_pred_ranks.items():
            if pd.isna(rank):
                continue
            pct = count / total * 100
            print(f"  予想{int(rank)}位: {count}回 ({pct:.1f}%)")

        # 実際の3位を予想で何位にしていたか
        print("\n【実際の3位を予想で何位にしていたか】")
        actual3_pred_ranks = conf_df['actual_3_pred_rank'].value_counts().sort_index()
        for rank, count in actual3_pred_ranks.items():
            if pd.isna(rank):
                continue
            pct = count / total * 100
            print(f"  予想{int(rank)}位: {count}回 ({pct:.1f}%)")

def analyze_score_differences(df):
    """スコア差と的中率の関係"""
    print("\n" + "=" * 80)
    print("【スコア差と的中率の関係（信頼度B）】")
    print("=" * 80)

    conf_df = df[df['confidence'] == 'B']

    # 1位と2位のスコア差で分類
    print("\n【1位と2位のスコア差 vs 2位的中率】")
    bins = [0, 2, 5, 10, 20, 100]
    labels = ['0-2点', '2-5点', '5-10点', '10-20点', '20点以上']
    conf_df['score_diff_1_2_bin'] = pd.cut(conf_df['score_diff_1_2'], bins=bins, labels=labels)

    for bin_label in labels:
        bin_df = conf_df[conf_df['score_diff_1_2_bin'] == bin_label]
        if len(bin_df) == 0:
            continue

        hit_2 = bin_df['hit_2'].sum()
        rate_2 = (hit_2 / len(bin_df) * 100)
        print(f"  {bin_label}: {rate_2:.2f}% ({hit_2}/{len(bin_df)})")

    # 2位と3位のスコア差で分類
    print("\n【2位と3位のスコア差 vs 3位的中率】")
    conf_df['score_diff_2_3_bin'] = pd.cut(conf_df['score_diff_2_3'], bins=bins, labels=labels)

    for bin_label in labels:
        bin_df = conf_df[conf_df['score_diff_2_3_bin'] == bin_label]
        if len(bin_df) == 0:
            continue

        hit_3 = bin_df['hit_3'].sum()
        rate_3 = (hit_3 / len(bin_df) * 100)
        print(f"  {bin_label}: {rate_3:.2f}% ({hit_3}/{len(bin_df)})")

def analyze_rank2_patterns_when_rank1_hit(df):
    """1位的中時に2位が外れる原因を分析"""
    print("\n" + "=" * 80)
    print("【1位的中時に2位が外れる原因分析（信頼度B）】")
    print("=" * 80)

    conf_df = df[df['confidence'] == 'B']
    hit1_df = conf_df[conf_df['hit_1'] == True]

    # 2位が外れたレース
    hit1_miss2_df = hit1_df[hit1_df['hit_2_given_1'] == False]

    print(f"\n1位的中レース: {len(hit1_df)}")
    print(f"  うち2位的中: {hit1_df['hit_2_given_1'].sum()}")
    print(f"  うち2位不的中: {len(hit1_miss2_df)}")

    if len(hit1_miss2_df) > 0:
        print("\n【2位が外れた場合、予想2位は実際何位だったか】")
        pred2_ranks = hit1_miss2_df['pred_2_actual_rank'].value_counts().sort_index()
        for rank, count in pred2_ranks.items():
            pct = count / len(hit1_miss2_df) * 100
            print(f"  {rank}位: {count}回 ({pct:.1f}%)")

        print("\n【2位が外れた場合、実際の2位を予想で何位にしていたか】")
        actual2_pred_ranks = hit1_miss2_df['actual_2_pred_rank'].value_counts().sort_index()
        for rank, count in actual2_pred_ranks.items():
            if pd.isna(rank):
                continue
            pct = count / len(hit1_miss2_df) * 100
            print(f"  予想{int(rank)}位: {count}回 ({pct:.1f}%)")

def propose_improvements(df):
    """改善提案"""
    print("\n" + "=" * 80)
    print("【2位・3位予想精度の改善提案】")
    print("=" * 80)

    conf_b = df[df['confidence'] == 'B']

    # 問題点のサマリー
    print("\n【現状の問題点】")

    total = len(conf_b)
    hit_1 = conf_b['hit_1'].sum()
    hit_2 = conf_b['hit_2'].sum()
    hit_3 = conf_b['hit_3'].sum()

    rate_1 = hit_1 / total * 100
    rate_2 = hit_2 / total * 100
    rate_3 = hit_3 / total * 100

    random_rate = 1/6 * 100  # 16.67%

    print(f"1. 1位的中率: {rate_1:.2f}% (ランダムの{rate_1/random_rate:.1f}倍) ← 優秀")
    print(f"2. 2位的中率: {rate_2:.2f}% (ランダムの{rate_2/random_rate:.1f}倍) ← 問題")
    print(f"3. 3位的中率: {rate_3:.2f}% (ランダムの{rate_3/random_rate:.1f}倍) ← 問題")

    # 1位的中時の分析
    hit1_df = conf_b[conf_b['hit_1'] == True]
    if len(hit1_df) > 0:
        hit_2_given_1 = hit1_df['hit_2_given_1'].sum()
        rate_2_given_1 = hit_2_given_1 / len(hit1_df) * 100
        random_2_given_1 = 1/5 * 100  # 20%

        print(f"\n4. 1位的中時の2位的中率: {rate_2_given_1:.2f}% (理論値20%の{rate_2_given_1/random_2_given_1:.2f}倍)")

        if rate_2_given_1 < random_2_given_1:
            print("   → ランダム以下！条件付き確率モデルが機能していない")

    print("\n【改善策の提案】")

    print("\n1. 条件付き確率モデルの見直し")
    print("   - 現在: HierarchicalPredictor（1着→2着→3着の段階的予測）")
    print("   - 問題: 1位的中時の2位的中率がランダム以下")
    print("   - 対策: ConditionalRankModelの学習データを見直す")

    print("\n2. 2位・3位の特徴量を強化")
    print("   - 追加すべき特徴量:")
    print("     - 展示タイムの2位・3位（現在は1位中心？）")
    print("     - STの2位・3位")
    print("     - 進入コースの2位・3位の相対位置")
    print("     - 1位との相対スコア差")

    print("\n3. スコア差分の活用")
    # スコア差と的中率の関係をチェック
    score_diff_stats = conf_b.groupby(pd.cut(conf_b['score_diff_1_2'], bins=[0, 5, 10, 100]))['hit_2'].mean()
    print("   - 1位と2位のスコア差が小さいほど2位予想が難しい")
    print("   - スコア差を信頼度判定に組み込む")

    print("\n4. 直前情報の活用度を上げる")
    print("   - 展示タイム、STの順位相関を確認")
    print("   - 直前情報スコアの重み付けを調整")

    print("\n5. 検証スクリプトの作成")
    print("   - scripts/validate_hierarchical_predictor.py")
    print("   - ConditionalRankModelの精度を個別に検証")
    print("   - 学習データの質を確認")

def main():
    """メイン処理"""
    print("2位・3位予想精度の詳細分析を開始します...")
    print(f"データベース: {DB_PATH}")

    # データ読み込み
    print("\nデータ読み込み中...")
    df = load_predictions_with_results()

    if len(df) == 0:
        print("ERROR: データが見つかりません")
        return

    print(f"{len(df)} 件のレースを取得しました")

    # 分析実行
    analyze_rank_accuracy(df)
    analyze_conditional_accuracy(df)
    analyze_prediction_vs_actual(df)
    analyze_actual_vs_prediction(df)
    analyze_score_differences(df)
    analyze_rank2_patterns_when_rank1_hit(df)
    propose_improvements(df)

    # 結果をCSVに保存
    output_path = Path(__file__).parent.parent / "results" / f"rank23_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n分析結果を保存しました: {output_path}")

if __name__ == "__main__":
    main()
