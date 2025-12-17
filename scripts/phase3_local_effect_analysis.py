# -*- coding: utf-8 -*-
"""
Phase 3: 局所的効果検証

全体では効果がなかった施策が、特定条件下で有効かを検証し、
ROI改善につながる最適化ルールを発見する。

2025-12-17 作成
"""
import sys
import sqlite3
import math
from pathlib import Path
from collections import defaultdict

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.betting.bet_target_evaluator import BetTargetEvaluator, BetStatus


def z_test_roi(roi_obs, roi_expected, n, bet_amount_per_unit=300):
    """
    ROIの統計的有意性を検定

    H0: 真のROI = roi_expected (100%)
    H1: 真のROI > roi_expected

    簡易的な正規近似を使用
    """
    if n < 5:
        return None, None

    # 的中率の推定（ROIと平均オッズから逆算は困難なため、別の方法を使用）
    # 簡易的にROI > 100%かどうかを判定するためのz検定
    # ROIの標準誤差を推定（大雑把な近似）
    # 真の収益率の標準偏差は sqrt(n) * 平均賭け金 * 的中率変動 に依存
    # ここでは簡略化してブートストラップ的な考え方を省略

    # 単純に二項検定的なアプローチ：
    # 仮にROI=100%なら期待収支=0、観測ROI-100%の標準誤差を推定

    # 標準偏差は大体オッズの1/sqrt(n)程度と仮定
    se = (roi_obs / 100) / math.sqrt(n) * 100  # 大雑把な推定
    if se == 0:
        return None, None

    z = (roi_obs - roi_expected) / se

    # p-value (片側検定)
    from scipy import stats
    p_value = 1 - stats.norm.cdf(z)

    return z, p_value


def analyze_local_effects():
    """局所的効果検証のメイン処理"""
    db_path = ROOT_DIR / 'data' / 'boatrace.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    evaluator = BetTargetEvaluator()

    # 全データを収集
    data = []

    # 2025年のレースを取得
    cursor.execute('''
        SELECT r.id as race_id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= '2025-01-01' AND r.race_date <= '2025-12-31'
        ORDER BY r.race_date, r.venue_code, r.race_number
    ''')
    races = cursor.fetchall()

    for race in races:
        race_id = race['race_id']
        venue_code = int(race['venue_code']) if race['venue_code'] else 0
        race_date = race['race_date']

        # 1コース級別を取得
        cursor.execute('SELECT racer_rank FROM entries WHERE race_id = ? AND pit_number = 1', (race_id,))
        c1 = cursor.fetchone()
        c1_rank = c1['racer_rank'] if c1 else 'B1'

        # 予測情報を取得（直前情報 = before）
        cursor.execute('''
            SELECT pit_number, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = 'before'
            ORDER BY total_score DESC
        ''', (race_id,))
        preds = cursor.fetchall()

        if len(preds) < 6:
            continue

        confidence = preds[0]['confidence']

        # 信頼度A, Bは除外
        if confidence in ['A', 'B']:
            continue

        top3 = [p['pit_number'] for p in preds[:3]]
        combo = f"{top3[0]}-{top3[1]}-{top3[2]}"
        top_pred = top3[0]  # 予測1着コース

        # オッズ取得
        cursor.execute('SELECT odds FROM trifecta_odds WHERE race_id = ? AND combination = ?',
                       (race_id, combo))
        odds_row = cursor.fetchone()

        if not odds_row:
            continue

        odds = odds_row['odds']

        # BetTargetEvaluatorで購入判定
        result = evaluator.evaluate(
            confidence=confidence,
            c1_rank=c1_rank,
            old_combo=combo,
            new_combo=combo,
            old_odds=odds,
            new_odds=odds,
            has_beforeinfo=True,
            venue_code=venue_code
        )

        # 購入対象でない場合はスキップ
        if result.status not in [BetStatus.TARGET_ADVANCE, BetStatus.TARGET_CONFIRMED]:
            continue

        bet_amount = result.bet_amount

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
        is_hit = (combo == actual_combo)

        # 払戻取得
        payout = 0
        if is_hit:
            cursor.execute('''
                SELECT amount FROM payouts
                WHERE race_id = ? AND bet_type = 'trifecta' AND combination = ?
            ''', (race_id, actual_combo))
            payout_row = cursor.fetchone()
            if payout_row:
                payout = (bet_amount / 100) * payout_row['amount']

        # オッズ帯を細かく分類
        if odds < 20:
            odds_band = '0-20'
        elif odds < 25:
            odds_band = '20-25'
        elif odds < 30:
            odds_band = '25-30'
        elif odds < 35:
            odds_band = '30-35'
        elif odds < 40:
            odds_band = '35-40'
        elif odds < 45:
            odds_band = '40-45'
        elif odds < 50:
            odds_band = '45-50'
        elif odds < 60:
            odds_band = '50-60'
        else:
            odds_band = '60+'

        data.append({
            'race_id': race_id,
            'race_date': race_date,
            'venue_code': venue_code,
            'c1_rank': c1_rank,
            'confidence': confidence,
            'top_pred': top_pred,  # 予測1着コース
            'combo': combo,
            'odds': odds,
            'odds_band': odds_band,
            'bet_amount': bet_amount,
            'is_hit': is_hit,
            'payout': payout,
        })

    conn.close()

    return data


def print_stats(data, label=""):
    """統計を表示する共通関数"""
    if not data:
        print(f"  データなし")
        return {'count': 0, 'hit': 0, 'bet': 0, 'payout': 0, 'roi': 0, 'hit_rate': 0, 'profit': 0}

    count = len(data)
    hit = sum(1 for d in data if d['is_hit'])
    bet = sum(d['bet_amount'] for d in data)
    payout = sum(d['payout'] for d in data)

    hit_rate = (hit / count * 100) if count > 0 else 0
    roi = (payout / bet * 100) if bet > 0 else 0
    profit = payout - bet

    return {
        'count': count,
        'hit': hit,
        'bet': bet,
        'payout': payout,
        'roi': roi,
        'hit_rate': hit_rate,
        'profit': profit
    }


def main():
    print("=" * 100)
    print("Phase 3: 局所的効果検証")
    print("=" * 100)
    print()

    # データ収集
    print("データ収集中...")
    data = analyze_local_effects()
    print(f"購入対象件数: {len(data)}件")
    print()

    # 全体統計
    print("=" * 100)
    print("1. 全体サマリー")
    print("=" * 100)
    total_stats = print_stats(data)
    print(f"  購入: {total_stats['count']}件")
    print(f"  的中: {total_stats['hit']}件 (的中率 {total_stats['hit_rate']:.2f}%)")
    print(f"  投資: {total_stats['bet']:,.0f}円")
    print(f"  払戻: {total_stats['payout']:,.0f}円")
    print(f"  収支: {total_stats['profit']:+,.0f}円")
    print(f"  ROI: {total_stats['roi']:.1f}%")
    print()

    # 1. 信頼度別分析
    print("=" * 100)
    print("2. 信頼度別分析（最優先）")
    print("=" * 100)
    print()

    confidence_results = {}
    for conf in ['C', 'D']:
        filtered = [d for d in data if d['confidence'] == conf]
        stats = print_stats(filtered)
        confidence_results[conf] = stats

        print(f"【信頼度{conf}】")
        print(f"  購入: {stats['count']}件")
        print(f"  的中: {stats['hit']}件 (的中率 {stats['hit_rate']:.2f}%)")
        print(f"  投資: {stats['bet']:,.0f}円")
        print(f"  払戻: {stats['payout']:,.0f}円")
        print(f"  収支: {stats['profit']:+,.0f}円")
        print(f"  ROI: {stats['roi']:.1f}%")
        print()

    # 2. 予測コース別分析
    print("=" * 100)
    print("3. 予測コース別分析")
    print("=" * 100)
    print()

    print(f"{'コース':<8} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資':<14} {'払戻':<14} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    course_results = {}
    for course in range(1, 7):
        filtered = [d for d in data if d['top_pred'] == course]
        stats = print_stats(filtered)
        course_results[course] = stats

        if stats['count'] > 0:
            print(f"{course}コース    {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['bet']:>13,.0f} {stats['payout']:>13,.0f} {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 3. オッズ帯別分析
    print("=" * 100)
    print("4. オッズ帯別分析")
    print("=" * 100)
    print()

    print(f"{'オッズ帯':<12} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資':<14} {'払戻':<14} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    odds_bands = ['0-20', '20-25', '25-30', '30-35', '35-40', '40-45', '45-50', '50-60', '60+']
    odds_results = {}
    for band in odds_bands:
        filtered = [d for d in data if d['odds_band'] == band]
        stats = print_stats(filtered)
        odds_results[band] = stats

        if stats['count'] > 0:
            print(f"{band}倍       {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['bet']:>13,.0f} {stats['payout']:>13,.0f} {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 4. 交差分析: 信頼度 × 予測コース
    print("=" * 100)
    print("5. 交差分析: 信頼度 × 予測コース")
    print("=" * 100)
    print()

    print(f"{'条件':<20} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資':<14} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    cross_conf_course = {}
    for conf in ['C', 'D']:
        for course in range(1, 7):
            filtered = [d for d in data if d['confidence'] == conf and d['top_pred'] == course]
            stats = print_stats(filtered)
            key = f"{conf} × {course}コース"
            cross_conf_course[key] = stats

            if stats['count'] >= 5:  # サンプル5件以上のみ表示
                print(f"{key:<20} {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['bet']:>13,.0f} {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 5. 交差分析: 信頼度 × オッズ帯
    print("=" * 100)
    print("6. 交差分析: 信頼度 × オッズ帯")
    print("=" * 100)
    print()

    print(f"{'条件':<20} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資':<14} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    cross_conf_odds = {}
    for conf in ['C', 'D']:
        for band in odds_bands:
            filtered = [d for d in data if d['confidence'] == conf and d['odds_band'] == band]
            stats = print_stats(filtered)
            key = f"{conf} × {band}倍"
            cross_conf_odds[key] = stats

            if stats['count'] >= 5:
                print(f"{key:<20} {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['bet']:>13,.0f} {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 6. 交差分析: 予測コース × オッズ帯
    print("=" * 100)
    print("7. 交差分析: 予測コース × オッズ帯")
    print("=" * 100)
    print()

    print(f"{'条件':<20} {'購入':<8} {'的中':<8} {'的中率':<10} {'投資':<14} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    cross_course_odds = {}
    for course in range(1, 7):
        for band in odds_bands:
            filtered = [d for d in data if d['top_pred'] == course and d['odds_band'] == band]
            stats = print_stats(filtered)
            key = f"{course}コース × {band}倍"
            cross_course_odds[key] = stats

            if stats['count'] >= 5:
                print(f"{key:<20} {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['bet']:>13,.0f} {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 7. 三重交差分析: 信頼度 × 予測コース × オッズ帯（主要な組み合わせのみ）
    print("=" * 100)
    print("8. 三重交差分析（30件以上のみ）")
    print("=" * 100)
    print()

    print(f"{'条件':<30} {'購入':<8} {'的中':<8} {'的中率':<10} {'収支':<14} {'ROI':<10}")
    print("-" * 100)

    triple_cross = []
    for conf in ['C', 'D']:
        for course in range(1, 7):
            for band in odds_bands:
                filtered = [d for d in data if d['confidence'] == conf and d['top_pred'] == course and d['odds_band'] == band]
                stats = print_stats(filtered)
                key = f"{conf} × {course}コース × {band}倍"

                if stats['count'] >= 30:
                    triple_cross.append((key, stats))

    # ROIでソート
    triple_cross.sort(key=lambda x: x[1]['roi'], reverse=True)

    for key, stats in triple_cross:
        print(f"{key:<30} {stats['count']:<8} {stats['hit']:<8} {stats['hit_rate']:>7.2f}% {stats['profit']:>+13,.0f} {stats['roi']:>8.1f}%")

    print()

    # 8. 改善施策の検討
    print("=" * 100)
    print("9. 改善施策の検討")
    print("=" * 100)
    print()

    # 施策1: 6コース予測除外
    print("【施策1】6コース予測除外")
    filtered_no6 = [d for d in data if d['top_pred'] != 6]
    stats_no6 = print_stats(filtered_no6)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_no6['roi']:.1f}%, 収支 {stats_no6['profit']:+,.0f}円 ({stats_no6['count']}件)")

    delta_roi = stats_no6['roi'] - total_stats['roi']
    delta_profit = stats_no6['profit'] - total_stats['profit']
    print(f"  効果: ROI {delta_roi:+.1f}pt, 収支 {delta_profit:+,.0f}円")

    # 除外される6コース予測の詳細
    course6_stats = course_results.get(6, {})
    if course6_stats.get('count', 0) > 0:
        print(f"  除外対象: {course6_stats['count']}件 (ROI {course6_stats['roi']:.1f}%, 収支 {course6_stats['profit']:+,.0f}円)")
    print()

    # 施策2: 低ROIコース除外（5,6コース）
    print("【施策2】5,6コース予測除外")
    filtered_no56 = [d for d in data if d['top_pred'] not in [5, 6]]
    stats_no56 = print_stats(filtered_no56)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_no56['roi']:.1f}%, 収支 {stats_no56['profit']:+,.0f}円 ({stats_no56['count']}件)")

    delta_roi = stats_no56['roi'] - total_stats['roi']
    delta_profit = stats_no56['profit'] - total_stats['profit']
    print(f"  効果: ROI {delta_roi:+.1f}pt, 収支 {delta_profit:+,.0f}円")
    print()

    # 施策3: 信頼度Dのみ購入
    print("【施策3】信頼度Dのみ購入")
    filtered_d = [d for d in data if d['confidence'] == 'D']
    stats_d = print_stats(filtered_d)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_d['roi']:.1f}%, 収支 {stats_d['profit']:+,.0f}円 ({stats_d['count']}件)")

    delta_roi = stats_d['roi'] - total_stats['roi']
    delta_profit = stats_d['profit'] - total_stats['profit']
    print(f"  効果: ROI {delta_roi:+.1f}pt, 収支 {delta_profit:+,.0f}円")
    print()

    # 施策4: 高ROIオッズ帯に限定（40-50倍）
    print("【施策4】オッズ40-50倍に限定")
    filtered_4050 = [d for d in data if 40 <= d['odds'] < 50]
    stats_4050 = print_stats(filtered_4050)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_4050['roi']:.1f}%, 収支 {stats_4050['profit']:+,.0f}円 ({stats_4050['count']}件)")

    delta_roi = stats_4050['roi'] - total_stats['roi']
    delta_profit = stats_4050['profit'] - total_stats['profit']
    print(f"  効果: ROI {delta_roi:+.1f}pt, 収支 {delta_profit:+,.0f}円")
    print()

    # 施策5: 複合施策（信頼度D + 3コース予測）
    print("【施策5】信頼度D + 3コース予測")
    filtered_d3 = [d for d in data if d['confidence'] == 'D' and d['top_pred'] == 3]
    stats_d3 = print_stats(filtered_d3)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_d3['roi']:.1f}%, 収支 {stats_d3['profit']:+,.0f}円 ({stats_d3['count']}件)")

    delta_roi = stats_d3['roi'] - total_stats['roi']
    delta_profit = stats_d3['profit'] - total_stats['profit']
    print(f"  効果: ROI {delta_roi:+.1f}pt, 収支 {delta_profit:+,.0f}円")
    print()

    # 施策6: 除外条件の組み合わせ（6コース除外 + 信頼度C × 低ROIコース除外）
    print("【施策6】6コース除外のみ（最小限の変更）")
    filtered_simple = [d for d in data if d['top_pred'] != 6]
    stats_simple = print_stats(filtered_simple)

    print(f"  変更前: ROI {total_stats['roi']:.1f}%, 収支 {total_stats['profit']:+,.0f}円 ({total_stats['count']}件)")
    print(f"  変更後: ROI {stats_simple['roi']:.1f}%, 収支 {stats_simple['profit']:+,.0f}円 ({stats_simple['count']}件)")
    print()

    # 年間換算
    print("=" * 100)
    print("10. 年間収支換算")
    print("=" * 100)
    print()

    # 現在のデータ期間を計算（2025年の日数）
    from datetime import datetime
    dates = sorted(set(d['race_date'] for d in data))
    if dates:
        first_date = datetime.strptime(dates[0], '%Y-%m-%d')
        last_date = datetime.strptime(dates[-1], '%Y-%m-%d')
        days = (last_date - first_date).days + 1

        if days > 0:
            daily_profit = total_stats['profit'] / days
            annual_profit = daily_profit * 365

            print(f"  データ期間: {dates[0]} 〜 {dates[-1]} ({days}日間)")
            print(f"  期間収支: {total_stats['profit']:+,.0f}円")
            print(f"  日次収支: {daily_profit:+,.0f}円/日")
            print(f"  年間換算: {annual_profit:+,.0f}円/年")

    print()
    print("=" * 100)

    return {
        'data': data,
        'total_stats': total_stats,
        'confidence_results': confidence_results,
        'course_results': course_results,
        'odds_results': odds_results,
        'cross_conf_course': cross_conf_course,
        'cross_conf_odds': cross_conf_odds,
        'cross_course_odds': cross_course_odds,
    }


if __name__ == '__main__':
    results = main()
