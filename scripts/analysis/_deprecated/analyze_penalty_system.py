# -*- coding: utf-8 -*-
"""
信頼度B 環境要因減点システム分析

除外ではなく、環境要因ごとの減点値を算出
的中率の低下度合いに応じて適切な減点ポイントを決定
"""

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from collections import defaultdict
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


def load_2025_confidence_b_data():
    """2025年BEFORE予測信頼度Bデータをロード"""
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
        r.race_grade,
        r.is_nighter,
        rc.weather,
        rc.wind_direction,
        rc.wind_speed,
        rc.wave_height,
        rc.temperature,
        res.rank as actual_rank,
        vd.course_1_win_rate,
        vs.tide_impact
    FROM race_predictions p
    JOIN races r ON p.race_id = r.id
    LEFT JOIN race_conditions rc ON p.race_id = rc.race_id
    LEFT JOIN results res ON p.race_id = res.race_id AND p.pit_number = res.pit_number
    LEFT JOIN venue_data vd ON r.venue_code = vd.venue_code
    LEFT JOIN venue_strategies vs ON r.venue_code = vs.venue_code
    WHERE p.prediction_type = 'before'
      AND p.confidence = 'B'
      AND r.race_date LIKE '2025%'
      AND res.rank IS NOT NULL
      AND res.is_invalid = 0
    ORDER BY p.race_id, p.rank_prediction
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    # カテゴリ追加
    df['time_category'] = df['race_time'].apply(categorize_time)
    df['wind_category'] = df['wind_speed'].apply(categorize_wind)
    df['wave_category'] = df['wave_height'].apply(categorize_wave)

    return df


def calculate_hit_rate_impact(df, condition_filter, baseline_rate):
    """
    特定条件下での的中率と基準的中率との差分を計算

    Args:
        df: 全データ
        condition_filter: 条件フィルタ（bool Series）
        baseline_rate: 基準的中率

    Returns:
        dict: サンプル数、的中率、差分、減点ポイント
    """
    subset = df[condition_filter]

    if len(subset) == 0:
        return None

    # 1着予想のみ
    pred_1st = subset[subset['rank_prediction'] == 1]

    if len(pred_1st) < 5:  # サンプル数最低5件
        return None

    # actual_rankをintに変換して比較
    hit_rate = (pred_1st['actual_rank'].astype(int) == 1).mean() * 100
    diff = baseline_rate - hit_rate

    # 減点ポイントの計算
    # 的中率が10%下がるごとに2ポイント減点
    penalty = max(0, int(diff / 5))  # 5%で1ポイント

    return {
        'sample_size': len(pred_1st),
        'hit_rate': hit_rate,
        'diff': diff,
        'penalty': penalty
    }


def main():
    print("=" * 100)
    print("信頼度B 環境要因減点システム分析")
    print("=" * 100)

    # データロード
    df = load_2025_confidence_b_data()

    # 1着予想のみで全体的中率を算出（基準値）
    pred_1st = df[df['rank_prediction'] == 1]
    baseline_hit_rate = (pred_1st['actual_rank'].astype(int) == 1).mean() * 100

    print(f"\n【基準値】")
    print(f"  総レース数: {len(pred_1st)}")
    print(f"  全体的中率: {baseline_hit_rate:.2f}%")
    print(f"  （この的中率を100として、各条件での低下度合いを減点ポイントに変換）")

    print("\n" + "=" * 100)
    print("【環境要因別 減点ポイント算出】")
    print("=" * 100)

    penalty_rules = []

    # =============================================================================
    # 1. 会場別（1コース勝率低い会場）
    # =============================================================================
    print("\n■ 会場要因（1コース勝率）")
    print("-" * 100)
    print(f"{'会場':8s} | {'1C勝率':>8s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    for venue_code in sorted(df['venue_code'].unique()):
        venue_data = df[df['venue_code'] == venue_code]
        course1_rate = venue_data['course_1_win_rate'].iloc[0] if len(venue_data) > 0 else None

        result = calculate_hit_rate_impact(df, df['venue_code'] == venue_code, baseline_hit_rate)

        if result and result['sample_size'] >= 10:
            venue_name = VENUE_NAMES.get(venue_code, venue_code)

            # 1コース勝率が47%未満の会場のみ減点対象
            if course1_rate and course1_rate < 47:
                penalty_rules.append({
                    'category': '会場',
                    'condition': f"venue_code == '{venue_code}'",
                    'description': f"{venue_name}（1C勝率{course1_rate:.1f}%）",
                    'penalty': result['penalty'],
                    'hit_rate': result['hit_rate'],
                    'sample_size': result['sample_size']
                })

            print(f"{venue_name:8s} | {course1_rate:7.1f}% | {result['sample_size']:6d} | "
                  f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 2. 会場×時間帯×風速×風向（複合要因）
    # =============================================================================
    print("\n■ 会場×時間帯×風速×風向要因（4要因複合分析）")
    print("-" * 100)
    print(f"{'会場':8s} | {'時間':6s} | {'風向':6s} | {'風速':6s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    # 特定会場のみ分析（戸田、江戸川、平和島）
    target_venues = ['02', '03', '04']

    # まず風向を取得
    wind_directions = df['wind_direction'].dropna().unique()

    for venue_code in target_venues:
        venue_name = VENUE_NAMES.get(venue_code, venue_code)

        for time_cat in ['早朝', '午前', '午後', '夕方']:
            for wind_dir in sorted(wind_directions):
                for wind_cat in ['無風', '微風', '強風', '暴風']:
                    condition = (df['venue_code'] == venue_code) & \
                               (df['time_category'] == time_cat) & \
                               (df['wind_direction'] == wind_dir) & \
                               (df['wind_category'] == wind_cat)
                    result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

                    if result and result['sample_size'] >= 5:  # 複合条件は5件以上
                        # 減点が発生する場合のみルールに追加
                        if result['penalty'] > 0:
                            penalty_rules.append({
                                'category': '会場×時間×風向×風速',
                                'condition': f"venue_code == '{venue_code}' and time_category == '{time_cat}' and wind_direction == '{wind_dir}' and wind_category == '{wind_cat}'",
                                'description': f"{venue_name}×{time_cat}×{wind_dir}×{wind_cat}",
                                'penalty': result['penalty'],
                                'hit_rate': result['hit_rate'],
                                'sample_size': result['sample_size']
                            })

                        print(f"{venue_name:8s} | {time_cat:6s} | {wind_dir:6s} | {wind_cat:6s} | {result['sample_size']:6d} | "
                              f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 2-2. 会場×時間帯（シンプル版）
    # =============================================================================
    print("\n■ 会場×時間帯要因（シンプル集計）")
    print("-" * 100)
    print(f"{'会場':8s} | {'時間帯':8s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    for venue_code in target_venues:
        for time_cat in ['早朝', '午前', '午後', '夕方']:
            condition = (df['venue_code'] == venue_code) & (df['time_category'] == time_cat)
            result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

            if result:
                venue_name = VENUE_NAMES.get(venue_code, venue_code)

                # 減点が発生する場合のみルールに追加
                if result['penalty'] > 0:
                    penalty_rules.append({
                        'category': '会場×時間帯',
                        'condition': f"venue_code == '{venue_code}' and time_category == '{time_cat}'",
                        'description': f"{venue_name}×{time_cat}",
                        'penalty': result['penalty'],
                        'hit_rate': result['hit_rate'],
                        'sample_size': result['sample_size']
                    })

                print(f"{venue_name:8s} | {time_cat:8s} | {result['sample_size']:6d} | "
                      f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 3. 風速×風向要因
    # =============================================================================
    print("\n■ 風速×風向要因")
    print("-" * 100)
    print(f"{'風向':10s} | {'風速':10s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    # 風向を取得（NULLでない）
    wind_directions = df['wind_direction'].dropna().unique()

    for wind_dir in sorted(wind_directions):
        for wind_cat in ['無風', '微風', '強風', '暴風']:
            condition = (df['wind_direction'] == wind_dir) & (df['wind_category'] == wind_cat)
            result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

            if result and result['sample_size'] >= 10:
                if result['penalty'] > 0:
                    penalty_rules.append({
                        'category': '風速×風向',
                        'condition': f"wind_direction == '{wind_dir}' and wind_category == '{wind_cat}'",
                        'description': f"{wind_dir}×{wind_cat}",
                        'penalty': result['penalty'],
                        'hit_rate': result['hit_rate'],
                        'sample_size': result['sample_size']
                    })

                print(f"{wind_dir:10s} | {wind_cat:10s} | {result['sample_size']:6d} | "
                      f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # 向かい風の特殊分析
    print("\n  [向かい風の詳細分析]")
    headwind_df = df[df['wind_direction'].str.contains('向', na=False)]

    if len(headwind_df) >= 10:
        for wind_cat in ['微風', '強風', '暴風']:
            condition = (df['wind_direction'].str.contains('向', na=False)) & (df['wind_category'] == wind_cat)
            result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

            if result and result['sample_size'] >= 5:
                if result['penalty'] > 0:
                    penalty_rules.append({
                        'category': '風速×風向',
                        'condition': f"wind_direction.contains('向') and wind_category == '{wind_cat}'",
                        'description': f"向かい風×{wind_cat}",
                        'penalty': result['penalty'],
                        'hit_rate': result['hit_rate'],
                        'sample_size': result['sample_size']
                    })

                print(f"  {'向かい風':10s} | {wind_cat:10s} | {result['sample_size']:6d} | "
                      f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 4. 会場×風速×風向（潮位影響会場）
    # =============================================================================
    print("\n■ 会場×風速×風向要因（潮位影響会場）")
    print("-" * 100)
    print(f"{'会場':8s} | {'風向':10s} | {'風速':10s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    # 潮位影響がある会場のみ（tide_impact > 0）
    tide_venues = df[df['tide_impact'] > 0]['venue_code'].unique()

    for venue_code in tide_venues:
        venue_name = VENUE_NAMES.get(venue_code, venue_code)

        for wind_dir in sorted(wind_directions):
            for wind_cat in ['微風', '強風', '暴風']:
                condition = (df['venue_code'] == venue_code) & \
                           (df['wind_direction'] == wind_dir) & \
                           (df['wind_category'] == wind_cat)
                result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

                if result and result['sample_size'] >= 5:  # 潮位影響会場は5件以上で判断
                    if result['penalty'] > 0:
                        penalty_rules.append({
                            'category': '会場×風速×風向',
                            'condition': f"venue_code == '{venue_code}' and wind_direction == '{wind_dir}' and wind_category == '{wind_cat}'",
                            'description': f"{venue_name}×{wind_dir}×{wind_cat}",
                            'penalty': result['penalty'],
                            'hit_rate': result['hit_rate'],
                            'sample_size': result['sample_size']
                        })

                    print(f"{venue_name:8s} | {wind_dir:10s} | {wind_cat:10s} | {result['sample_size']:6d} | "
                          f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 5. 波高要因
    # =============================================================================
    print("\n■ 波高要因")
    print("-" * 100)
    print(f"{'波高':10s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    for wave_cat in ['穏やか', '小波', '中波', '大波']:
        condition = df['wave_category'] == wave_cat
        result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

        if result and result['sample_size'] >= 10:
            if result['penalty'] > 0:
                penalty_rules.append({
                    'category': '波高',
                    'condition': f"wave_category == '{wave_cat}'",
                    'description': f"{wave_cat}",
                    'penalty': result['penalty'],
                    'hit_rate': result['hit_rate'],
                    'sample_size': result['sample_size']
                })

            print(f"{wave_cat:10s} | {result['sample_size']:6d} | "
                  f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 6. 天候要因
    # =============================================================================
    print("\n■ 天候要因")
    print("-" * 100)
    print(f"{'天候':10s} | {'件数':>6s} | {'的中率':>8s} | {'差分':>7s} | {'減点':>6s}")
    print("-" * 100)

    for weather in df['weather'].dropna().unique():
        condition = df['weather'] == weather
        result = calculate_hit_rate_impact(df, condition, baseline_hit_rate)

        if result:
            if result['penalty'] > 0 and result['sample_size'] >= 5:
                penalty_rules.append({
                    'category': '天候',
                    'condition': f"weather == '{weather}'",
                    'description': f"{weather}",
                    'penalty': result['penalty'],
                    'hit_rate': result['hit_rate'],
                    'sample_size': result['sample_size']
                })

            print(f"{weather:10s} | {result['sample_size']:6d} | "
                  f"{result['hit_rate']:7.2f}% | {result['diff']:+6.2f}pt | {result['penalty']:6d}pt")

    # =============================================================================
    # 減点ルールサマリー
    # =============================================================================
    print("\n" + "=" * 100)
    print("【減点ルール一覧（減点ポイント降順）】")
    print("=" * 100)

    penalty_rules_sorted = sorted(penalty_rules, key=lambda x: x['penalty'], reverse=True)

    print(f"\n{'カテゴリ':12s} | {'条件':40s} | {'減点':>6s} | {'的中率':>8s} | {'件数':>6s}")
    print("-" * 100)

    for rule in penalty_rules_sorted:
        if rule['penalty'] >= 1:  # 1ポイント以上のみ表示
            print(f"{rule['category']:12s} | {rule['description']:40s} | "
                  f"{rule['penalty']:6d}pt | {rule['hit_rate']:7.2f}% | {rule['sample_size']:6d}")

    # =============================================================================
    # 実装例の出力
    # =============================================================================
    print("\n" + "=" * 100)
    print("【減点システム実装例】")
    print("=" * 100)

    print("""
class ConfidenceBPenaltySystem:
    \"\"\"
    信頼度B環境要因減点システム

    各環境要因に対して減点ポイントを適用し、
    最終スコアを調整する
    \"\"\"

    def __init__(self):
        # 減点ルール定義（上記分析結果から自動生成）
        self.penalty_rules = [
""")

    for rule in penalty_rules_sorted[:10]:  # 上位10個のみ
        print(f"            {{'category': '{rule['category']}', "
              f"'condition': '{rule['condition']}', "
              f"'penalty': {rule['penalty']}}},")

    print("""        ]

    def calculate_penalty(self, venue_code, race_time, wind_speed, wave_height, weather, tide_impact):
        \"\"\"
        環境要因から減点ポイントを算出

        Returns:
            int: 減点ポイント（累積）
        \"\"\"
        total_penalty = 0
        applied_rules = []

        # 時間帯カテゴリ化
        time_category = self._categorize_time(race_time)
        wind_category = self._categorize_wind(wind_speed)
        wave_category = self._categorize_wave(wave_height)

        # 各ルールを評価
        for rule in self.penalty_rules:
            # 条件評価（簡易実装）
            if self._evaluate_condition(rule['condition'], venue_code, time_category,
                                        wind_category, wave_category, weather):
                total_penalty += rule['penalty']
                applied_rules.append(rule)

        return total_penalty, applied_rules

    def adjust_confidence_score(self, original_score, penalty):
        \"\"\"
        元のスコアから減点を適用

        Args:
            original_score: 元の信頼度スコア
            penalty: 減点ポイント

        Returns:
            adjusted_score: 調整後スコア
            new_confidence: 調整後信頼度（B/C/D）
        \"\"\"
        adjusted_score = original_score - penalty

        # 信頼度再判定
        if adjusted_score >= 100:
            new_confidence = 'B'
        elif adjusted_score >= 80:
            new_confidence = 'C'
        else:
            new_confidence = 'D'  # または投票対象外

        return adjusted_score, new_confidence
""")

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)

    print(f"\n[要約]")
    print(f"  - 基準的中率: {baseline_hit_rate:.2f}%")
    print(f"  - 減点ルール数: {len([r for r in penalty_rules if r['penalty'] >= 1])}件")
    print(f"  - 最大減点ポイント: {max([r['penalty'] for r in penalty_rules])}pt")
    print(f"  - 減点適用により、低的中率パターンを信頼度C/Dに格下げ可能")


if __name__ == "__main__":
    main()
