"""
信頼度Bの詳細分析スクリプト v2

2024年・2025年のデータを使って信頼度Bの活用方法を検討する
- 基本統計
- 級別×オッズレンジのクロス集計
- 会場特性別の分析
- 的中・不的中レースの特徴分析
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def calculate_odds_range(odds):
    """オッズをレンジに分類"""
    if pd.isna(odds) or odds == 0:
        return '不明'
    elif odds < 10:
        return '5-10倍未満'
    elif odds < 20:
        return '10-20倍'
    elif odds < 30:
        return '20-30倍'
    elif odds < 50:
        return '30-50倍'
    elif odds < 100:
        return '50-100倍'
    elif odds < 150:
        return '100-150倍'
    elif odds < 200:
        return '150-200倍'
    elif odds < 300:
        return '200-300倍'
    elif odds < 500:
        return '300-500倍'
    else:
        return '500倍以上'

def calculate_venue_type(course_1_win_rate):
    """会場タイプを分類（1コース勝率ベース）"""
    if pd.isna(course_1_win_rate) or course_1_win_rate == 0:
        return '不明'
    elif course_1_win_rate >= 60:
        return '超イン強'
    elif course_1_win_rate >= 50:
        return 'イン強'
    elif course_1_win_rate >= 40:
        return '普通'
    else:
        return 'イン弱'

def load_confidence_b_data():
    """2024年・2025年の信頼度Bデータを抽出"""
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

        # 予測情報を取得（信頼度Bのみ）
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

        # 1位予想の信頼度がB以外はスキップ
        if preds[0]['confidence'] != 'B':
            continue

        confidence = preds[0]['confidence']
        predicted_rank_1 = preds[0]['pit_number']
        predicted_rank_2 = preds[1]['pit_number']
        predicted_rank_3 = preds[2]['pit_number']
        total_score = preds[0]['total_score']
        course_score = preds[0]['course_score']
        racer_score = preds[0]['racer_score']
        motor_score = preds[0]['motor_score']
        kimarite_score = preds[0]['kimarite_score']
        grade_score = preds[0]['grade_score']

        pred_combo = f"{predicted_rank_1}-{predicted_rank_2}-{predicted_rank_3}"

        # オッズを取得
        cursor.execute('''
            SELECT odds FROM trifecta_odds
            WHERE race_id = ? AND combination = ?
        ''', (race_id, pred_combo))
        odds_row = cursor.fetchone()
        predicted_odds = odds_row['odds'] if odds_row else None

        # 1コースの級別を取得
        cursor.execute('''
            SELECT racer_rank FROM entries
            WHERE race_id = ? AND pit_number = 1
        ''', (race_id,))
        c1_entry = cursor.fetchone()
        c1_class = c1_entry['racer_rank'] if c1_entry else None

        # トップ予想艇の級別を取得
        cursor.execute('''
            SELECT racer_rank FROM entries
            WHERE race_id = ? AND pit_number = ?
        ''', (race_id, predicted_rank_1))
        top_entry = cursor.fetchone()
        top_racer_class = top_entry['racer_rank'] if top_entry else None

        # 会場情報を取得（1コース勝率）
        cursor.execute('''
            SELECT course_1_win_rate FROM venue_data
            WHERE venue_code = ?
        ''', (venue_code,))
        venue_row = cursor.fetchone()
        course_1_win_rate = venue_row['course_1_win_rate'] if venue_row else None

        # 会場名を取得
        cursor.execute('''
            SELECT name FROM venues
            WHERE code = ?
        ''', (venue_code,))
        venue_name_row = cursor.fetchone()
        venue_name = venue_name_row['name'] if venue_name_row else None

        # レース結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) >= 3:
            rank_1 = results[0]['pit_number']
            rank_2 = results[1]['pit_number']
            rank_3 = results[2]['pit_number']
            actual_combo = f"{rank_1}-{rank_2}-{rank_3}"

            # 的中判定
            hit = (pred_combo == actual_combo)

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
            hit = False
            trifecta_payout = None

        # データを追加
        data_list.append({
            'race_date': race_date,
            'venue_code': venue_code,
            'venue_name': venue_name,
            'race_number': race_number,
            'confidence': confidence,
            'predicted_rank_1': predicted_rank_1,
            'predicted_rank_2': predicted_rank_2,
            'predicted_rank_3': predicted_rank_3,
            'predicted_odds': predicted_odds,
            'total_score': total_score,
            'course_score': course_score,
            'racer_score': racer_score,
            'motor_score': motor_score,
            'kimarite_score': kimarite_score,
            'grade_score': grade_score,
            'top_racer_class': top_racer_class,
            'c1_class': c1_class,
            'course_1_win_rate': course_1_win_rate,
            'rank_1': rank_1,
            'rank_2': rank_2,
            'rank_3': rank_3,
            'hit': hit,
            'trifecta_payout': trifecta_payout
        })

    conn.close()

    df = pd.DataFrame(data_list)
    return df

def analyze_basic_stats(df):
    """基本統計の分析"""
    print("=" * 80)
    print("【信頼度B 基本統計】")
    print("=" * 80)

    total = len(df)
    hit_count = df['hit'].sum()
    hit_rate = (hit_count / total * 100) if total > 0 else 0

    print(f"\n総レース数: {total}")
    print(f"的中数: {hit_count}")
    print(f"的中率: {hit_rate:.2f}%")

    # 年別統計
    df['year'] = pd.to_datetime(df['race_date']).dt.year
    year_stats = df.groupby('year').agg({
        'race_date': 'count',
        'hit': 'sum'
    }).rename(columns={'race_date': 'count'})
    year_stats['hit_rate'] = (year_stats['hit'] / year_stats['count'] * 100)

    print("\n【年別統計】")
    print(year_stats)

    # 払戻金の統計（的中レースのみ）
    hit_df = df[df['hit'] == True]
    if len(hit_df) > 0:
        print(f"\n【的中レースの払戻金統計（100円あたり）】")
        print(f"平均払戻: {hit_df['trifecta_payout'].mean():.1f}円")
        print(f"中央値払戻: {hit_df['trifecta_payout'].median():.1f}円")
        print(f"最小払戻: {hit_df['trifecta_payout'].min():.1f}円")
        print(f"最大払戻: {hit_df['trifecta_payout'].max():.1f}円")

        # ROI計算（仮に全レース300円購入した場合）
        bet_amount = 300
        total_bet = total * bet_amount
        total_return = (hit_df['trifecta_payout'] * bet_amount / 100).sum()
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        print(f"\n【ROI計算（全レース300円購入）】")
        print(f"総購入額: {total_bet:,}円")
        print(f"総払戻額: {total_return:,.0f}円")
        print(f"収支: {total_return - total_bet:+,.0f}円")
        print(f"ROI: {roi:.1f}%")

    return df

def analyze_by_racer_class_and_odds(df):
    """級別×オッズレンジのクロス集計"""
    print("\n" + "=" * 80)
    print("【級別×オッズレンジのクロス集計】")
    print("=" * 80)

    # オッズレンジを追加
    df['odds_range'] = df['predicted_odds'].apply(calculate_odds_range)

    # 級別×オッズレンジでグループ化
    grouped = df.groupby(['top_racer_class', 'odds_range'])

    results = []
    for (racer_class, odds_range), group in grouped:
        count = len(group)
        hit = group['hit'].sum()
        hit_rate = (hit / count * 100) if count > 0 else 0

        # 払戻金計算
        hit_group = group[group['hit'] == True]
        bet_amount = 300
        total_bet = count * bet_amount
        total_return = (hit_group['trifecta_payout'] * bet_amount / 100).sum() if len(hit_group) > 0 else 0
        profit = total_return - total_bet
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        results.append({
            '級別': racer_class,
            'オッズレンジ': odds_range,
            'レース数': count,
            '的中数': hit,
            '的中率%': round(hit_rate, 1),
            '総購入額': total_bet,
            '総払戻額': int(total_return),
            '収支': int(profit),
            'ROI%': round(roi, 1)
        })

    cross_tab = pd.DataFrame(results)
    cross_tab = cross_tab.sort_values(['級別', 'ROI%'], ascending=[True, False])

    print("\n" + cross_tab.to_string(index=False))

    # ROI 100%以上の条件を抽出
    profitable = cross_tab[cross_tab['ROI%'] >= 100].sort_values('ROI%', ascending=False)

    print("\n" + "=" * 80)
    print("【ROI 100%以上の条件】")
    print("=" * 80)
    if len(profitable) > 0:
        print(profitable.to_string(index=False))
    else:
        print("該当なし")

    # ROI 80%以上（損失20%以内）の条件も確認
    nearly_profitable = cross_tab[(cross_tab['ROI%'] >= 80) & (cross_tab['ROI%'] < 100)].sort_values('ROI%', ascending=False)

    print("\n" + "=" * 80)
    print("【ROI 80%以上100%未満の条件（損失20%以内）】")
    print("=" * 80)
    if len(nearly_profitable) > 0:
        print(nearly_profitable.to_string(index=False))
    else:
        print("該当なし")

    return df

def analyze_by_venue_type(df):
    """会場特性別の分析"""
    print("\n" + "=" * 80)
    print("【会場特性別の分析】")
    print("=" * 80)

    # 会場タイプを追加
    df['venue_type'] = df['course_1_win_rate'].apply(calculate_venue_type)

    grouped = df.groupby('venue_type')

    results = []
    for venue_type, group in grouped:
        count = len(group)
        hit = group['hit'].sum()
        hit_rate = (hit / count * 100) if count > 0 else 0

        # 払戻金計算
        hit_group = group[group['hit'] == True]
        bet_amount = 300
        total_bet = count * bet_amount
        total_return = (hit_group['trifecta_payout'] * bet_amount / 100).sum() if len(hit_group) > 0 else 0
        profit = total_return - total_bet
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        avg_odds = group['predicted_odds'].mean()

        results.append({
            '会場タイプ': venue_type,
            'レース数': count,
            '的中数': hit,
            '的中率%': round(hit_rate, 1),
            '平均オッズ': round(avg_odds, 1),
            '総購入額': total_bet,
            '総払戻額': int(total_return),
            '収支': int(profit),
            'ROI%': round(roi, 1)
        })

    venue_stats = pd.DataFrame(results)
    venue_stats = venue_stats.sort_values('ROI%', ascending=False)

    print("\n" + venue_stats.to_string(index=False))

    # 会場タイプ×級別のクロス集計
    print("\n" + "=" * 80)
    print("【会場タイプ×級別のクロス集計】")
    print("=" * 80)

    grouped2 = df.groupby(['venue_type', 'top_racer_class'])

    results2 = []
    for (venue_type, racer_class), group in grouped2:
        count = len(group)
        hit = group['hit'].sum()
        hit_rate = (hit / count * 100) if count > 0 else 0

        # 払戻金計算
        hit_group = group[group['hit'] == True]
        bet_amount = 300
        total_bet = count * bet_amount
        total_return = (hit_group['trifecta_payout'] * bet_amount / 100).sum() if len(hit_group) > 0 else 0
        profit = total_return - total_bet
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        results2.append({
            '会場タイプ': venue_type,
            '級別': racer_class,
            'レース数': count,
            '的中数': hit,
            '的中率%': round(hit_rate, 1),
            '総購入額': total_bet,
            '総払戻額': int(total_return),
            '収支': int(profit),
            'ROI%': round(roi, 1)
        })

    venue_class_cross = pd.DataFrame(results2)
    venue_class_cross = venue_class_cross.sort_values(['会場タイプ', 'ROI%'], ascending=[True, False])

    print("\n" + venue_class_cross.to_string(index=False))

    return df

def analyze_hit_vs_miss_features(df):
    """的中レースと不的中レースの特徴分析"""
    print("\n" + "=" * 80)
    print("【的中レースと不的中レースの特徴比較】")
    print("=" * 80)

    hit_df = df[df['hit'] == True]
    miss_df = df[df['hit'] == False]

    print(f"\n的中レース数: {len(hit_df)}")
    print(f"不的中レース数: {len(miss_df)}")

    # 数値特徴の比較
    features = ['total_score', 'course_score', 'racer_score', 'motor_score',
                'kimarite_score', 'grade_score', 'predicted_odds', 'course_1_win_rate']

    comparison_data = []
    for feat in features:
        comparison_data.append({
            '特徴': feat,
            '的中平均': round(hit_df[feat].mean(), 2) if len(hit_df) > 0 else 0,
            '不的中平均': round(miss_df[feat].mean(), 2) if len(miss_df) > 0 else 0,
            '差分': round(hit_df[feat].mean() - miss_df[feat].mean(), 2) if len(hit_df) > 0 and len(miss_df) > 0 else 0
        })

    comparison = pd.DataFrame(comparison_data)
    print("\n" + comparison.to_string(index=False))

    # カテゴリ特徴の比較
    print("\n【級別の分布】")
    print("的中レース:")
    if len(hit_df) > 0:
        print(hit_df['top_racer_class'].value_counts())
    else:
        print("データなし")

    print("\n不的中レース:")
    if len(miss_df) > 0:
        print(miss_df['top_racer_class'].value_counts())
    else:
        print("データなし")

    print("\n【オッズレンジの分布】")
    print("的中レース:")
    if len(hit_df) > 0:
        print(hit_df['odds_range'].value_counts().sort_index())
    else:
        print("データなし")

    print("\n不的中レース:")
    if len(miss_df) > 0:
        print(miss_df['odds_range'].value_counts().sort_index())
    else:
        print("データなし")

    print("\n【会場タイプの分布】")
    print("的中レース:")
    if len(hit_df) > 0:
        print(hit_df['venue_type'].value_counts())
    else:
        print("データなし")

    print("\n不的中レース:")
    if len(miss_df) > 0:
        print(miss_df['venue_type'].value_counts())
    else:
        print("データなし")

    return df

def propose_strategies(df):
    """信頼度B活用戦略の提案"""
    print("\n" + "=" * 80)
    print("【信頼度B活用戦略の提案】")
    print("=" * 80)

    # オッズレンジを追加（まだなければ）
    if 'odds_range' not in df.columns:
        df['odds_range'] = df['predicted_odds'].apply(calculate_odds_range)

    # 戦略1: 級別×オッズレンジでフィルタリング（ROI 100%以上、サンプル10以上）
    print("\n【戦略1: 級別×オッズレンジフィルタリング】")

    grouped = df.groupby(['top_racer_class', 'odds_range'])

    profitable_conditions = []
    for (racer_class, odds_range), group in grouped:
        count = len(group)
        if count < 10:  # サンプル数10未満は除外
            continue

        hit = group['hit'].sum()
        hit_rate = (hit / count * 100) if count > 0 else 0

        # 払戻金計算
        hit_group = group[group['hit'] == True]
        bet_amount = 300
        total_bet = count * bet_amount
        total_return = (hit_group['trifecta_payout'] * bet_amount / 100).sum() if len(hit_group) > 0 else 0
        profit = total_return - total_bet
        roi = (total_return / total_bet * 100) if total_bet > 0 else 0

        if roi >= 100:
            profitable_conditions.append({
                '級別': racer_class,
                'オッズレンジ': odds_range,
                'レース数': count,
                '的中数': hit,
                '的中率%': round(hit_rate, 1),
                '総購入額': total_bet,
                '総払戻額': int(total_return),
                '収支': int(profit),
                'ROI%': round(roi, 1)
            })

    if profitable_conditions:
        profitable_df = pd.DataFrame(profitable_conditions).sort_values('ROI%', ascending=False)
        print("\n[OK] 採用候補（ROI 100%以上、サンプル10以上）:")
        print(profitable_df.to_string(index=False))

        # 戦略1の収支計算
        strategy1_df = df[
            df.apply(lambda x: any(
                (x['top_racer_class'] == cond['級別']) and (x['odds_range'] == cond['オッズレンジ'])
                for cond in profitable_conditions
            ), axis=1)
        ]

        if len(strategy1_df) > 0:
            s1_total = len(strategy1_df)
            s1_hit = strategy1_df['hit'].sum()
            s1_hit_rate = (s1_hit / s1_total * 100)
            s1_bet_amount = 300
            s1_total_bet = s1_total * s1_bet_amount
            s1_hit_group = strategy1_df[strategy1_df['hit'] == True]
            s1_total_return = (s1_hit_group['trifecta_payout'] * s1_bet_amount / 100).sum()
            s1_profit = s1_total_return - s1_total_bet
            s1_roi = (s1_total_return / s1_total_bet * 100) if s1_total_bet > 0 else 0

            print(f"\n【戦略1のバックテスト結果】")
            print(f"対象レース数: {s1_total}")
            print(f"的中数: {s1_hit}")
            print(f"的中率: {s1_hit_rate:.2f}%")
            print(f"総購入額: {s1_total_bet:,}円")
            print(f"総払戻額: {s1_total_return:,.0f}円")
            print(f"収支: {s1_profit:+,.0f}円")
            print(f"ROI: {s1_roi:.1f}%")
    else:
        print("\n[NG] ROI 100%以上の条件なし")

    # 戦略2: スコア閾値でフィルタリング
    print("\n" + "=" * 80)
    print("【戦略2: スコア閾値フィルタリング】")

    # total_scoreの分位数を確認
    quantiles = df['total_score'].quantile([0.5, 0.6, 0.7, 0.8, 0.9])
    print("\ntotal_scoreの分位数:")
    print(quantiles)

    # 上位30%のレースに絞る
    threshold = df['total_score'].quantile(0.7)
    high_score_df = df[df['total_score'] >= threshold]

    s2_total = len(high_score_df)
    s2_hit = high_score_df['hit'].sum()
    s2_hit_rate = (s2_hit / s2_total * 100) if s2_total > 0 else 0
    s2_bet_amount = 300
    s2_total_bet = s2_total * s2_bet_amount
    s2_hit_group = high_score_df[high_score_df['hit'] == True]
    s2_total_return = (s2_hit_group['trifecta_payout'] * s2_bet_amount / 100).sum() if len(s2_hit_group) > 0 else 0
    s2_profit = s2_total_return - s2_total_bet
    s2_roi = (s2_total_return / s2_total_bet * 100) if s2_total_bet > 0 else 0

    print(f"\n【戦略2のバックテスト結果（total_score >= {threshold:.1f}）】")
    print(f"対象レース数: {s2_total}")
    print(f"的中数: {s2_hit}")
    print(f"的中率: {s2_hit_rate:.2f}%")
    print(f"総購入額: {s2_total_bet:,}円")
    print(f"総払戻額: {s2_total_return:,.0f}円")
    print(f"収支: {s2_profit:+,.0f}円")
    print(f"ROI: {s2_roi:.1f}%")

    # 戦略3: 組み合わせ戦略（級別フィルタ + スコア閾値）
    print("\n" + "=" * 80)
    print("【戦略3: 組み合わせ戦略（A1級 かつ high score）】")

    strategy3_df = df[
        (df['top_racer_class'] == 'A1') &
        (df['total_score'] >= threshold)
    ]

    s3_total = len(strategy3_df)
    if s3_total > 0:
        s3_hit = strategy3_df['hit'].sum()
        s3_hit_rate = (s3_hit / s3_total * 100)
        s3_bet_amount = 300
        s3_total_bet = s3_total * s3_bet_amount
        s3_hit_group = strategy3_df[strategy3_df['hit'] == True]
        s3_total_return = (s3_hit_group['trifecta_payout'] * s3_bet_amount / 100).sum() if len(s3_hit_group) > 0 else 0
        s3_profit = s3_total_return - s3_total_bet
        s3_roi = (s3_total_return / s3_total_bet * 100) if s3_total_bet > 0 else 0

        print(f"\n【戦略3のバックテスト結果（A1級 かつ total_score >= {threshold:.1f}）】")
        print(f"対象レース数: {s3_total}")
        print(f"的中数: {s3_hit}")
        print(f"的中率: {s3_hit_rate:.2f}%")
        print(f"総購入額: {s3_total_bet:,}円")
        print(f"総払戻額: {s3_total_return:,.0f}円")
        print(f"収支: {s3_profit:+,.0f}円")
        print(f"ROI: {s3_roi:.1f}%")
    else:
        print("\n該当レースなし")

    print("\n" + "=" * 80)
    print("【推奨戦略のまとめ】")
    print("=" * 80)
    print("\n各戦略のROIを比較し、最適な戦略を選択してください。")
    print("または、複数の戦略を組み合わせることも検討してください。")

def main():
    """メイン処理"""
    print("信頼度B詳細分析を開始します...")
    print(f"データベース: {DB_PATH}")

    # データ読み込み
    print("\nデータ読み込み中...")
    df = load_confidence_b_data()

    if len(df) == 0:
        print("ERROR: 信頼度Bのデータが見つかりません")
        return

    print(f"{len(df)} 件の信頼度Bレースを取得しました")

    # 分析実行
    df = analyze_basic_stats(df)
    df = analyze_by_racer_class_and_odds(df)
    df = analyze_by_venue_type(df)
    df = analyze_hit_vs_miss_features(df)
    propose_strategies(df)

    # 結果をCSVに保存
    output_path = Path(__file__).parent.parent / "results" / f"confidence_b_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    output_path.parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n分析結果を保存しました: {output_path}")

if __name__ == "__main__":
    main()
