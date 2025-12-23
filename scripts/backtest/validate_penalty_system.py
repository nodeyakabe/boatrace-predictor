# -*- coding: utf-8 -*-
"""
減点システム効果検証スクリプト

減点適用前後での的中率を比較し、システムの有効性を検証
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
import sys

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = Path(__file__).parent.parent / "data" / "boatrace.db"

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}


def categorize_time(time_str):
    """時間帯の分類"""
    if pd.isna(time_str):
        return 'unknown'
    try:
        hour = int(time_str.split(':')[0])
        if hour < 10:
            return '早朝'
        elif hour < 13:
            return '午前'
        elif hour < 16:
            return '午後'
        else:
            return '夕方'
    except:
        return 'unknown'


def categorize_wind(speed):
    """風速の分類"""
    if pd.isna(speed):
        return 'unknown'
    if speed <= 2:
        return '無風'
    elif speed <= 4:
        return '微風'
    elif speed <= 6:
        return '強風'
    else:
        return '暴風'


def categorize_wave(wave):
    """波高の分類"""
    if pd.isna(wave):
        return 'unknown'
    if wave <= 2:
        return '穏やか'
    elif wave <= 5:
        return '小波'
    elif wave <= 10:
        return '中波'
    else:
        return '大波'


class PenaltySystem:
    """減点システム"""

    def __init__(self):
        # 分析で得られた減点ルール（上位30件）
        self.rules = [
            # 危険度最高（7pt以上）
            {'venue': '02', 'time': '午前', 'penalty': 7},
            {'venue': '02', 'time': '夕方', 'penalty': 7},
            {'venue': '03', 'time': '夕方', 'penalty': 7},

            # 会場全体
            {'venue': '02', 'penalty': 4},  # 戸田
            {'venue': '04', 'penalty': 2},  # 平和島

            # 天候
            {'weather': '雨', 'penalty': 6},
            {'weather': '曇', 'penalty': 2},

            # 波高
            {'wave': '大波', 'penalty': 4},

            # 風向×風速（主要パターン）
            {'wind_dir': '北北西', 'wind_cat': '暴風', 'penalty': 5},
            {'wind_dir': '東', 'wind_cat': '暴風', 'penalty': 4},
            {'wind_dir': '西', 'wind_cat': '暴風', 'penalty': 3},
            {'wind_dir': '南東', 'wind_cat': '強風', 'penalty': 3},

            # 会場×風向×風速（潮位影響会場）
            {'venue': '08', 'wind_dir': '北北西', 'wind_cat': '微風', 'penalty': 13},
            {'venue': '03', 'wind_dir': '東', 'wind_cat': '暴風', 'penalty': 5},
            {'venue': '03', 'wind_dir': '西', 'wind_cat': '強風', 'penalty': 6},
            {'venue': '04', 'wind_dir': '東北東', 'wind_cat': '微風', 'penalty': 9},
            {'venue': '04', 'wind_dir': '東南東', 'wind_cat': '微風', 'penalty': 5},
            {'venue': '20', 'wind_dir': '北西', 'wind_cat': '微風', 'penalty': 4},
            {'venue': '20', 'wind_dir': '南東', 'wind_cat': '強風', 'penalty': 5},
            {'venue': '20', 'wind_dir': '東', 'wind_cat': '微風', 'penalty': 4},
        ]

    def calculate_penalty(self, row):
        """
        各レースの減点ポイントを計算

        Returns:
            int: 減点ポイント（累積）
        """
        total_penalty = 0
        applied = []

        venue = row['venue_code']
        time = categorize_time(row['race_time'])
        wind_dir = row['wind_direction']
        wind_cat = categorize_wind(row['wind_speed'])
        wave_cat = categorize_wave(row['wave_height'])
        weather = row['weather']

        for rule in self.rules:
            match = True

            # 条件チェック
            if 'venue' in rule and rule['venue'] != venue:
                match = False
            if 'time' in rule and rule['time'] != time:
                match = False
            if 'wind_dir' in rule and rule['wind_dir'] != wind_dir:
                match = False
            if 'wind_cat' in rule and rule['wind_cat'] != wind_cat:
                match = False
            if 'wave' in rule and rule['wave'] != wave_cat:
                match = False
            if 'weather' in rule and rule['weather'] != weather:
                match = False

            if match:
                total_penalty += rule['penalty']
                applied.append(rule)

        return total_penalty, applied


def load_data(year='2025', prediction_type='before'):
    """指定年・予測タイプのデータをロード"""
    conn = sqlite3.connect(str(DB_PATH))

    query = """
    SELECT
        p.race_id,
        p.pit_number,
        p.rank_prediction,
        p.total_score,
        r.venue_code,
        r.race_date,
        r.race_time,
        r.race_number,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,
        res.rank as actual_rank
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN race_conditions rc ON p.race_id = rc.race_id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    WHERE p.prediction_type = ?
      AND p.confidence = 'B'
      AND r.race_date LIKE ?
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    ORDER BY p.race_id, p.rank_prediction
    """

    df = pd.read_sql_query(query, conn, params=(prediction_type, f'{year}%'))
    conn.close()

    return df


def main():
    import argparse
    parser = argparse.ArgumentParser(description='減点システム効果検証')
    parser.add_argument('--year', type=str, default='2025', help='検証年（2024 or 2025）')
    parser.add_argument('--type', type=str, default='before', choices=['advance', 'before'], help='予測タイプ')
    args = parser.parse_args()

    print("=" * 100)
    print(f"減点システム効果検証（{args.year}年・{args.type}予測）")
    print("=" * 100)

    # データロード
    df = load_data(year=args.year, prediction_type=args.type)

    if len(df) == 0:
        print(f"\n[エラー] {args.year}年の{args.type}予測データが見つかりません")
        return

    # 1着予想のみ
    pred_1st = df[df['rank_prediction'] == 1].copy()

    print(f"\n【データ概要】")
    print(f"  総レース数: {len(pred_1st)}")

    # 減点システム初期化
    penalty_system = PenaltySystem()

    # 各レースに減点を適用
    penalties = []
    applied_rules_list = []

    for idx, row in pred_1st.iterrows():
        penalty, applied = penalty_system.calculate_penalty(row)
        penalties.append(penalty)
        applied_rules_list.append(applied)

    pred_1st['penalty'] = penalties
    pred_1st['adjusted_score'] = pred_1st['total_score'] - pred_1st['penalty']

    # 調整後の信頼度を計算
    def get_adjusted_confidence(score):
        if score >= 100:
            return 'B'
        elif score >= 80:
            return 'C'
        else:
            return 'D'

    pred_1st['adjusted_confidence'] = pred_1st['adjusted_score'].apply(get_adjusted_confidence)

    # ==========================================================================
    # 効果検証
    # ==========================================================================

    print("\n" + "=" * 100)
    print("【減点適用前後の比較】")
    print("=" * 100)

    # 全体的中率
    overall_hit_rate = (pred_1st['actual_rank'].astype(int) == 1).mean() * 100

    print(f"\n■ 減点適用前（全レース）")
    print(f"  件数: {len(pred_1st)}")
    print(f"  的中率: {overall_hit_rate:.2f}%")

    # 減点0のレース（減点ルール非適用）
    no_penalty = pred_1st[pred_1st['penalty'] == 0]
    no_penalty_hit = (no_penalty['actual_rank'].astype(int) == 1).mean() * 100 if len(no_penalty) > 0 else 0

    print(f"\n■ 減点0のレース（優良パターン）")
    print(f"  件数: {len(no_penalty)} ({len(no_penalty)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {no_penalty_hit:.2f}%")

    # 減点1-3のレース
    low_penalty = pred_1st[(pred_1st['penalty'] >= 1) & (pred_1st['penalty'] <= 3)]
    low_penalty_hit = (low_penalty['actual_rank'].astype(int) == 1).mean() * 100 if len(low_penalty) > 0 else 0

    print(f"\n■ 減点1-3のレース（軽度注意）")
    print(f"  件数: {len(low_penalty)} ({len(low_penalty)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {low_penalty_hit:.2f}%")
    print(f"  差分: {low_penalty_hit - overall_hit_rate:+.2f}pt")

    # 減点4-6のレース
    mid_penalty = pred_1st[(pred_1st['penalty'] >= 4) & (pred_1st['penalty'] <= 6)]
    mid_penalty_hit = (mid_penalty['actual_rank'].astype(int) == 1).mean() * 100 if len(mid_penalty) > 0 else 0

    print(f"\n■ 減点4-6のレース（中度注意）")
    print(f"  件数: {len(mid_penalty)} ({len(mid_penalty)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {mid_penalty_hit:.2f}%")
    print(f"  差分: {mid_penalty_hit - overall_hit_rate:+.2f}pt")

    # 減点7以上のレース
    high_penalty = pred_1st[pred_1st['penalty'] >= 7]
    high_penalty_hit = (high_penalty['actual_rank'].astype(int) == 1).mean() * 100 if len(high_penalty) > 0 else 0

    print(f"\n■ 減点7以上のレース（高度危険）")
    print(f"  件数: {len(high_penalty)} ({len(high_penalty)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {high_penalty_hit:.2f}%")
    print(f"  差分: {high_penalty_hit - overall_hit_rate:+.2f}pt")

    # ==========================================================================
    # 調整後信頼度別の分析
    # ==========================================================================

    print("\n" + "=" * 100)
    print("【調整後信頼度別の分析】")
    print("=" * 100)

    # 信頼度B維持（調整後スコア100以上）
    adjusted_b = pred_1st[pred_1st['adjusted_confidence'] == 'B']
    adjusted_b_hit = (adjusted_b['actual_rank'].astype(int) == 1).mean() * 100 if len(adjusted_b) > 0 else 0

    print(f"\n■ 調整後も信頼度B（スコア100以上）")
    print(f"  件数: {len(adjusted_b)} ({len(adjusted_b)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {adjusted_b_hit:.2f}%")
    print(f"  改善幅: {adjusted_b_hit - overall_hit_rate:+.2f}pt")

    # 信頼度C格下げ（調整後スコア80-99）
    adjusted_c = pred_1st[pred_1st['adjusted_confidence'] == 'C']
    adjusted_c_hit = (adjusted_c['actual_rank'].astype(int) == 1).mean() * 100 if len(adjusted_c) > 0 else 0

    print(f"\n■ 信頼度C格下げ（スコア80-99）")
    print(f"  件数: {len(adjusted_c)} ({len(adjusted_c)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {adjusted_c_hit:.2f}%")
    print(f"  差分: {adjusted_c_hit - overall_hit_rate:+.2f}pt")

    # 信頼度D格下げ（調整後スコア80未満）
    adjusted_d = pred_1st[pred_1st['adjusted_confidence'] == 'D']
    adjusted_d_hit = (adjusted_d['actual_rank'].astype(int) == 1).mean() * 100 if len(adjusted_d) > 0 else 0

    print(f"\n■ 信頼度D格下げ（スコア80未満）- 投票対象外推奨")
    print(f"  件数: {len(adjusted_d)} ({len(adjusted_d)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {adjusted_d_hit:.2f}%")
    print(f"  差分: {adjusted_d_hit - overall_hit_rate:+.2f}pt")

    # ==========================================================================
    # フィルタリング効果の検証
    # ==========================================================================

    print("\n" + "=" * 100)
    print("【フィルタリング効果】")
    print("=" * 100)

    # パターン1: 調整後D（スコア80未満）を除外
    filter1 = pred_1st[pred_1st['adjusted_confidence'] != 'D']
    filter1_hit = (filter1['actual_rank'].astype(int) == 1).mean() * 100

    print(f"\n■ パターン1: 調整後D（スコア80未満）を除外")
    print(f"  残りレース数: {len(filter1)} ({len(filter1)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {filter1_hit:.2f}%")
    print(f"  改善幅: {filter1_hit - overall_hit_rate:+.2f}pt ({(filter1_hit - overall_hit_rate) / overall_hit_rate * 100:+.1f}%)")

    # パターン2: 調整後C・D（スコア100未満）を除外
    filter2 = pred_1st[pred_1st['adjusted_confidence'] == 'B']
    filter2_hit = (filter2['actual_rank'].astype(int) == 1).mean() * 100

    print(f"\n■ パターン2: 調整後B（スコア100以上）のみ")
    print(f"  残りレース数: {len(filter2)} ({len(filter2)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {filter2_hit:.2f}%")
    print(f"  改善幅: {filter2_hit - overall_hit_rate:+.2f}pt ({(filter2_hit - overall_hit_rate) / overall_hit_rate * 100:+.1f}%)")

    # パターン3: 減点7以上を除外
    filter3 = pred_1st[pred_1st['penalty'] < 7]
    filter3_hit = (filter3['actual_rank'].astype(int) == 1).mean() * 100

    print(f"\n■ パターン3: 減点7以上を除外")
    print(f"  残りレース数: {len(filter3)} ({len(filter3)/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {filter3_hit:.2f}%")
    print(f"  改善幅: {filter3_hit - overall_hit_rate:+.2f}pt ({(filter3_hit - overall_hit_rate) / overall_hit_rate * 100:+.1f}%)")

    # ==========================================================================
    # 減点分布の分析
    # ==========================================================================

    print("\n" + "=" * 100)
    print("【減点ポイント分布】")
    print("=" * 100)

    penalty_dist = pred_1st.groupby('penalty').agg({
        'race_id': 'count',
        'actual_rank': lambda x: (x.astype(int) == 1).mean() * 100
    }).round(2)
    penalty_dist.columns = ['件数', '的中率(%)']

    print(f"\n{'減点':>6s} | {'件数':>6s} | {'割合':>7s} | {'的中率':>8s} | {'差分':>7s}")
    print("-" * 60)

    for penalty_val in sorted(pred_1st['penalty'].unique()):
        subset = pred_1st[pred_1st['penalty'] == penalty_val]
        count = len(subset)
        ratio = count / len(pred_1st) * 100
        hit_rate = (subset['actual_rank'].astype(int) == 1).mean() * 100
        diff = hit_rate - overall_hit_rate

        print(f"{penalty_val:6d} | {count:6d} | {ratio:6.1f}% | {hit_rate:7.2f}% | {diff:+6.2f}pt")

    # ==========================================================================
    # 結論
    # ==========================================================================

    print("\n" + "=" * 100)
    print("【検証結果サマリー】")
    print("=" * 100)

    print(f"\n✅ 減点システムの有効性:")
    print(f"  - 減点0のレース: {no_penalty_hit:.2f}% （基準より{no_penalty_hit - overall_hit_rate:+.2f}pt）")
    print(f"  - 減点7以上のレース: {high_penalty_hit:.2f}% （基準より{high_penalty_hit - overall_hit_rate:+.2f}pt）")
    print(f"  → 減点ポイントと的中率の相関: {'あり' if high_penalty_hit < no_penalty_hit else 'なし'}")

    print(f"\n📊 最適フィルタリング戦略:")

    best_pattern = 1
    best_improvement = filter1_hit - overall_hit_rate
    best_races = len(filter1)
    best_hit = filter1_hit

    if filter2_hit - overall_hit_rate > best_improvement:
        best_pattern = 2
        best_improvement = filter2_hit - overall_hit_rate
        best_races = len(filter2)
        best_hit = filter2_hit

    if filter3_hit - overall_hit_rate > best_improvement:
        best_pattern = 3
        best_improvement = filter3_hit - overall_hit_rate
        best_races = len(filter3)
        best_hit = filter3_hit

    print(f"  最適パターン: パターン{best_pattern}")
    print(f"  残存レース: {best_races}件 ({best_races/len(pred_1st)*100:.1f}%)")
    print(f"  的中率: {best_hit:.2f}%")
    print(f"  改善幅: {best_improvement:+.2f}pt ({best_improvement / overall_hit_rate * 100:+.1f}%)")

    if best_improvement > 2.0:
        print(f"\n✅ 減点システムは有効です！")
        print(f"   的中率が{best_improvement:.2f}ポイント改善されます。")
    elif best_improvement > 0:
        print(f"\n⚠️  減点システムは小幅な改善効果があります。")
        print(f"   的中率が{best_improvement:.2f}ポイント改善されますが、効果は限定的です。")
    else:
        print(f"\n❌ 減点システムは効果がありません。")
        print(f"   的中率の改善が見られません。再検討が必要です。")

    print("\n" + "=" * 100)
    print("検証完了")
    print("=" * 100)


if __name__ == "__main__":
    main()
