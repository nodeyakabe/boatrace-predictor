"""
信頼度Bの詳細分析スクリプト

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

# データベースパス
DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

def load_confidence_b_data():
    """2024年・2025年の信頼度Bデータを抽出"""
    conn = sqlite3.connect(DB_PATH)

    # まず、信頼度Bの予想データを取得（1位予想のみ）
    query = """
    WITH confidence_b_races AS (
        SELECT
            p.race_id,
            p.pit_number as predicted_rank_1,
            p.total_score,
            p.confidence,
            p.racer_name,
            p.racer_number,
            p.course_score,
            p.racer_score,
            p.motor_score,
            p.kimarite_score,
            p.grade_score,
            p.prediction_type
        FROM race_predictions p
        WHERE p.confidence = 'B'
          AND p.rank_prediction = 1
    ),
    predicted_2nd AS (
        SELECT
            p.race_id,
            p.pit_number as predicted_rank_2
        FROM race_predictions p
        WHERE p.rank_prediction = 2
    ),
    predicted_3rd AS (
        SELECT
            p.race_id,
            p.pit_number as predicted_rank_3
        FROM race_predictions p
        WHERE p.rank_prediction = 3
    )
    SELECT
        r.race_date,
        r.venue_code,
        v.name as venue_name,
        r.race_number,
        cb.confidence,
        cb.predicted_rank_1,
        p2.predicted_rank_2,
        p3.predicted_rank_3,
        cb.total_score as final_score,
        cb.course_score + cb.racer_score + cb.motor_score + cb.kimarite_score + cb.grade_score as pre_score,
        0 as before_score,  -- race_predictionsには直前スコアが分離されていない

        -- レース結果
        res.rank_1,
        res.rank_2,
        res.rank_3,

        -- 払戻金（三連単）
        pay.payout as trifecta_payout,

        -- 出走表情報（トップ予想艇の級別）
        e1.racer_class as top_racer_class,
        e1.racer_name as top_racer_name,

        -- 会場情報（1コース勝率をイン強度として使用）
        vd.course_1_win_rate as inner_course_advantage,

        -- オッズ情報（1-2-3のオッズ）
        odds.odds as predicted_odds

    FROM confidence_b_races cb
    LEFT JOIN predicted_2nd p2 ON cb.race_id = p2.race_id
    LEFT JOIN predicted_3rd p3 ON cb.race_id = p3.race_id
    LEFT JOIN races r ON cb.race_id = r.id
    LEFT JOIN venues v ON r.venue_code = v.code
    LEFT JOIN results res ON r.id = res.race_id
    LEFT JOIN payouts pay ON r.id = pay.race_id
                          AND pay.bet_type = '3連単'
                          AND pay.winning_numbers = printf('%d-%d-%d',
                              res.rank_1, res.rank_2, res.rank_3)
    LEFT JOIN entries e1 ON r.id = e1.race_id
                         AND cb.predicted_rank_1 = e1.pit_number
    LEFT JOIN venue_data vd ON r.venue_code = vd.venue_code
    LEFT JOIN trifecta_odds odds ON r.id = odds.race_id
                                 AND odds.combination = printf('%d-%d-%d',
                                     cb.predicted_rank_1, p2.predicted_rank_2, p3.predicted_rank_3)

    WHERE r.race_date >= '2024-01-01'
      AND r.race_date < '2026-01-01'
    ORDER BY r.race_date, r.venue_code, r.race_number
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    return df

def calculate_odds_range(odds):
    """オッズをレンジに分類"""
    if pd.isna(odds):
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

def calculate_venue_type(inner_advantage):
    """会場タイプを分類"""
    if pd.isna(inner_advantage):
        return '不明'
    elif inner_advantage >= 60:
        return '超イン強'
    elif inner_advantage >= 50:
        return 'イン強'
    elif inner_advantage >= 40:
        return '普通'
    else:
        return 'イン弱'

def analyze_basic_stats(df):
    """基本統計の分析"""
    print("=" * 80)
    print("【信頼度B 基本統計】")
    print("=" * 80)

    # 的中判定
    df['hit'] = (
        (df['predicted_rank_1'] == df['rank_1']) &
        (df['predicted_rank_2'] == df['rank_2']) &
        (df['predicted_rank_3'] == df['rank_3'])
    )

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
        print(f"\n【的中レースの払戻金統計】")
        print(f"平均払戻: {hit_df['trifecta_payout'].mean():.1f}円")
        print(f"中央値払戻: {hit_df['trifecta_payout'].median():.1f}円")
        print(f"最小払戻: {hit_df['trifecta_payout'].min():.1f}円")
        print(f"最大払戻: {hit_df['trifecta_payout'].max():.1f}円")

        # ROI計算（仮に全レース300円購入した場合）
        bet_amount = 300
        total_bet = total * bet_amount
        total_return = hit_df['trifecta_payout'].sum()
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
    cross_tab = df.groupby(['top_racer_class', 'odds_range']).agg({
        'race_date': 'count',
        'hit': 'sum',
        'trifecta_payout': lambda x: x[df.loc[x.index, 'hit']].sum() if x[df.loc[x.index, 'hit']].any() else 0
    }).rename(columns={'race_date': 'count', 'trifecta_payout': 'total_return'})

    cross_tab['hit_rate'] = (cross_tab['hit'] / cross_tab['count'] * 100)
    cross_tab['total_bet'] = cross_tab['count'] * 300
    cross_tab['profit'] = cross_tab['total_return'] - cross_tab['total_bet']
    cross_tab['roi'] = (cross_tab['total_return'] / cross_tab['total_bet'] * 100)

    # 見やすくフォーマット
    cross_tab = cross_tab.round({
        'hit_rate': 1,
        'roi': 1
    })

    print("\n" + cross_tab.to_string())

    # ROI 100%以上の条件を抽出
    profitable = cross_tab[cross_tab['roi'] >= 100].sort_values('roi', ascending=False)

    print("\n" + "=" * 80)
    print("【ROI 100%以上の条件】")
    print("=" * 80)
    if len(profitable) > 0:
        print(profitable.to_string())
    else:
        print("該当なし")

    # ROI 80%以上（損失20%以内）の条件も確認
    nearly_profitable = cross_tab[(cross_tab['roi'] >= 80) & (cross_tab['roi'] < 100)].sort_values('roi', ascending=False)

    print("\n" + "=" * 80)
    print("【ROI 80%以上100%未満の条件（損失20%以内）】")
    print("=" * 80)
    if len(nearly_profitable) > 0:
        print(nearly_profitable.to_string())
    else:
        print("該当なし")

    return df

def analyze_by_venue_type(df):
    """会場特性別の分析"""
    print("\n" + "=" * 80)
    print("【会場特性別の分析】")
    print("=" * 80)

    # 会場タイプを追加
    df['venue_type'] = df['inner_course_advantage'].apply(calculate_venue_type)

    venue_stats = df.groupby('venue_type').agg({
        'race_date': 'count',
        'hit': 'sum',
        'trifecta_payout': lambda x: x[df.loc[x.index, 'hit']].sum() if x[df.loc[x.index, 'hit']].any() else 0,
        'predicted_odds': 'mean'
    }).rename(columns={'race_date': 'count', 'trifecta_payout': 'total_return'})

    venue_stats['hit_rate'] = (venue_stats['hit'] / venue_stats['count'] * 100)
    venue_stats['total_bet'] = venue_stats['count'] * 300
    venue_stats['profit'] = venue_stats['total_return'] - venue_stats['total_bet']
    venue_stats['roi'] = (venue_stats['total_return'] / venue_stats['total_bet'] * 100)

    venue_stats = venue_stats.round({
        'hit_rate': 1,
        'predicted_odds': 1,
        'roi': 1
    })

    print("\n" + venue_stats.to_string())

    # 会場タイプ×級別のクロス集計
    print("\n" + "=" * 80)
    print("【会場タイプ×級別のクロス集計】")
    print("=" * 80)

    venue_class_cross = df.groupby(['venue_type', 'top_racer_class']).agg({
        'race_date': 'count',
        'hit': 'sum',
        'trifecta_payout': lambda x: x[df.loc[x.index, 'hit']].sum() if x[df.loc[x.index, 'hit']].any() else 0
    }).rename(columns={'race_date': 'count', 'trifecta_payout': 'total_return'})

    venue_class_cross['hit_rate'] = (venue_class_cross['hit'] / venue_class_cross['count'] * 100)
    venue_class_cross['total_bet'] = venue_class_cross['count'] * 300
    venue_class_cross['profit'] = venue_class_cross['total_return'] - venue_class_cross['total_bet']
    venue_class_cross['roi'] = (venue_class_cross['total_return'] / venue_class_cross['total_bet'] * 100)

    venue_class_cross = venue_class_cross.round({
        'hit_rate': 1,
        'roi': 1
    })

    print("\n" + venue_class_cross.to_string())

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
    features = ['top_prob', 'final_score', 'pre_score', 'before_score', 'predicted_odds', 'inner_course_advantage']

    comparison = pd.DataFrame({
        '的中平均': hit_df[features].mean(),
        '不的中平均': miss_df[features].mean(),
        '差分': hit_df[features].mean() - miss_df[features].mean()
    })

    print("\n" + comparison.round(2).to_string())

    # カテゴリ特徴の比較
    print("\n【級別の分布】")
    print("的中レース:")
    print(hit_df['top_racer_class'].value_counts())
    print("\n不的中レース:")
    print(miss_df['top_racer_class'].value_counts())

    print("\n【オッズレンジの分布】")
    print("的中レース:")
    print(hit_df['odds_range'].value_counts().sort_index())
    print("\n不的中レース:")
    print(miss_df['odds_range'].value_counts().sort_index())

    print("\n【会場タイプの分布】")
    print("的中レース:")
    print(hit_df['venue_type'].value_counts())
    print("\n不的中レース:")
    print(miss_df['venue_type'].value_counts())

    return df

def propose_strategies(df):
    """信頼度B活用戦略の提案"""
    print("\n" + "=" * 80)
    print("【信頼度B活用戦略の提案】")
    print("=" * 80)

    # オッズレンジを追加（まだなければ）
    if 'odds_range' not in df.columns:
        df['odds_range'] = df['predicted_odds'].apply(calculate_odds_range)

    # 戦略1: 級別×オッズレンジでフィルタリング
    print("\n【戦略1: 級別×オッズレンジフィルタリング】")

    # ROI 100%以上の組み合わせを再確認
    cross_tab = df.groupby(['top_racer_class', 'odds_range']).agg({
        'race_date': 'count',
        'hit': 'sum',
        'trifecta_payout': lambda x: x[df.loc[x.index, 'hit']].sum() if x[df.loc[x.index, 'hit']].any() else 0
    }).rename(columns={'race_date': 'count', 'trifecta_payout': 'total_return'})

    cross_tab['hit_rate'] = (cross_tab['hit'] / cross_tab['count'] * 100)
    cross_tab['total_bet'] = cross_tab['count'] * 300
    cross_tab['profit'] = cross_tab['total_return'] - cross_tab['total_bet']
    cross_tab['roi'] = (cross_tab['total_return'] / cross_tab['total_bet'] * 100)

    profitable = cross_tab[
        (cross_tab['roi'] >= 100) &
        (cross_tab['count'] >= 10)  # サンプル数10以上
    ].sort_values('roi', ascending=False)

    if len(profitable) > 0:
        print("\n✅ 採用候補（ROI 100%以上、サンプル10以上）:")
        print(profitable.to_string())

        # 戦略1の収支計算
        strategy1_conditions = profitable.index.tolist()
        strategy1_df = df[
            df.apply(lambda x: (x['top_racer_class'], x['odds_range']) in strategy1_conditions, axis=1)
        ]

        s1_total = len(strategy1_df)
        s1_hit = strategy1_df['hit'].sum()
        s1_hit_rate = (s1_hit / s1_total * 100) if s1_total > 0 else 0
        s1_total_bet = s1_total * 300
        s1_total_return = strategy1_df[strategy1_df['hit']]['trifecta_payout'].sum()
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
        print("\n❌ ROI 100%以上の条件なし")

    # 戦略2: スコア閾値でフィルタリング
    print("\n" + "=" * 80)
    print("【戦略2: スコア閾値フィルタリング】")

    # final_scoreの分位数を確認
    quantiles = df['final_score'].quantile([0.5, 0.6, 0.7, 0.8, 0.9])
    print("\nfinal_scoreの分位数:")
    print(quantiles)

    # 上位30%のレースに絞る
    threshold = df['final_score'].quantile(0.7)
    high_score_df = df[df['final_score'] >= threshold]

    s2_total = len(high_score_df)
    s2_hit = high_score_df['hit'].sum()
    s2_hit_rate = (s2_hit / s2_total * 100) if s2_total > 0 else 0
    s2_total_bet = s2_total * 300
    s2_total_return = high_score_df[high_score_df['hit']]['trifecta_payout'].sum()
    s2_profit = s2_total_return - s2_total_bet
    s2_roi = (s2_total_return / s2_total_bet * 100) if s2_total_bet > 0 else 0

    print(f"\n【戦略2のバックテスト結果（final_score >= {threshold:.1f}）】")
    print(f"対象レース数: {s2_total}")
    print(f"的中数: {s2_hit}")
    print(f"的中率: {s2_hit_rate:.2f}%")
    print(f"総購入額: {s2_total_bet:,}円")
    print(f"総払戻額: {s2_total_return:,.0f}円")
    print(f"収支: {s2_profit:+,.0f}円")
    print(f"ROI: {s2_roi:.1f}%")

    # 戦略3: 組み合わせ戦略（級別フィルタ + スコア閾値）
    print("\n" + "=" * 80)
    print("【戦略3: 組み合わせ戦略】")

    # A1級 かつ high score
    strategy3_df = df[
        (df['top_racer_class'] == 'A1') &
        (df['final_score'] >= threshold)
    ]

    s3_total = len(strategy3_df)
    if s3_total > 0:
        s3_hit = strategy3_df['hit'].sum()
        s3_hit_rate = (s3_hit / s3_total * 100)
        s3_total_bet = s3_total * 300
        s3_total_return = strategy3_df[strategy3_df['hit']]['trifecta_payout'].sum()
        s3_profit = s3_total_return - s3_total_bet
        s3_roi = (s3_total_return / s3_total_bet * 100) if s3_total_bet > 0 else 0

        print(f"\n【戦略3のバックテスト結果（A1級 かつ final_score >= {threshold:.1f}）】")
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
    df = load_confidence_b_data()

    if len(df) == 0:
        print("ERROR: 信頼度Bのデータが見つかりません")
        return

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
