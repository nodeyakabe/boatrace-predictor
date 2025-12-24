#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
会場フィルター効果テスト

B×30-50×B1条件の会場フィルター追加による効果を検証
- before予測データを使用
- 2020-2025年の6年間で検証
"""
import sys
import os
import io
import sqlite3
from datetime import datetime

# Windows環境でのstdout/stderrエンコーディングをUTF-8に設定
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, PROJECT_ROOT)

from config.settings import DATABASE_PATH


def test_venue_filter_effect():
    """会場フィルター効果をテスト"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    print("=" * 70)
    print("会場フィルター効果テスト（B×30-50×B1条件）")
    print("=" * 70)
    print(f"テスト実行: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # 高ROI会場リスト（before予測分析結果）
    high_roi_venues = [10, 6, 16, 21, 9, 13, 20, 24, 7, 8]
    venue_names = {
        10: '三国', 6: '浜名湖', 16: '児島', 21: '芦屋', 9: '津',
        13: '尼崎', 20: '若松', 24: '大村', 7: '蒲郡', 8: '常滑'
    }

    print(f"高ROI会場: {', '.join([venue_names.get(v, str(v)) for v in high_roi_venues])}")
    print()

    # B×30-50×B1条件のSQL
    base_query = '''
    WITH bet_results AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            CAST(substr(r.race_date, 1, 4) AS INTEGER) as year,
            rp.confidence,
            e1.racer_rank as c1_rank,
            -- 予測買い目のオッズ
            COALESCE(
                (SELECT o.odds FROM trifecta_odds o
                 WHERE o.race_id = r.id
                 AND o.combination =
                     CAST(rp1.pit_number AS TEXT) || '-' ||
                     CAST(rp2.pit_number AS TEXT) || '-' ||
                     CAST(rp3.pit_number AS TEXT)
                ), 0
            ) as pred_odds,
            -- 予測買い目
            CAST(rp1.pit_number AS TEXT) || '-' ||
            CAST(rp2.pit_number AS TEXT) || '-' ||
            CAST(rp3.pit_number AS TEXT) as pred_combo,
            -- 実際の結果（resultsテーブルからrank=1,2,3のpit_numberを取得）
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
                 AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
                 AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
                THEN 1 ELSE 0
            END as is_hit,
            CASE
                WHEN (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '1') = rp1.pit_number
                 AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '2') = rp2.pit_number
                 AND (SELECT pit_number FROM results WHERE race_id = r.id AND rank = '3') = rp3.pit_number
                THEN COALESCE(
                    (SELECT o.odds FROM trifecta_odds o
                     WHERE o.race_id = r.id
                     AND o.combination =
                         CAST(rp1.pit_number AS TEXT) || '-' ||
                         CAST(rp2.pit_number AS TEXT) || '-' ||
                         CAST(rp3.pit_number AS TEXT)
                    ), 0
                ) * 100
                ELSE 0
            END as payout
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'B'
        AND e1.racer_rank = 'B1'
        AND substr(r.race_date, 1, 4) >= '2020'
        AND substr(r.race_date, 1, 4) <= '2025'
    )
    SELECT
        year,
        {venue_filter_clause}
        COUNT(*) as total,
        SUM(is_hit) as hits,
        SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN 1 ELSE 0 END) as bets,
        SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN is_hit ELSE 0 END) as bet_hits,
        SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN payout ELSE 0 END) as bet_payout,
        CASE
            WHEN SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN 1 ELSE 0 END) > 0
            THEN ROUND(
                100.0 * SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN payout ELSE 0 END) /
                (SUM(CASE WHEN pred_odds >= 30 AND pred_odds < 50 THEN 1 ELSE 0 END) * 100), 1
            )
            ELSE 0
        END as roi
    FROM bet_results
    {where_clause}
    GROUP BY year {venue_group}
    ORDER BY year {venue_order}
    '''

    # フィルターなしの結果
    print("[1] フィルターなし（全会場）")
    print("-" * 50)

    query_no_filter = base_query.format(
        venue_filter_clause='',
        where_clause='',
        venue_group='',
        venue_order=''
    )

    cursor.execute(query_no_filter)
    rows = cursor.fetchall()

    total_bets_no_filter = 0
    total_payout_no_filter = 0

    print(f"{'年度':<8} {'件数':<8} {'的中':<8} {'払戻':<12} {'ROI':<8}")
    print("-" * 50)

    for row in rows:
        year, total, hits, bets, bet_hits, bet_payout, roi = row
        total_bets_no_filter += bets
        total_payout_no_filter += bet_payout
        print(f"{year:<8} {bets:<8} {bet_hits:<8} {bet_payout:<12,.0f} {roi:.1f}%")

    if total_bets_no_filter > 0:
        total_roi_no_filter = 100.0 * total_payout_no_filter / (total_bets_no_filter * 100)
    else:
        total_roi_no_filter = 0

    print("-" * 50)
    print(f"{'合計':<8} {total_bets_no_filter:<8} {'-':<8} {total_payout_no_filter:<12,.0f} {total_roi_no_filter:.1f}%")
    print()

    # フィルターありの結果
    venue_placeholders = ','.join(['?' for _ in high_roi_venues])

    print(f"[2] 高ROI会場フィルターあり（{len(high_roi_venues)}会場）")
    print("-" * 50)

    query_with_filter = base_query.format(
        venue_filter_clause='',
        where_clause=f'WHERE venue_code IN ({venue_placeholders})',
        venue_group='',
        venue_order=''
    )

    cursor.execute(query_with_filter, high_roi_venues)
    rows = cursor.fetchall()

    total_bets_with_filter = 0
    total_payout_with_filter = 0

    print(f"{'年度':<8} {'件数':<8} {'的中':<8} {'払戻':<12} {'ROI':<8}")
    print("-" * 50)

    for row in rows:
        year, total, hits, bets, bet_hits, bet_payout, roi = row
        total_bets_with_filter += bets
        total_payout_with_filter += bet_payout
        print(f"{year:<8} {bets:<8} {bet_hits:<8} {bet_payout:<12,.0f} {roi:.1f}%")

    if total_bets_with_filter > 0:
        total_roi_with_filter = 100.0 * total_payout_with_filter / (total_bets_with_filter * 100)
    else:
        total_roi_with_filter = 0

    print("-" * 50)
    print(f"{'合計':<8} {total_bets_with_filter:<8} {'-':<8} {total_payout_with_filter:<12,.0f} {total_roi_with_filter:.1f}%")
    print()

    # 効果サマリー
    print("=" * 70)
    print("効果サマリー")
    print("=" * 70)
    print(f"{'項目':<20} {'フィルターなし':<15} {'フィルターあり':<15} {'改善':<10}")
    print("-" * 70)
    print(f"{'件数':<20} {total_bets_no_filter:<15} {total_bets_with_filter:<15} {total_bets_with_filter - total_bets_no_filter:+}")
    print(f"{'ROI':<20} {total_roi_no_filter:.1f}%{'':<10} {total_roi_with_filter:.1f}%{'':<10} {total_roi_with_filter - total_roi_no_filter:+.1f}pt")

    # 期待収益の計算
    profit_no_filter = total_payout_no_filter - (total_bets_no_filter * 100)
    profit_with_filter = total_payout_with_filter - (total_bets_with_filter * 100)

    print(f"{'6年間収益':<20} {profit_no_filter:+,.0f}円{'':<5} {profit_with_filter:+,.0f}円{'':<5} -")

    # 年間平均
    annual_profit_no_filter = profit_no_filter / 6
    annual_profit_with_filter = profit_with_filter / 6

    print(f"{'年間平均収益':<20} {annual_profit_no_filter:+,.0f}円{'':<5} {annual_profit_with_filter:+,.0f}円{'':<5} -")
    print("=" * 70)

    conn.close()

    return {
        'no_filter': {
            'bets': total_bets_no_filter,
            'roi': total_roi_no_filter,
            'profit': profit_no_filter
        },
        'with_filter': {
            'bets': total_bets_with_filter,
            'roi': total_roi_with_filter,
            'profit': profit_with_filter
        },
        'improvement': total_roi_with_filter - total_roi_no_filter
    }


if __name__ == '__main__':
    test_venue_filter_effect()
