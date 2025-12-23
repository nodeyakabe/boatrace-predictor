# -*- coding: utf-8 -*-
"""
コース強制化の効果検証バックテスト

修正前（コース強制化なし）と修正後（コース強制化あり）のROI・収支を比較

DBの予測データはスコア順（強制化なし）で保存されているため、
このスクリプトでは強制化をシミュレートして効果を検証する。

2025-12-16 作成
"""
import sys
import sqlite3
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def apply_course_enforcement(predictions, score_threshold=15.0):
    """
    コース強制化をシミュレート

    Args:
        predictions: スコア降順にソートされた予測リスト [{'pit_number': int, 'total_score': float, ...}, ...]
        score_threshold: 強制化適用閾値（pt）

    Returns:
        (enforced_predictions, is_enforced, original_top_pit)
    """
    if not predictions:
        return predictions, False, None

    top_pred = predictions[0]
    top_pit = top_pred['pit_number']
    top_score = top_pred['total_score']

    # 1コースが既に1位予測の場合は処理不要
    if top_pit == 1:
        return predictions, False, None

    # 1コースの予測データを取得
    course1_pred = None
    for p in predictions:
        if p['pit_number'] == 1:
            course1_pred = p
            break

    if not course1_pred:
        return predictions, False, None

    course1_score = course1_pred['total_score']
    score_diff = top_score - course1_score

    # スコア差が閾値未満の場合、1コースに強制
    if score_diff < score_threshold:
        # 1コースのスコアを最大にする
        new_predictions = []
        course1_modified = dict(course1_pred)
        course1_modified['total_score'] = top_score + 0.1

        new_predictions.append(course1_modified)
        for p in predictions:
            if p['pit_number'] != 1:
                new_predictions.append(p)

        return new_predictions, True, top_pit

    return predictions, False, None


def main():
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    # 2025年1月〜11月のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-11-30'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    # 閾値設定（現在の設定: 15pt）
    SCORE_THRESHOLD = 15.0

    # コース強制化後（シミュレート）
    results_after = {
        'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0,
        'enforced_count': 0,
        'enforced_hit': 0,
        'non_enforced_hit': 0,
        'by_month': defaultdict(lambda: {'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
    }

    # コース強制化なし（DBのスコア順をそのまま使用）
    results_before = {
        'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0,
        'by_month': defaultdict(lambda: {'purchase': 0, 'hit': 0, 'bet': 0, 'payout': 0}),
    }

    # 強制化適用レースの詳細
    enforced_details = []

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']
        month = race_date[:7]

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報を取得（直前情報 = before）- スコア順（DBの元データ）
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds_rows = cursor.fetchall()

        if len(preds_rows) < 6:
            continue

        # dict形式に変換
        preds_before = [{'pit_number': p['pit_number'], 'total_score': p['total_score'], 'confidence': p['confidence']} for p in preds_rows]
        confidence = preds_before[0]['confidence']

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

        # コース強制化をシミュレート
        preds_after, is_enforced, original_top = apply_course_enforcement(preds_before, SCORE_THRESHOLD)

        # 予測買い目（強制化前）
        top3_before = [p['pit_number'] for p in preds_before[:3]]
        combo_before = f"{top3_before[0]}-{top3_before[1]}-{top3_before[2]}"

        # 予測買い目（強制化後）
        top3_after = [p['pit_number'] for p in preds_after[:3]]
        combo_after = f"{top3_after[0]}-{top3_after[1]}-{top3_after[2]}"

        # 実際の結果を取得
        cursor.execute('''
            SELECT pit_number FROM results
            WHERE race_id = ? AND is_invalid = 0 AND rank <= 3
            ORDER BY rank
        ''', (race_id,))
        results_rows = cursor.fetchall()

        if len(results_rows) < 3:
            continue

        actual_combo = f"{results_rows[0]['pit_number']}-{results_rows[1]['pit_number']}-{results_rows[2]['pit_number']}"
        actual_1st = results_rows[0]['pit_number']

        # --- 強制化後のバックテスト ---
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo_after))
        odds_row_after = cursor.fetchone()

        if odds_row_after:
            odds_after = odds_row_after['odds']

            result_after = evaluator.evaluate(
                confidence=confidence,
                c1_rank=c1_rank,
                old_combo=combo_after,
                new_combo=combo_after,
                old_odds=odds_after,
                new_odds=odds_after,
                has_beforeinfo=True,
                venue_code=venue_code
            )

            if result_after.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                bet_amount = result_after.bet_amount
                results_after['purchase'] += 1
                results_after['bet'] += bet_amount
                results_after['by_month'][month]['purchase'] += 1
                results_after['by_month'][month]['bet'] += bet_amount

                if is_enforced:
                    results_after['enforced_count'] += 1
                    enforced_details.append({
                        'race_id': race_id,
                        'race_date': race_date,
                        'original_top': original_top,
                        'combo_before': combo_before,
                        'combo_after': combo_after,
                        'actual_1st': actual_1st,
                        'actual_combo': actual_combo,
                        'hit_after': combo_after == actual_combo,
                        'hit_before': combo_before == actual_combo,
                    })

                if combo_after == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        actual_payout = (bet_amount / 100) * payout_row['amount']
                        results_after['hit'] += 1
                        results_after['payout'] += actual_payout
                        results_after['by_month'][month]['hit'] += 1
                        results_after['by_month'][month]['payout'] += actual_payout

                        if is_enforced:
                            results_after['enforced_hit'] += 1
                        else:
                            results_after['non_enforced_hit'] += 1

        # --- 強制化前のバックテスト ---
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo_before))
        odds_row_before = cursor.fetchone()

        if odds_row_before:
            odds_before = odds_row_before['odds']

            result_before = evaluator.evaluate(
                confidence=confidence,
                c1_rank=c1_rank,
                old_combo=combo_before,
                new_combo=combo_before,
                old_odds=odds_before,
                new_odds=odds_before,
                has_beforeinfo=True,
                venue_code=venue_code
            )

            if result_before.status in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
                bet_amount = result_before.bet_amount
                results_before['purchase'] += 1
                results_before['bet'] += bet_amount
                results_before['by_month'][month]['purchase'] += 1
                results_before['by_month'][month]['bet'] += bet_amount

                if combo_before == actual_combo:
                    cursor.execute('''
                        SELECT amount FROM payouts
                        WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
                    ''', (race_id, actual_combo))
                    payout_row = cursor.fetchone()

                    if payout_row:
                        actual_payout = (bet_amount / 100) * payout_row['amount']
                        results_before['hit'] += 1
                        results_before['payout'] += actual_payout
                        results_before['by_month'][month]['hit'] += 1
                        results_before['by_month'][month]['payout'] += actual_payout

    conn.close()

    # 結果比較
    print('=' * 80)
    print('コース強制化の効果検証（2025年1月〜11月）')
    print('=' * 80)
    print()

    print('【修正前（コース強制化なし）】')
    p = results_before['purchase']
    h = results_before['hit']
    b = results_before['bet']
    pay = results_before['payout']
    hr = (h / p * 100) if p > 0 else 0
    roi = (pay / b * 100) if b > 0 else 0
    profit = pay - b
    print(f'  購入: {p}件, 的中: {h}件, 的中率: {hr:.2f}%')
    print(f'  投資: {b:,.0f}円, 払戻: {pay:,.0f}円')
    print(f'  収支: {profit:+,.0f}円, ROI: {roi:.1f}%')
    print()

    print('【修正後（コース強制化あり）】')
    p = results_after['purchase']
    h = results_after['hit']
    b = results_after['bet']
    pay = results_after['payout']
    hr = (h / p * 100) if p > 0 else 0
    roi = (pay / b * 100) if b > 0 else 0
    profit = pay - b
    print(f'  購入: {p}件, 的中: {h}件, 的中率: {hr:.2f}%')
    print(f'  投資: {b:,.0f}円, 払戻: {pay:,.0f}円')
    print(f'  収支: {profit:+,.0f}円, ROI: {roi:.1f}%')
    print(f'  (内訳: 強制化適用レース {results_after["enforced_count"]}件, 強制化的中 {results_after["enforced_hit"]}件)')
    print()

    # 差分
    print('【差分】')
    d_purchase = results_after['purchase'] - results_before['purchase']
    d_hit = results_after['hit'] - results_before['hit']
    d_bet = results_after['bet'] - results_before['bet']
    d_payout = results_after['payout'] - results_before['payout']
    d_profit = (results_after['payout'] - results_after['bet']) - (results_before['payout'] - results_before['bet'])

    hr_before = (results_before['hit'] / results_before['purchase'] * 100) if results_before['purchase'] > 0 else 0
    hr_after = (results_after['hit'] / results_after['purchase'] * 100) if results_after['purchase'] > 0 else 0
    d_hr = hr_after - hr_before

    roi_before = (results_before['payout'] / results_before['bet'] * 100) if results_before['bet'] > 0 else 0
    roi_after = (results_after['payout'] / results_after['bet'] * 100) if results_after['bet'] > 0 else 0
    d_roi = roi_after - roi_before

    print(f'  購入変化: {d_purchase:+d}件')
    print(f'  的中変化: {d_hit:+d}件')
    print(f'  的中率変化: {d_hr:+.2f}pt')
    print(f'  収支変化: {d_profit:+,.0f}円')
    print(f'  ROI変化: {d_roi:+.1f}pt')
    print()

    # 月別詳細
    print('=' * 80)
    print('月別比較')
    print('=' * 80)
    print()
    print(f"{'月':<10} | {'修正前購入':>8} {'修正前的中':>8} {'修正前ROI':>10} | {'修正後購入':>8} {'修正後的中':>8} {'修正後ROI':>10}")
    print('-' * 80)

    all_months = sorted(set(results_before['by_month'].keys()) | set(results_after['by_month'].keys()))
    for month in all_months:
        mb = results_before['by_month'][month]
        ma = results_after['by_month'][month]

        roi_b = (mb['payout'] / mb['bet'] * 100) if mb['bet'] > 0 else 0
        roi_a = (ma['payout'] / ma['bet'] * 100) if ma['bet'] > 0 else 0

        print(f"{month:<10} | {mb['purchase']:>8} {mb['hit']:>8} {roi_b:>9.1f}% | {ma['purchase']:>8} {ma['hit']:>8} {roi_a:>9.1f}%")

    print()

    # 統計的有意性（簡易版）
    print('=' * 80)
    print('統計的有意性')
    print('=' * 80)
    print()

    # サンプルサイズ
    n_before = results_before['purchase']
    n_after = results_after['purchase']
    print(f'サンプルサイズ: 修正前 {n_before}件, 修正後 {n_after}件')

    # 的中率の差の検定（二項検定の近似）
    p1 = results_before['hit'] / n_before if n_before > 0 else 0
    p2 = results_after['hit'] / n_after if n_after > 0 else 0
    pooled_p = (results_before['hit'] + results_after['hit']) / (n_before + n_after) if (n_before + n_after) > 0 else 0

    if pooled_p > 0 and pooled_p < 1:
        se = (pooled_p * (1 - pooled_p) * (1/n_before + 1/n_after)) ** 0.5
        z = (p2 - p1) / se if se > 0 else 0
        print(f'的中率差: {(p2-p1)*100:.2f}pt')
        print(f'Z統計量: {z:.2f}')
        print(f'判定: {"有意差あり (|Z| > 1.96)" if abs(z) > 1.96 else "有意差なし"}')
    else:
        print('検定不能（データ不足）')

    # 強制化適用レースの詳細
    print()
    print('=' * 80)
    print('強制化適用レースの詳細分析')
    print('=' * 80)
    print()

    if enforced_details:
        # 1着的中率の変化
        enforced_1st_hit_after = sum(1 for d in enforced_details if d['actual_1st'] == 1)
        enforced_1st_hit_before = sum(1 for d in enforced_details if d['actual_1st'] == d['original_top'])
        print(f'強制化適用レース: {len(enforced_details)}件')
        print(f'  - 1コースが実際に1着: {enforced_1st_hit_after}件 ({enforced_1st_hit_after/len(enforced_details)*100:.1f}%)')
        print(f'  - 元の予測コースが1着: {enforced_1st_hit_before}件 ({enforced_1st_hit_before/len(enforced_details)*100:.1f}%)')
        print()

        # 3連単的中の変化
        hit_after_only = sum(1 for d in enforced_details if d['hit_after'] and not d['hit_before'])
        hit_before_only = sum(1 for d in enforced_details if d['hit_before'] and not d['hit_after'])
        hit_both = sum(1 for d in enforced_details if d['hit_before'] and d['hit_after'])
        hit_none = sum(1 for d in enforced_details if not d['hit_before'] and not d['hit_after'])

        print(f'3連単的中の変化（強制化適用レースのみ）:')
        print(f'  - 強制化後のみ的中: {hit_after_only}件')
        print(f'  - 強制化前のみ的中: {hit_before_only}件')
        print(f'  - 両方的中: {hit_both}件')
        print(f'  - 両方ハズレ: {hit_none}件')
        print()

        # サンプル表示
        print('強制化適用レースのサンプル（最初の10件）:')
        for d in enforced_details[:10]:
            status = '的中' if d['hit_after'] else 'ハズレ'
            print(f"  {d['race_date']} race_id={d['race_id']}: {d['combo_before']} -> {d['combo_after']} (実際:{d['actual_combo']}) [{status}]")
    else:
        print('購入対象レースでコース強制化が適用されたケースはありませんでした。')

    # 結果をサマリとして返す
    return {
        'before': {
            'purchase': results_before['purchase'],
            'hit': results_before['hit'],
            'hit_rate': hr_before,
            'bet': results_before['bet'],
            'payout': results_before['payout'],
            'profit': results_before['payout'] - results_before['bet'],
            'roi': roi_before,
        },
        'after': {
            'purchase': results_after['purchase'],
            'hit': results_after['hit'],
            'hit_rate': hr_after,
            'bet': results_after['bet'],
            'payout': results_after['payout'],
            'profit': results_after['payout'] - results_after['bet'],
            'roi': roi_after,
            'enforced_count': results_after['enforced_count'],
            'enforced_hit': results_after['enforced_hit'],
        },
        'diff': {
            'purchase': d_purchase,
            'hit': d_hit,
            'hit_rate': d_hr,
            'profit': d_profit,
            'roi': d_roi,
        }
    }


if __name__ == '__main__':
    main()
