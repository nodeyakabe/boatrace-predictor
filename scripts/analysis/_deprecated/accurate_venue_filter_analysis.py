# -*- coding: utf-8 -*-
"""
会場フィルター最適化の正確な分析スクリプト

standard_backtest.pyと完全に同じロジックで会場別ROIを計算
対象条件: C2 (B×50-100×冬+4月除外), C10 (D×5コース予測×A2除外), C11 (B2×20-30倍)
"""
import sqlite3
import sys
from typing import Dict, List

DATABASE_PATH = 'data/boatrace.db'

VENUE_NAMES = {
    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島', '05': '多摩川',
    '06': '浜名湖', '07': '蒲郡', '08': '常滑', '09': '津', '10': '三国',
    '11': 'びわこ', '12': '住之江', '13': '尼崎', '14': '鳴門', '15': '丸亀',
    '16': '児島', '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
}

def analyze_c2_venue(cursor, date_start='2020-01-01', date_end='2026-01-01'):
    """
    C2条件: B×50-100×冬+4月除外
    standard_backtest.pyの行119-137と完全一致
    """
    print("\n" + "="*80)
    print("C2条件: B×50-100×冬+4月除外 の会場別分析")
    print("="*80)

    # パターンH: 3点買い (1-2-3:200円, 1-2-4:100円, 1-2-5:100円)
    query = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'B'
        AND e1.racer_rank IN ('A1', 'B1')
        AND r.race_date >= ?
        AND r.race_date < ?
        AND CAST(strftime('%m', r.race_date) AS INTEGER) NOT IN (12, 1, 2, 4)
    ),
    race_with_results AS (
        SELECT
            rb.*,
            -- 3点買いオッズ取得
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
            -- 実際の結果
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    ),
    race_payouts AS (
        SELECT
            rwr.*,
            -- パターンH: 1-2-3に200円、1-2-4に100円、1-2-5に100円
            CASE
                WHEN odds_123 >= 50 AND odds_123 < 100 THEN 200
                ELSE 0
            END as bet_123,
            CASE
                WHEN odds_124 >= 50 AND odds_124 < 100 THEN 100
                ELSE 0
            END as bet_124,
            CASE
                WHEN odds_125 >= 50 AND odds_125 < 100 THEN 100
                ELSE 0
            END as bet_125,
            -- 的中判定・払戻
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= 50 AND odds_123 < 100
                THEN odds_123 * 200 ELSE 0
            END as payout_123,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                     AND odds_124 >= 50 AND odds_124 < 100
                THEN odds_124 * 100 ELSE 0
            END as payout_124,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                     AND odds_125 >= 50 AND odds_125 < 100
                THEN odds_125 * 100 ELSE 0
            END as payout_125,
            -- 的中フラグ
            CASE
                WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 50 AND odds_123 < 100)
                  OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 50 AND odds_124 < 100)
                  OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 50 AND odds_125 < 100)
                THEN 1 ELSE 0
            END as is_hit
        FROM race_with_results rwr
    )
    SELECT
        venue_code,
        COUNT(*) as races,
        SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
        SUM(is_hit) as hits,
        SUM(bet_123 + bet_124 + bet_125) as total_investment,
        SUM(payout_123 + payout_124 + payout_125) as total_payout
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    GROUP BY venue_code
    ORDER BY venue_code
    '''

    cursor.execute(query, (date_start, date_end))
    results = cursor.fetchall()

    venue_data_sorted = print_venue_analysis_results("C2", results)
    return venue_data_sorted


def analyze_c10_venue(cursor, date_start='2020-01-01', date_end='2026-01-01'):
    """
    C10条件: D×5コース予測×A2除外
    standard_backtest.pyの行281-300と完全一致

    重要: predicted_course = 5 は「予測1位の選手が5コース（pit_number=5）」という意味
    """
    print("\n" + "="*80)
    print("C10条件: D×5コース予測×A2除外 の会場別分析")
    print("="*80)
    print("注: predicted_course=5 は「予測1位の選手が5コース(pit_number=5)」を意味します")

    # パターンH: 3点買い
    query = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            rp4.pit_number as p4,
            rp5.pit_number as p5
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN race_predictions rp4 ON r.id = rp4.race_id AND rp4.prediction_type = 'before' AND rp4.rank_prediction = 4
        JOIN race_predictions rp5 ON r.id = rp5.race_id AND rp5.prediction_type = 'before' AND rp5.rank_prediction = 5
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        WHERE rp.rank_prediction = 1
        AND rp.confidence = 'D'
        AND e1.racer_rank IN ('A1', 'B1', 'B2')
        AND r.race_date >= ?
        AND r.race_date < ?
        AND rp1.pit_number = 5  -- 予測1位が5コース
    ),
    race_with_results AS (
        SELECT
            rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p4 AS TEXT)), 0) as odds_124,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p5 AS TEXT)), 0) as odds_125,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    ),
    race_payouts AS (
        SELECT
            rwr.*,
            CASE WHEN odds_123 >= 10 AND odds_123 < 200 THEN 200 ELSE 0 END as bet_123,
            CASE WHEN odds_124 >= 10 AND odds_124 < 200 THEN 100 ELSE 0 END as bet_124,
            CASE WHEN odds_125 >= 10 AND odds_125 < 200 THEN 100 ELSE 0 END as bet_125,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= 10 AND odds_123 < 200
                THEN odds_123 * 200 ELSE 0
            END as payout_123,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4
                     AND odds_124 >= 10 AND odds_124 < 200
                THEN odds_124 * 100 ELSE 0
            END as payout_124,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5
                     AND odds_125 >= 10 AND odds_125 < 200
                THEN odds_125 * 100 ELSE 0
            END as payout_125,
            CASE
                WHEN (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3 AND odds_123 >= 10 AND odds_123 < 200)
                  OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p4 AND odds_124 >= 10 AND odds_124 < 200)
                  OR (actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p5 AND odds_125 >= 10 AND odds_125 < 200)
                THEN 1 ELSE 0
            END as is_hit
        FROM race_with_results rwr
    )
    SELECT
        venue_code,
        COUNT(*) as races,
        SUM(CASE WHEN bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0 THEN 1 ELSE 0 END) as bets,
        SUM(is_hit) as hits,
        SUM(bet_123 + bet_124 + bet_125) as total_investment,
        SUM(payout_123 + payout_124 + payout_125) as total_payout
    FROM race_payouts
    WHERE bet_123 > 0 OR bet_124 > 0 OR bet_125 > 0
    GROUP BY venue_code
    ORDER BY venue_code
    '''

    cursor.execute(query, (date_start, date_end))
    results = cursor.fetchall()

    venue_data_sorted = print_venue_analysis_results("C10", results)
    return venue_data_sorted


def analyze_c11_venue(cursor, date_start='2020-01-01', date_end='2026-01-01'):
    """
    C11条件: B2×20-30倍
    standard_backtest.pyの行300-329と完全一致

    predicted_rank_has_class: 予測1-3位のいずれかがB2級
    """
    print("\n" + "="*80)
    print("C11条件: B2×20-30倍 の会場別分析")
    print("="*80)
    print("注: 予測1-3位のいずれかがB2級の条件です")

    # 1点買い: 1-2-3のみに100円
    query = '''
    WITH race_base AS (
        SELECT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            rp.confidence,
            e1.racer_rank as c1_rank,
            rp1.pit_number as p1,
            rp2.pit_number as p2,
            rp3.pit_number as p3,
            ep1.racer_rank as r1_class,
            ep2.racer_rank as r2_class,
            ep3.racer_rank as r3_class
        FROM races r
        JOIN race_predictions rp ON r.id = rp.race_id AND rp.prediction_type = 'before'
        JOIN race_predictions rp1 ON r.id = rp1.race_id AND rp1.prediction_type = 'before' AND rp1.rank_prediction = 1
        JOIN race_predictions rp2 ON r.id = rp2.race_id AND rp2.prediction_type = 'before' AND rp2.rank_prediction = 2
        JOIN race_predictions rp3 ON r.id = rp3.race_id AND rp3.prediction_type = 'before' AND rp3.rank_prediction = 3
        JOIN entries e1 ON r.id = e1.race_id AND e1.pit_number = 1
        JOIN entries ep1 ON r.id = ep1.race_id AND ep1.pit_number = rp1.pit_number
        JOIN entries ep2 ON r.id = ep2.race_id AND ep2.pit_number = rp2.pit_number
        JOIN entries ep3 ON r.id = ep3.race_id AND ep3.pit_number = rp3.pit_number
        WHERE rp.rank_prediction = 1
        AND e1.racer_rank IN ('A1', 'A2', 'B1', 'B2')
        AND r.race_date >= ?
        AND r.race_date < ?
        AND (ep1.racer_rank = 'B2' OR ep2.racer_rank = 'B2' OR ep3.racer_rank = 'B2')
    ),
    race_bets AS (
        SELECT
            rb.*,
            COALESCE((SELECT o.odds FROM trifecta_odds o WHERE o.race_id = rb.race_id
                      AND o.combination = CAST(rb.p1 AS TEXT) || '-' || CAST(rb.p2 AS TEXT) || '-' || CAST(rb.p3 AS TEXT)), 0) as odds_123,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '1') as actual_1st,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '2') as actual_2nd,
            (SELECT pit_number FROM results WHERE race_id = rb.race_id AND rank = '3') as actual_3rd
        FROM race_base rb
    ),
    race_payouts AS (
        SELECT
            rb.*,
            CASE WHEN odds_123 >= 20 AND odds_123 < 30 THEN 100 ELSE 0 END as bet_amount,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= 20 AND odds_123 < 30
                THEN odds_123 * 100 ELSE 0
            END as payout,
            CASE
                WHEN actual_1st = p1 AND actual_2nd = p2 AND actual_3rd = p3
                     AND odds_123 >= 20 AND odds_123 < 30
                THEN 1 ELSE 0
            END as is_hit
        FROM race_bets rb
    )
    SELECT
        venue_code,
        COUNT(*) as races,
        SUM(CASE WHEN bet_amount > 0 THEN 1 ELSE 0 END) as bets,
        SUM(is_hit) as hits,
        SUM(bet_amount) as total_investment,
        SUM(payout) as total_payout
    FROM race_payouts
    WHERE bet_amount > 0
    GROUP BY venue_code
    ORDER BY venue_code
    '''

    cursor.execute(query, (date_start, date_end))
    results = cursor.fetchall()

    venue_data_sorted = print_venue_analysis_results("C11", results)
    return venue_data_sorted


def print_venue_analysis_results(condition_name: str, results: List):
    """会場別分析結果を表示"""
    output = []
    output.append(f"\n{'会場コード':>8s} | {'会場名':>8s} | {'レース数':>8s} | {'的中数':>6s} | {'投資額':>12s} | {'払戻額':>12s} | {'収支':>12s} | {'ROI':>8s}")
    output.append("-" * 100)

    total_races = 0
    total_hits = 0
    total_investment = 0
    total_payout = 0

    venue_data = []

    for row in results:
        venue_code, races, bets, hits, investment, payout = row
        profit = payout - investment
        roi = (payout / investment * 100) if investment > 0 else 0

        venue_name = VENUE_NAMES.get(venue_code, f"会場{venue_code}")

        total_races += races
        total_hits += hits
        total_investment += investment
        total_payout += payout

        venue_data.append({
            'venue_code': venue_code,
            'venue_name': venue_name,
            'races': races,
            'hits': hits,
            'investment': investment,
            'payout': payout,
            'profit': profit,
            'roi': roi
        })

        output.append(f"{venue_code:>8s} | {venue_name:>8s} | {races:>8d} | {hits:>6d} | {investment:>12,.0f}円 | {payout:>12,.0f}円 | {profit:>+12,.0f}円 | {roi:>7.1f}%")

    # 合計
    total_profit = total_payout - total_investment
    total_roi = (total_payout / total_investment * 100) if total_investment > 0 else 0

    output.append("-" * 100)
    output.append(f"{'':>8s} | {'合計':>8s} | {total_races:>8d} | {total_hits:>6d} | {total_investment:>12,.0f}円 | {total_payout:>12,.0f}円 | {total_profit:>+12,.0f}円 | {total_roi:>7.1f}%")

    # ROI順にソート
    venue_data_sorted = sorted(venue_data, key=lambda x: x['roi'], reverse=True)

    output.append("\n" + "="*80)
    output.append(f"{condition_name}条件: ROI上位会場")
    output.append("="*80)

    for i, v in enumerate(venue_data_sorted[:10], 1):
        if v['roi'] >= 100:
            marker = "[OK]"
        elif v['roi'] >= 80:
            marker = "[WARN]"
        else:
            marker = "[NG]"

        output.append(f"{i:>2d}. {v['venue_name']:>8s}({v['venue_code']}): ROI {v['roi']:>7.1f}%, {v['races']:>4d}レース, 収支{v['profit']:>+12,.0f}円 {marker}")

    output.append("\n" + "="*80)
    output.append(f"{condition_name}条件: ROI下位会場（大幅赤字）")
    output.append("="*80)

    for i, v in enumerate(reversed(venue_data_sorted[-5:]), 1):
        output.append(f"{i:>2d}. {v['venue_name']:>8s}({v['venue_code']}): ROI {v['roi']:>7.1f}%, {v['races']:>4d}レース, 収支{v['profit']:>+12,.0f}円 [NG]")

    # 出力（コンソールとファイル）
    output_text = '\n'.join(output)
    print(output_text)

    return venue_data_sorted


def main():
    """メイン実行"""
    import io
    from datetime import datetime

    # UTF-8出力設定
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    output_file = 'docs/analysis/ACCURATE_VENUE_FILTER_ANALYSIS_20260213.md'
    report = []

    report.append("# 会場フィルター最適化の正確な分析レポート")
    report.append("")
    report.append(f"**分析日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**データ期間**: 2020-01-01 ~ 2025-12-31（6年間）")
    report.append(f"**ロジック**: standard_backtest.pyと完全一致")
    report.append("")

    print("="*80)
    print("会場フィルター最適化の正確な分析")
    print("="*80)
    print("データ期間: 2020-01-01 ~ 2025-12-31（6年間）")
    print("ロジック: standard_backtest.pyと完全一致")
    print()

    # C2: B×50-100×冬+4月除外
    print("\n処理中: C2条件...")
    cursor.execute("SELECT 1")  # カーソル確認
    c2_results = analyze_c2_venue(cursor)

    # C10: D×5コース予測×A2除外
    print("\n処理中: C10条件...")
    c10_results = analyze_c10_venue(cursor)

    # C11: B2×20-30倍
    print("\n処理中: C11条件...")
    c11_results = analyze_c11_venue(cursor)

    conn.close()

    # 結果が返されているか確認
    if not c2_results or not c10_results or not c11_results:
        print("エラー: 分析結果が取得できませんでした")
        return

    # レポート作成（c2_results等はリスト形式で返される）
    report.append("## 分析結果サマリー")
    report.append("")
    report.append("### C2条件: B×50-100×冬+4月除外")
    report.append("")
    report.append("**推奨会場フィルター（ROI ≥ 150% かつ サンプル ≥ 20レース）:**")
    c2_recommended = [v for v in c2_results if v['roi'] >= 150 and v['races'] >= 20]
    report.append(f"- venue_filter: [{', '.join(v['venue_code'] for v in c2_recommended)}]")
    report.append(f"- 該当会場: {', '.join(v['venue_name'] for v in c2_recommended)}")
    report.append("")
    report.append("| 会場 | レース数 | ROI | 収支 | 判定 |")
    report.append("|------|----------|-----|------|------|")
    for v in c2_results[:15]:
        marker = "OK" if v['roi'] >= 100 else "NG"
        report.append(f"| {v['venue_name']}({v['venue_code']}) | {v['races']}件 | {v['roi']:.1f}% | {v['profit']:+,.0f}円 | {marker} |")

    report.append("")
    report.append("### C10条件: D×5コース予測×A2除外")
    report.append("")
    report.append("**推奨会場フィルター（ROI ≥ 150% かつ サンプル ≥ 20レース）:**")
    c10_recommended = [v for v in c10_results if v['roi'] >= 150 and v['races'] >= 20]
    report.append(f"- venue_filter: [{', '.join(v['venue_code'] for v in c10_recommended)}]")
    report.append(f"- 該当会場: {', '.join(v['venue_name'] for v in c10_recommended)}")
    report.append("")
    report.append("| 会場 | レース数 | ROI | 収支 | 判定 |")
    report.append("|------|----------|-----|------|------|")
    for v in c10_results[:15]:
        marker = "OK" if v['roi'] >= 100 else "NG"
        report.append(f"| {v['venue_name']}({v['venue_code']}) | {v['races']}件 | {v['roi']:.1f}% | {v['profit']:+,.0f}円 | {marker} |")

    report.append("")
    report.append("### C11条件: B2×20-30倍")
    report.append("")
    report.append("**推奨会場フィルター（ROI ≥ 100% かつ サンプル ≥ 20レース）:**")
    c11_recommended = [v for v in c11_results if v['roi'] >= 100 and v['races'] >= 20]
    if c11_recommended:
        report.append(f"- venue_filter: [{', '.join(v['venue_code'] for v in c11_recommended)}]")
        report.append(f"- 該当会場: {', '.join(v['venue_name'] for v in c11_recommended)}")
    else:
        report.append("- **該当なし** - 条件全体のROI 26.4%で採用基準未達")
    report.append("")
    report.append("| 会場 | レース数 | ROI | 収支 | 判定 |")
    report.append("|------|----------|-----|------|------|")
    for v in c11_results[:15]:
        marker = "OK" if v['roi'] >= 100 else "NG"
        report.append(f"| {v['venue_name']}({v['venue_code']}) | {v['races']}件 | {v['roi']:.1f}% | {v['profit']:+,.0f}円 | {marker} |")

    # ファイル保存
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    print("\n" + "="*80)
    print("分析完了")
    print("="*80)
    print(f"レポート保存: {output_file}")
    print("\n推奨アクション:")
    print("1. ROI >= 150% かつ サンプル数 >= 20レースの会場を venue_filter に追加")
    print("2. ROI < 50% かつ 大幅赤字の会場を除外")
    print("3. 変更後は必ず standard_backtest.py --full で検証")


if __name__ == '__main__':
    main()
