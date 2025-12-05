"""
3連単5点買いバックテストスクリプト

現在の予想ロジックで3連単5点を購入した場合の的中率・回収率を検証
"""

import sys
import os
import io

# 文字コード問題を回避
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from datetime import datetime, timedelta
from src.analysis.race_predictor import RacePredictor
from collections import defaultdict
import json


def get_trifecta_payout(cursor, race_id, combination):
    """3連単払戻金を取得（100円あたり）"""
    try:
        cursor.execute("""
            SELECT amount
            FROM payouts
            WHERE race_id = ?
            AND bet_type = 'trifecta'
            AND combination = ?
        """, (race_id, combination))
        result = cursor.fetchone()
        return int(result[0]) if result else None
    except:
        return None


def get_actual_result(cursor, race_id):
    """実際のレース結果（1-2-3着）を取得"""
    cursor.execute("""
        SELECT pit_number
        FROM results
        WHERE race_id = ? AND is_invalid = 0
        ORDER BY rank
        LIMIT 3
    """, (race_id,))
    results = cursor.fetchall()
    if len(results) >= 3:
        return f"{results[0][0]}-{results[1][0]}-{results[2][0]}"
    return None


def format_currency(amount):
    """金額をフォーマット"""
    return f"¥{amount:,.0f}"


def main():
    print("=" * 80)
    print("3連単5点買いバックテスト")
    print("=" * 80)
    print()

    db_path = 'data/boatrace.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # テスト期間を設定（過去6ヶ月分から1000レースサンプリング）
    cursor.execute("""
        SELECT r.id, r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE EXISTS (
            SELECT 1 FROM results res
            WHERE res.race_id = r.id AND res.rank IS NOT NULL AND res.is_invalid = 0
        )
        AND EXISTS (
            SELECT 1 FROM race_details rd
            WHERE rd.race_id = r.id
        )
        AND EXISTS (
            SELECT 1 FROM payouts p
            WHERE p.race_id = r.id AND p.bet_type = 'trifecta'
        )
        AND r.race_date >= date('now', '-6 months')
        ORDER BY r.race_date DESC, r.id DESC
        LIMIT 1000
    """)
    all_races = cursor.fetchall()

    print(f"テスト対象: {len(all_races)}レース")
    print(f"期間: {all_races[-1][1]} 〜 {all_races[0][1]}")
    print()

    # 予測エンジン初期化
    predictor = RacePredictor(db_path=db_path)

    # 統計データ
    stats = {
        'total_races': 0,
        'valid_predictions': 0,
        'hits': 0,
        'total_bet': 0,
        'total_return': 0,
        'odds_available': 0,
        'prediction_errors': 0,
        'race_details': []
    }

    # 会場別・月別統計
    venue_stats = defaultdict(lambda: {'races': 0, 'hits': 0, 'bet': 0, 'return': 0})
    monthly_stats = defaultdict(lambda: {'races': 0, 'hits': 0, 'bet': 0, 'return': 0})

    print("予測実行中...\n")

    for idx, (race_id, race_date, venue_code, race_number) in enumerate(all_races, 1):
        stats['total_races'] += 1

        # 進捗表示（100レースごと）
        if idx % 100 == 0:
            print(f"  進捗: {idx}/{len(all_races)} レース ({idx/len(all_races)*100:.1f}%) - 的中{stats['hits']}件 的中率{stats['hits']/stats['valid_predictions']*100 if stats['valid_predictions'] > 0 else 0:.1f}%")

        try:
            # 予測実行（各艇のスコアと順位予測を取得）
            predictions = predictor.predict_race_by_key(
                race_date=race_date,
                venue_code=venue_code,
                race_number=race_number
            )

            if not predictions or len(predictions) < 6:
                stats['prediction_errors'] += 1
                continue

            # スコア順にソートして上位3艇を取得
            sorted_predictions = sorted(predictions, key=lambda x: x.get('total_score', 0), reverse=True)
            top_3_pits = [p['pit_number'] for p in sorted_predictions[:3]]

            # 上位3艇で3連単の組み合わせを生成（3P3 = 6通り）
            # そのうち上位5つを選択（スコア差でランク付け）
            from itertools import permutations

            trifecta_combinations = []
            for perm in permutations(top_3_pits, 3):
                combination = f"{perm[0]}-{perm[1]}-{perm[2]}"
                # スコア差を計算（1着-2着-3着のスコア合計）
                score_sum = sum([sorted_predictions[i]['total_score'] for i, p in enumerate(sorted_predictions[:3]) if p['pit_number'] in perm])
                trifecta_combinations.append((combination, score_sum))

            # スコア順にソート
            trifecta_combinations.sort(key=lambda x: x[1], reverse=True)
            top_5_combinations = [combo[0] for combo in trifecta_combinations[:5]]

            if len(top_5_combinations) < 5:
                stats['prediction_errors'] += 1
                continue

            stats['valid_predictions'] += 1

            # 実際の結果を取得
            actual_result = get_actual_result(cursor, race_id)
            if not actual_result:
                continue

            # 的中判定
            is_hit = actual_result in top_5_combinations

            # 購入金額（1点100円 × 5点 = 500円）
            bet_amount = 500
            stats['total_bet'] += bet_amount

            # 的中した場合の払戻
            return_amount = 0
            payout_value = None
            if is_hit:
                stats['hits'] += 1
                payout_value = get_trifecta_payout(cursor, race_id, actual_result)
                if payout_value:
                    return_amount = payout_value  # 100円購入での払戻金額
                    stats['total_return'] += return_amount
                    stats['odds_available'] += 1

            # 会場別統計
            venue_stats[venue_code]['races'] += 1
            venue_stats[venue_code]['bet'] += bet_amount
            if is_hit:
                venue_stats[venue_code]['hits'] += 1
                venue_stats[venue_code]['return'] += return_amount

            # 月別統計
            month_key = race_date[:7]  # YYYY-MM
            monthly_stats[month_key]['races'] += 1
            monthly_stats[month_key]['bet'] += bet_amount
            if is_hit:
                monthly_stats[month_key]['hits'] += 1
                monthly_stats[month_key]['return'] += return_amount

            # 詳細記録（最初の10件と的中したレースのみ）
            if len(stats['race_details']) < 10 or is_hit:
                stats['race_details'].append({
                    'race_id': race_id,
                    'date': race_date,
                    'venue': venue_code,
                    'race_no': race_number,
                    'predicted': top_5_combinations,
                    'actual': actual_result,
                    'hit': is_hit,
                    'payout': payout_value,
                    'return': return_amount
                })

        except Exception as e:
            print(f"  エラー (Race {race_id}): {e}")
            stats['prediction_errors'] += 1
            continue

    conn.close()

    # 結果表示
    print("\n" + "=" * 80)
    print("バックテスト結果")
    print("=" * 80)
    print()

    print("【全体サマリー】")
    print(f"  総レース数: {stats['total_races']} レース")
    print(f"  予測成功: {stats['valid_predictions']} レース")
    print(f"  予測エラー: {stats['prediction_errors']} レース")
    print()

    if stats['valid_predictions'] > 0:
        hit_rate = (stats['hits'] / stats['valid_predictions']) * 100
        recovery_rate = (stats['total_return'] / stats['total_bet']) * 100 if stats['total_bet'] > 0 else 0
        profit = stats['total_return'] - stats['total_bet']

        print("【3連単5点買い成績】")
        print(f"  的中数: {stats['hits']} / {stats['valid_predictions']} レース")
        print(f"  的中率: {hit_rate:.2f}%")
        print()
        print(f"  総購入金額: {format_currency(stats['total_bet'])} (1レース¥500 × {stats['valid_predictions']}レース)")
        print(f"  総払戻金額: {format_currency(stats['total_return'])}")
        print(f"  収支: {format_currency(profit)} ({'黒字' if profit >= 0 else '赤字'})")
        print(f"  回収率: {recovery_rate:.2f}%")
        print()

        if stats['odds_available'] > 0:
            print(f"  ※オッズデータ取得可能: {stats['odds_available']} / {stats['hits']} 的中")
            print(f"    (オッズ未取得の的中は払戻計算に含まれていません)")
            print()

        # 理論的な期待値計算
        print("【参考: 損益分岐点分析】")
        print(f"  現在の的中率: {hit_rate:.2f}%")
        print(f"  現在の回収率: {recovery_rate:.2f}%")
        print()

        if stats['odds_available'] > 0:
            avg_payout = stats['total_return'] / stats['hits'] if stats['hits'] > 0 else 0
            print(f"  平均配当: {avg_payout:.0f}円（100円購入時）")
            breakeven_rate = (500 / avg_payout * 100) if avg_payout > 0 else 0  # 5点買い=500円
            print(f"  損益分岐点的中率: {breakeven_rate:.2f}%")
            print()

            if hit_rate > breakeven_rate:
                print(f"  ✓ 現在の的中率({hit_rate:.2f}%)は損益分岐点({breakeven_rate:.2f}%)を上回っています")
            else:
                print(f"  ✗ 現在の的中率({hit_rate:.2f}%)は損益分岐点({breakeven_rate:.2f}%)を下回っています")
            print()

        # 会場別成績（上位5会場）
        print("【会場別成績トップ5】")
        venue_results = []
        for venue, data in venue_stats.items():
            if data['races'] >= 5:  # 5レース以上の会場のみ
                v_hit_rate = (data['hits'] / data['races']) * 100
                v_recovery = (data['return'] / data['bet']) * 100 if data['bet'] > 0 else 0
                venue_results.append({
                    'venue': venue,
                    'races': data['races'],
                    'hit_rate': v_hit_rate,
                    'recovery': v_recovery,
                    'profit': data['return'] - data['bet']
                })

        # 的中率でソート
        venue_results.sort(key=lambda x: x['hit_rate'], reverse=True)
        for v in venue_results[:5]:
            venue_name = v['venue']
            print(f"  {venue_name}場: 的中率{v['hit_rate']:.1f}% ({v['races']}R) | "
                  f"回収率{v['recovery']:.1f}% | 収支{format_currency(v['profit'])}")
        print()

        # 月別推移
        print("【月別成績推移】")
        for month in sorted(monthly_stats.keys()):
            data = monthly_stats[month]
            m_hit_rate = (data['hits'] / data['races']) * 100
            m_recovery = (data['return'] / data['bet']) * 100 if data['bet'] > 0 else 0
            m_profit = data['return'] - data['bet']
            print(f"  {month}: 的中率{m_hit_rate:.1f}% ({data['races']}R) | "
                  f"回収率{m_recovery:.1f}% | 収支{format_currency(m_profit)}")
        print()

        # サンプル表示
        print("【予測サンプル（最初の5件）】")
        for detail in stats['race_details'][:5]:
            venue_str = str(detail['venue'])
            print(f"\n  レース: {detail['date']} {venue_str}場 {detail['race_no']}R")
            print(f"  予測5点: {', '.join(detail['predicted'])}")
            print(f"  実際結果: {detail['actual']} {'✓的中' if detail['hit'] else '✗'}")
            if detail['hit'] and detail['payout']:
                print(f"  配当: {detail['payout']}円 (払戻: {format_currency(detail['return'])})")
        print()

        # 結果をJSONで保存
        output_file = 'temp/backtest_3tan_5points_result.json'
        os.makedirs('temp', exist_ok=True)

        result_data = {
            'test_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_races': stats['valid_predictions'],
            'hit_rate': hit_rate,
            'recovery_rate': recovery_rate,
            'total_bet': stats['total_bet'],
            'total_return': stats['total_return'],
            'profit': profit,
            'venue_stats': {k: dict(v) for k, v in venue_stats.items()},
            'monthly_stats': {k: dict(v) for k, v in monthly_stats.items()}
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)

        print(f"詳細結果を保存しました: {output_file}")
        print()

    else:
        print("予測可能なレースがありませんでした。")

    print("=" * 80)


if __name__ == '__main__':
    main()
