# -*- coding: utf-8 -*-
"""
A・Bランク包括的分析スクリプト
1. 購入対象として追加すべきか検証
2. オッズ帯・級別のフィルタリング条件分析
3. 既存戦略への組み込み方法提案
"""
import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore')

import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'

import logging
logging.disable(logging.CRITICAL)

import sqlite3
from collections import defaultdict
from datetime import datetime

DB_PATH = 'data/boatrace.db'


def suppress_output():
    """出力抑制"""
    import sys
    class DevNull:
        def write(self, msg): pass
        def flush(self): pass
    return DevNull()


def get_race_data_fast(conn, start_date, end_date, limit=None):
    """高速でレースデータを取得（RacePredictorを使わない軽量版）"""
    cursor = conn.cursor()

    query = '''
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.grade
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN ? AND ?
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY r.race_date, r.id
    '''
    if limit:
        query += f' LIMIT {limit}'

    cursor.execute(query, (start_date, end_date))
    return cursor.fetchall()


def analyze_with_predictor(sample_size=500):
    """RacePredictorを使った分析（サンプリング）"""
    from src.analysis.race_predictor import RacePredictor

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 2024-2025年からサンプリング
    cursor.execute('''
        SELECT DISTINCT r.id, r.race_date
        FROM races r
        INNER JOIN results res ON res.race_id = r.id
        WHERE r.race_date BETWEEN '2024-01-01' AND '2025-12-18'
            AND res.is_invalid = 0
            AND EXISTS (
                SELECT 1 FROM entries e WHERE e.race_id = r.id
                GROUP BY e.race_id HAVING COUNT(*) = 6
            )
        ORDER BY RANDOM()
        LIMIT ?
    ''', (sample_size,))
    races = cursor.fetchall()

    print(f"サンプル数: {len(races)}")

    # 予測器初期化（エラー出力抑制）
    import io
    import contextlib

    with contextlib.redirect_stderr(io.StringIO()):
        predictor = RacePredictor(db_path=DB_PATH, use_cache=False)

    results = []

    for i, (race_id, race_date) in enumerate(races):
        if (i + 1) % 100 == 0:
            print(f"進捗: {i+1}/{len(races)}")

        try:
            with contextlib.redirect_stderr(io.StringIO()):
                predictions = predictor.predict_race(race_id)

            if not predictions or len(predictions) < 3:
                continue

            confidence = predictions[0].get('confidence', 'D')

            # 結果取得
            cursor.execute('''
                SELECT pit_number FROM results
                WHERE race_id = ? AND is_invalid = 0 AND rank IS NOT NULL
                ORDER BY CAST(rank AS INTEGER)
                LIMIT 3
            ''', (race_id,))
            res = cursor.fetchall()
            if len(res) < 3:
                continue

            actual = [int(r[0]) for r in res]

            # オッズ取得
            actual_comb = f'{actual[0]}-{actual[1]}-{actual[2]}'
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                          (race_id, actual_comb))
            row = cursor.fetchone()
            actual_odds = float(row[0]) if row else 0.0

            pred_1st = predictions[0]['pit_number']
            pred_2nd = predictions[1]['pit_number']
            pred_3rd = predictions[2]['pit_number']

            # 予測オッズ
            pred_comb = f'{pred_1st}-{pred_2nd}-{pred_3rd}'
            cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                          (race_id, pred_comb))
            row = cursor.fetchone()
            pred_odds = float(row[0]) if row else 0.0

            # 1コース級別
            cursor.execute('''
                SELECT rm.rank_class FROM entries e
                JOIN racer_master rm ON e.racer_id = rm.racer_id
                WHERE e.race_id = ? AND e.pit_number = 1
            ''', (race_id,))
            row = cursor.fetchone()
            course1_class = row[0] if row else 'Unknown'

            hit = (pred_1st == actual[0] and pred_2nd == actual[1] and pred_3rd == actual[2])
            hit_1st = pred_1st == actual[0]

            results.append({
                'race_id': race_id,
                'date': race_date,
                'year': race_date[:4],
                'confidence': confidence,
                'pred_odds': pred_odds,
                'actual_odds': actual_odds,
                'course1_class': course1_class,
                'hit': hit,
                'hit_1st': hit_1st,
                'payout': actual_odds * 100 if hit else 0,
                'pred_1st': pred_1st
            })

        except Exception as e:
            continue

    conn.close()
    return results


def print_section(title):
    """セクションヘッダー出力"""
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print()


def analyze_results(results):
    """結果分析"""

    # 全期間推計用の係数
    total_db_races = 97000  # 2020-2025年の概算
    scale = total_db_races / len(results) if results else 1

    # ========================================
    # 1. 購入対象として追加すべきか検証
    # ========================================
    print_section("1. A・Bランクを購入対象として追加すべきか")

    for conf in ['A', 'B', 'C', 'D']:
        data = [r for r in results if r['confidence'] == conf]
        if not data:
            continue

        total = len(data)
        hits = sum(1 for r in data if r['hit'])
        hits_1st = sum(1 for r in data if r['hit_1st'])
        payout = sum(r['payout'] for r in data)
        bet = total * 100

        hit_rate = hits / total * 100 if total > 0 else 0
        hit_1st_rate = hits_1st / total * 100 if total > 0 else 0
        roi = payout / bet * 100 if bet > 0 else 0

        est_total = int(total * scale)

        print(f"【{conf}ランク】")
        print(f"  サンプル数: {total} (推計 {est_total:,}件/6年)")
        print(f"  1着的中率: {hit_1st_rate:.1f}%")
        print(f"  3連単的中率: {hit_rate:.2f}%")
        print(f"  ROI: {roi:.1f}%")
        print(f"  収支: {payout - bet:+,.0f}円 (投資{bet:,}円)")

        # 判定
        if roi >= 100:
            print(f"  → ★ 購入推奨（ROI {roi:.1f}%）")
        elif roi >= 80:
            print(f"  → △ 条件付きで検討（ROI {roi:.1f}%）")
        else:
            print(f"  → × 購入非推奨（ROI {roi:.1f}%）")
        print()

    # B+C（現行戦略）との比較
    print("-" * 50)
    print("【参考】現行戦略（B+C）との比較")

    bc_data = [r for r in results if r['confidence'] in ['B', 'C']]
    if bc_data:
        total = len(bc_data)
        hits = sum(1 for r in bc_data if r['hit'])
        payout = sum(r['payout'] for r in bc_data)
        bet = total * 100
        roi = payout / bet * 100
        print(f"  B+C: {total}件, 的中率{hits/total*100:.2f}%, ROI {roi:.1f}%")

    abc_data = [r for r in results if r['confidence'] in ['A', 'B', 'C']]
    if abc_data:
        total = len(abc_data)
        hits = sum(1 for r in abc_data if r['hit'])
        payout = sum(r['payout'] for r in abc_data)
        bet = total * 100
        roi = payout / bet * 100
        print(f"  A+B+C: {total}件, 的中率{hits/total*100:.2f}%, ROI {roi:.1f}%")

    # ========================================
    # 2. オッズ帯・級別のフィルタリング条件
    # ========================================
    print_section("2. オッズ帯・級別のフィルタリング条件分析")

    odds_ranges = [
        (0, 10, '0-10倍'),
        (10, 20, '10-20倍'),
        (20, 30, '20-30倍'),
        (30, 50, '30-50倍'),
        (50, 100, '50-100倍'),
        (100, 9999, '100倍+')
    ]

    for conf in ['A', 'B']:
        print(f"【{conf}ランク オッズ帯別】")
        print(f"{'オッズ帯':^12} | {'件数':^6} | {'的中':^5} | {'的中率':^8} | {'ROI':^8} | 判定")
        print("-" * 60)

        conf_data = [r for r in results if r['confidence'] == conf]

        best_conditions = []

        for low, high, label in odds_ranges:
            subset = [r for r in conf_data if low <= r['pred_odds'] < high]
            if len(subset) < 3:
                continue

            total = len(subset)
            hits = sum(1 for r in subset if r['hit'])
            payout = sum(r['payout'] for r in subset)
            bet = total * 100

            hit_rate = hits / total * 100
            roi = payout / bet * 100 if bet > 0 else 0

            if roi >= 100:
                judge = "★推奨"
                best_conditions.append((label, total, roi))
            elif roi >= 80:
                judge = "△検討"
            else:
                judge = "×除外"

            print(f"{label:^12} | {total:>4} | {hits:>3} | {hit_rate:>6.2f}% | {roi:>6.1f}% | {judge}")

        print()

        if best_conditions:
            print(f"  → {conf}ランク推奨条件: ", end="")
            print(", ".join([f"{c[0]}(ROI{c[2]:.0f}%)" for c in best_conditions]))
        print()

    # 級別分析
    print("-" * 50)
    print("【級別分析（A・Bランク合算）】")
    print(f"{'級別':^8} | {'件数':^6} | {'的中':^5} | {'的中率':^8} | {'ROI':^8}")
    print("-" * 50)

    ab_data = [r for r in results if r['confidence'] in ['A', 'B']]

    for cls in ['A1', 'A2', 'B1', 'B2']:
        subset = [r for r in ab_data if r['course1_class'] == cls]
        if len(subset) < 3:
            continue

        total = len(subset)
        hits = sum(1 for r in subset if r['hit'])
        payout = sum(r['payout'] for r in subset)
        bet = total * 100

        hit_rate = hits / total * 100
        roi = payout / bet * 100 if bet > 0 else 0

        print(f"{cls:^8} | {total:>4} | {hits:>3} | {hit_rate:>6.2f}% | {roi:>6.1f}%")

    # 1コース予測時のみ
    print()
    print("-" * 50)
    print("【1コース予測時のみ（A・Bランク）】")

    course1_pred = [r for r in ab_data if r['pred_1st'] == 1]
    if course1_pred:
        total = len(course1_pred)
        hits = sum(1 for r in course1_pred if r['hit'])
        payout = sum(r['payout'] for r in course1_pred)
        bet = total * 100
        roi = payout / bet * 100 if bet > 0 else 0

        print(f"  1コース予測: {total}件, 的中率{hits/total*100:.2f}%, ROI {roi:.1f}%")

    non_course1 = [r for r in ab_data if r['pred_1st'] != 1]
    if non_course1:
        total = len(non_course1)
        hits = sum(1 for r in non_course1 if r['hit'])
        payout = sum(r['payout'] for r in non_course1)
        bet = total * 100
        roi = payout / bet * 100 if bet > 0 else 0

        print(f"  非1コース予測: {total}件, 的中率{hits/total*100:.2f}%, ROI {roi:.1f}%")

    # ========================================
    # 3. 既存戦略への組み込み方法
    # ========================================
    print_section("3. 既存戦略（B+C購入）への組み込み提案")

    # 最適条件の探索
    print("【最適条件の探索】")
    print()

    best_overall = []

    for conf in ['A', 'B']:
        conf_data = [r for r in results if r['confidence'] == conf]

        for low, high, label in odds_ranges:
            for cls in ['A1', 'A2', 'B1', 'B2', None]:
                if cls:
                    subset = [r for r in conf_data if low <= r['pred_odds'] < high and r['course1_class'] == cls]
                else:
                    subset = [r for r in conf_data if low <= r['pred_odds'] < high]

                if len(subset) < 5:  # 最低5件
                    continue

                total = len(subset)
                hits = sum(1 for r in subset if r['hit'])
                payout = sum(r['payout'] for r in subset)
                bet = total * 100
                roi = payout / bet * 100 if bet > 0 else 0

                if roi >= 100:
                    cls_label = cls if cls else "全級"
                    best_overall.append({
                        'conf': conf,
                        'odds': label,
                        'class': cls_label,
                        'n': total,
                        'hit_rate': hits / total * 100,
                        'roi': roi
                    })

    # ROI順にソート
    best_overall.sort(key=lambda x: x['roi'], reverse=True)

    if best_overall:
        print("ROI 100%以上の条件（上位10件）:")
        print(f"{'ランク':^6} | {'オッズ':^10} | {'級別':^6} | {'件数':^5} | {'的中率':^8} | {'ROI':^8}")
        print("-" * 60)

        for item in best_overall[:10]:
            print(f"{item['conf']:^6} | {item['odds']:^10} | {item['class']:^6} | {item['n']:>3} | {item['hit_rate']:>6.2f}% | {item['roi']:>6.1f}%")
    else:
        print("ROI 100%以上の条件は見つかりませんでした")

    print()
    print("-" * 50)
    print("【組み込み提案】")
    print()

    # A・Bランクの総合判定
    a_data = [r for r in results if r['confidence'] == 'A']
    b_data = [r for r in results if r['confidence'] == 'B']

    a_roi = sum(r['payout'] for r in a_data) / (len(a_data) * 100) * 100 if a_data else 0
    b_roi = sum(r['payout'] for r in b_data) / (len(b_data) * 100) * 100 if b_data else 0

    print("◆ Aランク戦略:")
    if a_roi >= 100:
        print(f"  → 全購入を推奨（ROI {a_roi:.1f}%）")
        print("  → 現行B+C戦略に追加可能")
    elif a_roi >= 80:
        print(f"  → 条件付き購入を検討（ROI {a_roi:.1f}%）")
        print("  → 高オッズ帯（30倍以上）に限定することを推奨")
    else:
        print(f"  → 購入非推奨（ROI {a_roi:.1f}%）")
    print()

    print("◆ Bランク戦略:")
    if b_roi >= 100:
        print(f"  → 全購入を推奨（ROI {b_roi:.1f}%）")
    elif b_roi >= 80:
        print(f"  → 現行通り条件付き購入（ROI {b_roi:.1f}%）")
        # ROI 100%以上の条件を抽出
        b_good = [item for item in best_overall if item['conf'] == 'B']
        if b_good:
            print("  → 以下の条件で絞り込み推奨:")
            for item in b_good[:3]:
                print(f"     - {item['odds']} x {item['class']}: ROI {item['roi']:.1f}%")
    else:
        print(f"  → フィルタリング必須（全体ROI {b_roi:.1f}%）")

    print()
    print("-" * 50)
    print("【実装案】")
    print()

    if a_roi >= 80 or any(item['conf'] == 'A' and item['roi'] >= 100 for item in best_overall):
        print("1. Aランク追加:")
        print("   - feature_flags.pyに 'include_confidence_a': True 追加")
        print("   - BetTargetEvaluator に Aランク条件を追加")
        if a_roi < 100:
            print("   - オッズフィルター（30倍以上）を適用")
    else:
        print("1. Aランク: 追加見送り（ROI不足）")

    print()

    if b_roi >= 80:
        print("2. Bランク最適化:")
        print("   - 現行の購入条件を維持")
        b_good = [item for item in best_overall if item['conf'] == 'B']
        if b_good:
            print("   - 以下の条件を優先購入:")
            for item in b_good[:3]:
                print(f"     {item['odds']} x {item['class']}")

    return best_overall


def main():
    print("=" * 70)
    print("A・Bランク包括的分析")
    print(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # サンプル分析実行
    print()
    print("RacePredictorを使用した分析を実行中...")
    print("（2024-2025年から500レースをサンプリング）")
    print()

    results = analyze_with_predictor(sample_size=500)

    print(f"\n有効データ: {len(results)}件")

    # 分析実行
    best_conditions = analyze_results(results)

    # サマリー
    print_section("総括")

    # 信頼度別のサンプル数
    conf_counts = defaultdict(int)
    for r in results:
        conf_counts[r['confidence']] += 1

    print("【サンプル内訳】")
    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf_counts[conf] > 0:
            print(f"  {conf}ランク: {conf_counts[conf]}件 ({conf_counts[conf]/len(results)*100:.1f}%)")

    print()
    print("【推定年間レース数（2020-2025年平均）】")
    scale = 97000 / len(results) if results else 1
    for conf in ['A', 'B']:
        est = int(conf_counts[conf] * scale)
        print(f"  {conf}ランク: 約{est:,}件/6年 → 約{est//6:,}件/年")

    print()
    print("分析完了")


if __name__ == '__main__':
    main()
