"""
TJ-9: 展示タイム信頼性マップ市場効率性検証スクリプト

目的: 展示タイム情報が市場オッズに既に織り込まれているかを検証
方法: 会場別の展示タイム1位艇の平均オッズを比較

TJ-6（波高）、TJ-10（潮位）の失敗事例を踏まえ、
実装前に市場効率性を確認する。
"""

import sqlite3
from pathlib import Path
from typing import Dict, List
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))


def analyze_exhibition_time_market_efficiency(
    db_path: str = "data/boatrace.db",
    start_date: str = "2020-01-01",
    end_date: str = "2026-01-01"
):
    """
    展示タイムと市場オッズの相関を分析

    高信頼会場（徳山等）と低信頼会場（江戸川等）で、
    展示タイム1位艇のオッズに差があれば、市場が会場別信頼性を織り込んでいない。

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日
    """
    print("=" * 80)
    print("TJ-9: 展示タイム信頼性マップ市場効率性検証")
    print("=" * 80)
    print(f"対象期間: {start_date} ~ {end_date}")
    print()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ========================================
    # 1. 全体統計
    # ========================================
    print("【1. 全体統計】")
    print("-" * 80)

    cursor.execute("""
        SELECT
            COUNT(DISTINCT r.id) as total_races,
            COUNT(DISTINCT CASE WHEN rd.exhibition_time IS NOT NULL THEN r.id END) as races_with_exhibition,
            COUNT(DISTINCT rd.race_id) as total_details
        FROM races r
        LEFT JOIN race_details rd ON r.id = rd.race_id
        WHERE r.race_date BETWEEN ? AND ?
    """, (start_date, end_date))

    row = cursor.fetchone()
    print(f"総レース数: {row[0]:,}件")
    print(f"展示タイムありレース: {row[1]:,}件 ({row[1]/row[0]*100:.2f}%)")
    print(f"race_details総件数: {row[2]:,}件")
    print()

    # ========================================
    # 2. 会場別の展示タイム1位艇の平均オッズ
    # ========================================
    print("【2. 会場別の展示タイム1位艇の平均オッズ（trifecta_odds使用）】")
    print("-" * 80)
    print("※ 展示タイム1位艇を1着に含む3連単の平均オッズで期待オッズを推定")
    print()

    cursor.execute("""
        WITH exhibition_rank AS (
            SELECT
                rd.race_id,
                rd.pit_number,
                rd.exhibition_time,
                ROW_NUMBER() OVER (
                    PARTITION BY rd.race_id
                    ORDER BY rd.exhibition_time ASC
                ) as exhibition_rank
            FROM race_details rd
            WHERE rd.exhibition_time IS NOT NULL
        ),
        pit1_odds_by_venue AS (
            SELECT
                r.venue_code,
                r.id as race_id,
                er.pit_number as pit1_number,
                AVG(t.odds) as avg_pit1_odds,
                COUNT(DISTINCT t.combination) as odds_count
            FROM races r
            JOIN exhibition_rank er ON r.id = er.race_id AND er.exhibition_rank = 1
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date BETWEEN ? AND ?
                AND t.combination LIKE CAST(er.pit_number AS TEXT) || '-%'
            GROUP BY r.venue_code, r.id, er.pit_number
            HAVING COUNT(DISTINCT t.combination) >= 10
        )
        SELECT
            venue_code,
            COUNT(*) as race_count,
            AVG(avg_pit1_odds) as avg_odds,
            MIN(avg_pit1_odds) as min_odds,
            MAX(avg_pit1_odds) as max_odds
        FROM pit1_odds_by_venue
        GROUP BY venue_code
        ORDER BY venue_code
    """, (start_date, end_date))

    rows = cursor.fetchall()

    venue_odds_map = {}
    print(f"{'会場':>6} {'レース数':>10} {'平均オッズ':>12} {'最小オッズ':>12} {'最大オッズ':>12}")
    print("-" * 80)

    for row in rows:
        venue, count, avg_odds, min_odds, max_odds = row
        venue_odds_map[venue] = avg_odds
        print(f"{venue:>6} {count:>10,}件 {avg_odds:>11.2f}倍 {min_odds:>11.2f}倍 {max_odds:>11.2f}倍")

    print()

    # ========================================
    # 3. Explore agentの信頼性ランキングとの比較
    # ========================================
    print("【3. 会場別信頼性ランキング vs オッズの関係】")
    print("-" * 80)
    print("※ Explore agentの分析: 展示1位と6位の勝率差で信頼性を評価")
    print()

    # Explore agentの信頼性ランキング（勝率差の大きい順）
    high_reliability_venues = ['18', '07', '12', '15', '13', '22']  # 徳山、蒲郡、住之江、丸亀、尼崎、福岡
    low_reliability_venues = ['03']  # 江戸川

    high_reliability_odds = [venue_odds_map.get(v, None) for v in high_reliability_venues if v in venue_odds_map]
    low_reliability_odds = [venue_odds_map.get(v, None) for v in low_reliability_venues if v in venue_odds_map]

    print(f"{'カテゴリ':<20} {'会場数':>10} {'平均オッズ':>12}")
    print("-" * 80)

    if high_reliability_odds:
        avg_high = sum(high_reliability_odds) / len(high_reliability_odds)
        print(f"{'高信頼性会場':<20} {len(high_reliability_odds):>10}会場 {avg_high:>11.2f}倍")
    else:
        avg_high = None
        print(f"{'高信頼性会場':<20} {'データなし':>10}")

    if low_reliability_odds:
        avg_low = sum(low_reliability_odds) / len(low_reliability_odds)
        print(f"{'低信頼性会場':<20} {len(low_reliability_odds):>10}会場 {avg_low:>11.2f}倍")
    else:
        avg_low = None
        print(f"{'低信頼性会場':<20} {'データなし':>10}")

    print()

    # ========================================
    # 4. 市場効率性の判定
    # ========================================
    print("【4. 市場効率性の判定】")
    print("-" * 80)

    if avg_high is not None and avg_low is not None:
        odds_diff_pct = (avg_high - avg_low) / avg_low * 100
        print(f"高信頼性会場平均: {avg_high:.2f}倍")
        print(f"低信頼性会場平均: {avg_low:.2f}倍")
        print(f"オッズ差: {odds_diff_pct:+.2f}%")
        print()

        if odds_diff_pct >= 5.0:
            print("[OK] **市場効率性: 低い（実装の価値あり）**")
            print(f"   -> 高信頼会場で展示タイム1位艇のオッズが{odds_diff_pct:+.2f}%高い")
            print("   -> 市場は会場別の展示タイム信頼性を十分織り込んでいない")
            print("   -> 会場別信頼性係数の実装を推奨")
        elif odds_diff_pct >= 2.0:
            print("[注意] **市場効率性: 中程度（慎重に実装検討）**")
            print(f"   -> 高信頼会場で展示タイム1位艇のオッズが{odds_diff_pct:+.2f}%高い")
            print("   -> 市場は会場別信頼性を部分的に織り込んでいる")
            print("   -> Tier 1テストで効果を確認後、実装判断")
        elif abs(odds_diff_pct) < 2.0:
            print("[NG] **市場効率性: 高い（実装不要）**")
            print(f"   -> 高信頼会場と低信頼会場でオッズ差は{odds_diff_pct:+.2f}%のみ")
            print("   -> 市場は既に会場別の展示タイム信頼性を織り込んでいる")
            print("   -> TJ-6（波高）、TJ-10（潮位）と同様、効果なしの可能性が高い")
        else:
            print("[NG] **市場効率性: 高い（逆方向）**")
            print(f"   -> 低信頼会場の方がオッズが{-odds_diff_pct:+.2f}%高い（逆転）")
            print("   -> 市場は既に会場別の展示タイム信頼性を織り込んでいる")
            print("   -> 実装不要")
    else:
        print("[注意] データ不足により判定不可")

    print()

    # ========================================
    # 5. 会場別詳細（参考）
    # ========================================
    print("【5. 会場別詳細（Explore agentの信頼性順）】")
    print("-" * 80)

    # Explore agentの信頼性データ（勝率差）
    venue_reliability = {
        '18': {'name': '徳山', 'win_rate_diff': 24.87},
        '07': {'name': '蒲郡', 'win_rate_diff': 21.52},
        '12': {'name': '住之江', 'win_rate_diff': 21.46},
        '15': {'name': '丸亀', 'win_rate_diff': 21.27},
        '13': {'name': '尼崎', 'win_rate_diff': 20.78},
        '22': {'name': '福岡', 'win_rate_diff': 20.01},
        '03': {'name': '江戸川', 'win_rate_diff': 12.03},
    }

    print(f"{'会場':>6} {'会場名':<10} {'信頼性':>10} {'レース数':>10} {'平均オッズ':>12}")
    print("-" * 80)

    for venue_code in sorted(venue_reliability.keys(), key=lambda v: venue_reliability[v]['win_rate_diff'], reverse=True):
        venue_data = venue_reliability[venue_code]
        odds = venue_odds_map.get(venue_code, None)

        # レース数を取得
        cursor.execute("""
            SELECT COUNT(*) FROM (
                SELECT r.id
                FROM races r
                JOIN race_details rd ON r.id = rd.race_id
                WHERE r.venue_code = ?
                    AND r.race_date BETWEEN ? AND ?
                    AND rd.exhibition_time IS NOT NULL
                GROUP BY r.id
            )
        """, (venue_code, start_date, end_date))
        race_count = cursor.fetchone()[0]

        reliability_star = "★" * int(venue_data['win_rate_diff'] / 5)

        if odds:
            print(f"{venue_code:>6} {venue_data['name']:<10} {reliability_star:<10} {race_count:>10,}件 {odds:>11.2f}倍")
        else:
            print(f"{venue_code:>6} {venue_data['name']:<10} {reliability_star:<10} {race_count:>10,}件 {'データなし':>12}")

    print()

    conn.close()

    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    analyze_exhibition_time_market_efficiency()
