# -*- coding: utf-8 -*-
"""直前情報全体の効果測定バックテスト

事前予想（advance）と直前予想（before）の精度差を定量測定し、
直前情報（展示タイム・気象補正・コース変更ペナルティ）の
予測精度向上への寄与を明確化する。

測定項目:
- 1着的中率、2着的中率、3着的中率
- 3連単完全一致率
- 月別・会場別・コース別の精度差分
- ROI、収支への影響（購入戦略と連動）
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))


def calculate_hit_rate(cursor, prediction_type, start_date='2025-01-01', end_date='2025-12-31'):
    """
    指定した予測タイプの的中率を計算

    Args:
        cursor: DBカーソル
        prediction_type: 'advance' or 'before'
        start_date: 開始日
        end_date: 終了日

    Returns:
        結果辞書
    """
    stats = {
        'total_races': 0,
        'rank1_correct': 0,
        'rank2_correct': 0,
        'rank3_correct': 0,
        'trifecta_correct': 0,
        'by_month': defaultdict(lambda: {
            'total': 0, 'rank1': 0, 'rank2': 0, 'rank3': 0, 'trifecta': 0
        }),
        'by_venue': defaultdict(lambda: {
            'total': 0, 'rank1': 0, 'rank2': 0, 'rank3': 0, 'trifecta': 0
        }),
        'by_course': defaultdict(lambda: {
            'total': 0, 'rank1': 0, 'rank2': 0, 'rank3': 0, 'trifecta': 0
        })
    }

    # 対象レース取得
    cursor.execute(f'''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''', (start_date, end_date))
    races = cursor.fetchall()

    for race in races:
        race_id = race['race_id']
        venue_code = race['venue_code']
        race_date = race['race_date']
        month = race_date[:7]

        # 予測情報取得
        cursor.execute('''
            SELECT pit_number, confidence
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
            ORDER BY rank_prediction
        ''', (race_id, prediction_type))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        # 実際の結果取得
        cursor.execute('''
            SELECT pit_number, rank FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results = cursor.fetchall()

        if len(results) < 3:
            continue

        stats['total_races'] += 1

        # 予測トップ3
        pred_top3 = [p['pit_number'] for p in preds[:3]]
        pred_1st = pred_top3[0]
        pred_2nd = pred_top3[1]
        pred_3rd = pred_top3[2]

        # 実際のトップ3
        actual_1st = results[0]['pit_number']
        actual_2nd = results[1]['pit_number']
        actual_3rd = results[2]['pit_number']

        # 1コース番号取得（コース別統計用）
        cursor.execute('SELECT pit_number FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        course_row = cursor.fetchone()
        course_key = '1コース' if course_row else 'その他'

        # 1着的中
        if pred_1st == actual_1st:
            stats['rank1_correct'] += 1
            stats['by_month'][month]['rank1'] += 1
            stats['by_venue'][venue_code]['rank1'] += 1
            stats['by_course'][course_key]['rank1'] += 1

        # 2着的中
        if pred_2nd == actual_2nd:
            stats['rank2_correct'] += 1
            stats['by_month'][month]['rank2'] += 1
            stats['by_venue'][venue_code]['rank2'] += 1
            stats['by_course'][course_key]['rank2'] += 1

        # 3着的中
        if pred_3rd == actual_3rd:
            stats['rank3_correct'] += 1
            stats['by_month'][month]['rank3'] += 1
            stats['by_venue'][venue_code]['rank3'] += 1
            stats['by_course'][course_key]['rank3'] += 1

        # 3連単完全一致
        if pred_1st == actual_1st and pred_2nd == actual_2nd and pred_3rd == actual_3rd:
            stats['trifecta_correct'] += 1
            stats['by_month'][month]['trifecta'] += 1
            stats['by_venue'][venue_code]['trifecta'] += 1
            stats['by_course'][course_key]['trifecta'] += 1

        # 月別・会場別・コース別の総数カウント
        stats['by_month'][month]['total'] += 1
        stats['by_venue'][venue_code]['total'] += 1
        stats['by_course'][course_key]['total'] += 1

    return stats


def print_comparison(advance_stats, before_stats):
    """比較結果を表示"""
    print(f"\n{'='*100}")
    print(f"全体サマリー")
    print(f"{'='*100}\n")

    total_races = advance_stats['total_races']

    # 事前予想
    adv_rank1_rate = (advance_stats['rank1_correct'] / total_races * 100) if total_races > 0 else 0
    adv_rank2_rate = (advance_stats['rank2_correct'] / total_races * 100) if total_races > 0 else 0
    adv_rank3_rate = (advance_stats['rank3_correct'] / total_races * 100) if total_races > 0 else 0
    adv_trifecta_rate = (advance_stats['trifecta_correct'] / total_races * 100) if total_races > 0 else 0

    # 直前予想
    bef_rank1_rate = (before_stats['rank1_correct'] / total_races * 100) if total_races > 0 else 0
    bef_rank2_rate = (before_stats['rank2_correct'] / total_races * 100) if total_races > 0 else 0
    bef_rank3_rate = (before_stats['rank3_correct'] / total_races * 100) if total_races > 0 else 0
    bef_trifecta_rate = (before_stats['trifecta_correct'] / total_races * 100) if total_races > 0 else 0

    # 差分
    diff_rank1 = bef_rank1_rate - adv_rank1_rate
    diff_rank2 = bef_rank2_rate - adv_rank2_rate
    diff_rank3 = bef_rank3_rate - adv_rank3_rate
    diff_trifecta = bef_trifecta_rate - adv_trifecta_rate

    print(f"対象レース数: {total_races}レース\n")
    print(f"{'項目':<20} {'事前予想':<20} {'直前予想':<20} {'差分':<20}")
    print('-' * 100)
    print(f"{'1着的中数':<20} {advance_stats['rank1_correct']:<20} {before_stats['rank1_correct']:<20} {before_stats['rank1_correct'] - advance_stats['rank1_correct']:+}")
    print(f"{'1着的中率':<20} {adv_rank1_rate:<18.2f}% {bef_rank1_rate:<18.2f}% {diff_rank1:+.2f}%")
    print(f"{'2着的中数':<20} {advance_stats['rank2_correct']:<20} {before_stats['rank2_correct']:<20} {before_stats['rank2_correct'] - advance_stats['rank2_correct']:+}")
    print(f"{'2着的中率':<20} {adv_rank2_rate:<18.2f}% {bef_rank2_rate:<18.2f}% {diff_rank2:+.2f}%")
    print(f"{'3着的中数':<20} {advance_stats['rank3_correct']:<20} {before_stats['rank3_correct']:<20} {before_stats['rank3_correct'] - advance_stats['rank3_correct']:+}")
    print(f"{'3着的中率':<20} {adv_rank3_rate:<18.2f}% {bef_rank3_rate:<18.2f}% {diff_rank3:+.2f}%")
    print(f"{'3連単完全一致数':<20} {advance_stats['trifecta_correct']:<20} {before_stats['trifecta_correct']:<20} {before_stats['trifecta_correct'] - advance_stats['trifecta_correct']:+}")
    print(f"{'3連単完全一致率':<20} {adv_trifecta_rate:<18.2f}% {bef_trifecta_rate:<18.2f}% {diff_trifecta:+.2f}%")

    # 月別詳細
    print(f"\n{'='*100}")
    print(f"月別比較")
    print(f"{'='*100}\n")
    print(f"{'月':<12} {'1着的中率(事前)':<18} {'1着的中率(直前)':<18} {'差分':<12} {'3連単一致率(事前)':<18} {'3連単一致率(直前)':<18} {'差分':<12}")
    print('-' * 100)

    for month in sorted(advance_stats['by_month'].keys()):
        adv_month = advance_stats['by_month'][month]
        bef_month = before_stats['by_month'][month]

        if adv_month['total'] == 0:
            continue

        adv_m_rank1_rate = (adv_month['rank1'] / adv_month['total'] * 100) if adv_month['total'] > 0 else 0
        bef_m_rank1_rate = (bef_month['rank1'] / bef_month['total'] * 100) if bef_month['total'] > 0 else 0
        diff_m_rank1 = bef_m_rank1_rate - adv_m_rank1_rate

        adv_m_trifecta_rate = (adv_month['trifecta'] / adv_month['total'] * 100) if adv_month['total'] > 0 else 0
        bef_m_trifecta_rate = (bef_month['trifecta'] / bef_month['total'] * 100) if bef_month['total'] > 0 else 0
        diff_m_trifecta = bef_m_trifecta_rate - adv_m_trifecta_rate

        print(f"{month:<12} {adv_m_rank1_rate:>14.2f}% {bef_m_rank1_rate:>14.2f}% {diff_m_rank1:>+9.2f}% "
              f"{adv_m_trifecta_rate:>14.2f}% {bef_m_trifecta_rate:>14.2f}% {diff_m_trifecta:>+9.2f}%")

    # 会場別トップ5（差分が大きい順）
    print(f"\n{'='*100}")
    print(f"会場別比較（1着的中率差分トップ5）")
    print(f"{'='*100}\n")

    venue_diffs = []
    for venue_code in advance_stats['by_venue'].keys():
        adv_venue = advance_stats['by_venue'][venue_code]
        bef_venue = before_stats['by_venue'][venue_code]

        if adv_venue['total'] < 50:  # サンプル数少ない会場は除外
            continue

        adv_v_rank1_rate = (adv_venue['rank1'] / adv_venue['total'] * 100) if adv_venue['total'] > 0 else 0
        bef_v_rank1_rate = (bef_venue['rank1'] / bef_venue['total'] * 100) if bef_venue['total'] > 0 else 0
        diff_v_rank1 = bef_v_rank1_rate - adv_v_rank1_rate

        venue_diffs.append({
            'venue_code': venue_code,
            'adv_rate': adv_v_rank1_rate,
            'bef_rate': bef_v_rank1_rate,
            'diff': diff_v_rank1,
            'total': adv_venue['total']
        })

    venue_diffs.sort(key=lambda x: x['diff'], reverse=True)

    print(f"{'会場コード':<12} {'レース数':<12} {'事前予想':<14} {'直前予想':<14} {'差分':<12}")
    print('-' * 100)
    for venue in venue_diffs[:5]:
        print(f"{venue['venue_code']:<12} {venue['total']:<12} {venue['adv_rate']:>11.2f}% {venue['bef_rate']:>11.2f}% {venue['diff']:>+9.2f}%")

    print(f"\n{'='*100}")
    print(f"判定")
    print(f"{'='*100}\n")

    if diff_rank1 >= 5.0:
        print(f"【判定: 直前情報の効果大】")
        print(f"   1着的中率が {diff_rank1:+.2f}% 向上しており、直前情報（展示タイム・気象補正）が")
        print(f"   予測精度向上に大きく寄与しています。")
    elif diff_rank1 >= 2.0:
        print(f"【判定: 直前情報の効果あり】")
        print(f"   1着的中率が {diff_rank1:+.2f}% 向上しており、直前情報の効果が確認されます。")
    elif diff_rank1 >= 0:
        print(f"【判定: 直前情報の効果限定的】")
        print(f"   1着的中率の向上は {diff_rank1:+.2f}% と限定的です。")
        print(f"   補正ロジックの見直しが必要かもしれません。")
    else:
        print(f"【判定: 直前情報が逆効果】")
        print(f"   1着的中率が {diff_rank1:+.2f}% 低下しています。")
        print(f"   直前情報の補正ロジックに問題がある可能性があります。")

    print(f"\n{'='*100}\n")


def main():
    """メイン処理"""
    db_path = ROOT_DIR / "data" / "boatrace.db"

    print(f"\n{'='*100}")
    print(f"直前情報全体の効果測定バックテスト")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 事前予想の精度計算
    print(f"\n## 事前予想（advance）の精度計算中...\n")
    advance_stats = calculate_hit_rate(cursor, 'advance')

    # 直前予想の精度計算
    print(f"\n## 直前予想（before）の精度計算中...\n")
    before_stats = calculate_hit_rate(cursor, 'before')

    conn.close()

    # 比較結果表示
    print_comparison(advance_stats, before_stats)


if __name__ == "__main__":
    main()
