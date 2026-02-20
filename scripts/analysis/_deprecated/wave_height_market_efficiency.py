"""
TJ-6: 波高フィルター市場効率性検証スクリプト

目的: 波高情報が市場オッズに既に織り込まれているかを検証
方法: 高波高時（10cm以上）vs 通常時の1号艇期待オッズを比較

TideAdjuster（TJ-10）の失敗事例（ROI±0.0pt）を回避するため、
実装前に市場効率性を確認する。
"""

import sqlite3
from pathlib import Path
from typing import Dict, List
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))


def analyze_wave_height_market_efficiency(
    db_path: str = "data/boatrace.db",
    start_date: str = "2020-01-01",
    end_date: str = "2026-01-01"
):
    """
    波高とオッズの相関を分析

    高波高時（10cm以上）に1号艇のオッズが高騰していれば、
    市場が波高情報を織り込んでいない（実装の価値あり）

    Args:
        db_path: データベースパス
        start_date: 開始日
        end_date: 終了日
    """
    print("=" * 80)
    print("TJ-6: 波高フィルター市場効率性検証")
    print("=" * 80)
    print(f"対象期間: {start_date} ～ {end_date}")
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
            COUNT(*) as total_races,
            COUNT(DISTINCT r.id) as races_with_conditions,
            SUM(CASE WHEN rc.wave_height IS NOT NULL THEN 1 ELSE 0 END) as wave_data_count,
            SUM(CASE WHEN rc.wave_height >= 10 THEN 1 ELSE 0 END) as high_wave_count
        FROM races r
        LEFT JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date BETWEEN ? AND ?
    """, (start_date, end_date))

    row = cursor.fetchone()
    print(f"総レース数: {row[0]:,}件")
    print(f"race_conditions件数: {row[1]:,}件")
    print(f"波高データ件数: {row[2]:,}件 ({row[2]/row[0]*100:.2f}%)")
    print(f"高波高レース（10cm以上）: {row[3]:,}件 ({row[3]/row[0]*100:.2f}%)")
    print()

    # ========================================
    # 2. 波高帯別の1号艇オッズ平均（trifecta_odds使用）
    # ========================================
    print("【2. 波高帯別の1号艇期待オッズ（trifecta_odds使用）】")
    print("-" * 80)
    print("※ 1-X-X組み合わせの平均オッズで1号艇期待オッズを推定")
    print()

    cursor.execute("""
        WITH pit1_odds AS (
            SELECT
                r.id as race_id,
                r.race_date,
                r.venue_code,
                rc.wave_height,
                CASE
                    WHEN rc.wave_height IS NULL THEN 'NULL'
                    WHEN rc.wave_height = 0 THEN '0cm（無波）'
                    WHEN rc.wave_height <= 2 THEN '1-2cm（低波）'
                    WHEN rc.wave_height <= 5 THEN '3-5cm（中波）'
                    WHEN rc.wave_height <= 9 THEN '6-9cm（高波）'
                    ELSE '10cm+（超高波）'
                END as wave_category,
                AVG(t.odds) as avg_pit1_odds,
                COUNT(DISTINCT t.combination) as odds_count
            FROM races r
            LEFT JOIN race_conditions rc ON r.id = rc.race_id
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date BETWEEN ? AND ?
                AND t.combination LIKE '1-%'  -- 1号艇が1着の組み合わせ
            GROUP BY r.id, r.race_date, r.venue_code, rc.wave_height
            HAVING COUNT(DISTINCT t.combination) >= 10  -- 最低10組み合わせ以上
        )
        SELECT
            wave_category,
            COUNT(*) as race_count,
            AVG(avg_pit1_odds) as avg_odds,
            MIN(avg_pit1_odds) as min_odds,
            MAX(avg_pit1_odds) as max_odds,
            AVG(avg_pit1_odds) * 1.0 / (SELECT AVG(avg_pit1_odds) FROM pit1_odds WHERE wave_category = '1-2cm（低波）') as relative_odds
        FROM pit1_odds
        GROUP BY wave_category
        ORDER BY
            CASE wave_category
                WHEN 'NULL' THEN 0
                WHEN '0cm（無波）' THEN 1
                WHEN '1-2cm（低波）' THEN 2
                WHEN '3-5cm（中波）' THEN 3
                WHEN '6-9cm（高波）' THEN 4
                WHEN '10cm+（超高波）' THEN 5
            END
    """, (start_date, end_date))

    rows = cursor.fetchall()

    print(f"{'波高帯':<20} {'レース数':>10} {'平均オッズ':>12} {'最小オッズ':>12} {'最大オッズ':>12} {'相対倍率':>12}")
    print("-" * 80)

    baseline_odds = None
    high_wave_odds = None

    for row in rows:
        wave_cat, count, avg_odds, min_odds, max_odds, relative = row
        print(f"{wave_cat:<20} {count:>10,}件 {avg_odds:>11.2f}倍 {min_odds:>11.2f}倍 {max_odds:>11.2f}倍 {relative:>11.2f}x")

        if wave_cat == '1-2cm（低波）':
            baseline_odds = avg_odds
        elif wave_cat == '10cm+（超高波）':
            high_wave_odds = avg_odds

    print()

    # ========================================
    # 3. 市場効率性の判定
    # ========================================
    print("【3. 市場効率性の判定】")
    print("-" * 80)

    if baseline_odds and high_wave_odds:
        odds_diff_pct = (high_wave_odds - baseline_odds) / baseline_odds * 100
        print(f"ベースライン（1-2cm低波）: {baseline_odds:.2f}倍")
        print(f"超高波高（10cm以上）: {high_wave_odds:.2f}倍")
        print(f"オッズ差: {odds_diff_pct:+.2f}%")
        print()

        if odds_diff_pct >= 5.0:
            print("[OK] **市場効率性: 低い（実装の価値あり）**")
            print(f"   -> 高波高時に1号艇オッズが{odds_diff_pct:+.2f}%高騰")
            print("   -> 波高情報は市場オッズに十分織り込まれていない")
            print("   -> 波高フィルター実装を推奨")
        elif odds_diff_pct >= 2.0:
            print("[注意] **市場効率性: 中程度（慎重に実装検討）**")
            print(f"   -> 高波高時に1号艇オッズが{odds_diff_pct:+.2f}%変化")
            print("   -> 波高情報は部分的に織り込まれている")
            print("   -> Tier 1テストで効果を確認後、実装判断")
        else:
            print("[NG] **市場効率性: 高い（実装不要）**")
            print(f"   -> 高波高時でも1号艇オッズの変化は{odds_diff_pct:+.2f}%のみ")
            print("   -> 波高情報は既に市場オッズに織り込み済み")
            print("   -> TJ-10（潮位）と同様、効果なしの可能性が高い")
    else:
        print("[注意] データ不足により判定不可")

    print()

    # ========================================
    # 4. 会場別の波高影響（海水会場のみ）
    # ========================================
    print("【4. 会場別の波高影響（海水会場、高波高10件以上のみ）】")
    print("-" * 80)

    cursor.execute("""
        WITH pit1_odds AS (
            SELECT
                r.venue_code,
                rc.wave_height,
                CASE
                    WHEN rc.wave_height >= 10 THEN 'high'
                    ELSE 'normal'
                END as wave_level,
                AVG(t.odds) as avg_pit1_odds
            FROM races r
            JOIN race_conditions rc ON r.id = rc.race_id
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date BETWEEN ? AND ?
                AND t.combination LIKE '1-%'
                AND rc.wave_height IS NOT NULL
            GROUP BY r.id, r.venue_code, rc.wave_height
            HAVING COUNT(DISTINCT t.combination) >= 10
        )
        SELECT
            venue_code,
            COUNT(CASE WHEN wave_level = 'normal' THEN 1 END) as normal_count,
            AVG(CASE WHEN wave_level = 'normal' THEN avg_pit1_odds END) as normal_odds,
            COUNT(CASE WHEN wave_level = 'high' THEN 1 END) as high_count,
            AVG(CASE WHEN wave_level = 'high' THEN avg_pit1_odds END) as high_odds,
            (AVG(CASE WHEN wave_level = 'high' THEN avg_pit1_odds END) -
             AVG(CASE WHEN wave_level = 'normal' THEN avg_pit1_odds END)) /
             AVG(CASE WHEN wave_level = 'normal' THEN avg_pit1_odds END) * 100 as diff_pct
        FROM pit1_odds
        GROUP BY venue_code
        HAVING COUNT(CASE WHEN wave_level = 'high' THEN 1 END) >= 10  -- 高波高10件以上
        ORDER BY diff_pct DESC
    """, (start_date, end_date))

    rows = cursor.fetchall()

    if rows:
        print(f"{'会場':>6} {'通常件数':>10} {'通常オッズ':>12} {'高波件数':>10} {'高波オッズ':>12} {'オッズ差':>12}")
        print("-" * 80)

        for row in rows:
            venue, normal_count, normal_odds, high_count, high_odds, diff_pct = row
            print(f"{venue:>6} {normal_count:>10}件 {normal_odds:>11.2f}倍 {high_count:>10}件 {high_odds:>11.2f}倍 {diff_pct:>11.2f}%")
    else:
        print("※ 高波高10件以上の会場なし")

    print()

    # ========================================
    # 5. 江戸川の特異性確認（平均8.71cmの異常値）
    # ========================================
    print("【5. 江戸川の波高分布（平均8.71cm、他会場の3.5倍）】")
    print("-" * 80)

    cursor.execute("""
        SELECT
            r.venue_code,
            COUNT(*) as race_count,
            AVG(rc.wave_height) as avg_wave,
            MIN(rc.wave_height) as min_wave,
            MAX(rc.wave_height) as max_wave,
            SUM(CASE WHEN rc.wave_height >= 10 THEN 1 ELSE 0 END) as high_wave_count,
            SUM(CASE WHEN rc.wave_height >= 10 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as high_wave_pct
        FROM races r
        JOIN race_conditions rc ON r.id = rc.race_id
        WHERE r.race_date BETWEEN ? AND ?
            AND rc.wave_height IS NOT NULL
            AND r.venue_code IN ('03', '10', '14', '15', '20', '23')  -- 江戸川+海水会場サンプル
        GROUP BY r.venue_code
        ORDER BY avg_wave DESC
    """, (start_date, end_date))

    rows = cursor.fetchall()

    print(f"{'会場':>6} {'レース数':>10} {'平均波高':>12} {'最小波高':>10} {'最大波高':>10} {'高波件数':>10} {'高波率':>10}")
    print("-" * 80)

    for row in rows:
        venue, count, avg, min_w, max_w, high_count, high_pct = row
        print(f"{venue:>6} {count:>10}件 {avg:>11.2f}cm {min_w:>9}cm {max_w:>9}cm {high_count:>10}件 {high_pct:>9.2f}%")

    print()
    print("※ 江戸川（03）は他会場と比較して波高が極端に高い")
    print("   → 江戸川のみ独自閾値を設定する必要あり")
    print()

    conn.close()

    print("=" * 80)
    print("分析完了")
    print("=" * 80)


if __name__ == "__main__":
    analyze_wave_height_market_efficiency()
