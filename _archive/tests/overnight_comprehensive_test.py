"""
夜間包括的検証スクリプト

PCを起動したまま実行する長時間テスト。
結果はtemp/overnight/に保存されます。
"""

import sys
import os
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

from src.evaluation.walkforward_backtest import WalkForwardBacktest
from src.evaluation.ab_test_dynamic_integration import ABTestDynamicIntegration
import sqlite3

def log(message):
    """ログ出力"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}")

    # ログファイルにも記録
    with open('temp/overnight/execution.log', 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {message}\n")


def test_1_large_walkforward():
    """テスト1: 大規模Walk-forwardバックテスト（1ヶ月）"""
    log("=" * 80)
    log("テスト1: 大規模Walk-forwardバックテスト開始")
    log("=" * 80)

    backtest = WalkForwardBacktest()

    try:
        result = backtest.run_walkforward(
            start_date='2025-10-18',
            end_date='2025-11-17',
            train_days=30,
            test_days=7,
            step_days=7,
            output_dir='temp/overnight/walkforward_1month'
        )

        log("テスト1完了")
        log(f"  総ステップ数: {result['summary']['total_steps']}")
        log(f"  総評価レース数: {result['summary']['total_races']}")
        log(f"  1着的中率: {result['summary']['overall_hit_rate_1st']:.2%}")
        log(f"  結果保存先: {result['output_dir']}")

        return True
    except Exception as e:
        log(f"テスト1エラー: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def test_2_bad_weather_analysis():
    """テスト2: 悪天候時レースの精度検証"""
    log("=" * 80)
    log("テスト2: 悪天候時レース精度検証開始")
    log("=" * 80)

    from src.analysis.race_predictor import RacePredictor

    conn = sqlite3.connect('data/boatrace.db')
    cursor = conn.cursor()

    # 悪天候レースを抽出（風速3m以上 or 波高30cm以上）
    cursor.execute("""
        SELECT DISTINCT r.id, r.race_date, r.venue_code, r.race_number,
               rd.wind_speed, rd.wave_height, rd.weather
        FROM races r
        JOIN race_details rd ON r.id = rd.race_id
        JOIN results res ON r.id = res.race_id
        WHERE (rd.wind_speed >= 3 OR rd.wave_height >= 30)
        AND res.rank IS NOT NULL
        AND res.is_invalid = 0
        ORDER BY r.race_date DESC
        LIMIT 100
    """)

    bad_weather_races = cursor.fetchall()
    log(f"悪天候レース数: {len(bad_weather_races)}")

    if len(bad_weather_races) == 0:
        log("悪天候レースが見つかりませんでした")
        conn.close()
        return False

    predictor = RacePredictor()

    # 統計
    integrated_wins = 0
    pre_only_wins = 0
    total = 0

    details = []

    for race_id, race_date, venue, race_no, wind, wave, weather in bad_weather_races:
        try:
            # 実際の結果
            cursor.execute("""
                SELECT pit_number, rank FROM results
                WHERE race_id = ? AND rank IS NOT NULL AND is_invalid = 0
                ORDER BY rank
            """, (race_id,))
            actual = cursor.fetchall()
            if not actual:
                continue
            actual_winner = actual[0][0]

            # 統合スコアで予測
            predictions = predictor.predict_race(race_id)
            if not predictions:
                continue

            integrated_pred = predictions[0]['pit_number']

            # PRE単体での予測
            pre_only = sorted(predictions, key=lambda x: x.get('pre_score', 0), reverse=True)
            pre_pred = pre_only[0]['pit_number']

            # 的中判定
            if integrated_pred == actual_winner:
                integrated_wins += 1
            if pre_pred == actual_winner:
                pre_only_wins += 1

            total += 1

            details.append({
                'race_id': race_id,
                'date': race_date,
                'venue': venue,
                'race_no': race_no,
                'wind': wind,
                'wave': wave,
                'weather': weather,
                'actual': actual_winner,
                'integrated': integrated_pred,
                'pre_only': pre_pred,
                'int_hit': integrated_pred == actual_winner,
                'pre_hit': pre_pred == actual_winner
            })

        except Exception as e:
            log(f"レース{race_id}処理エラー: {e}")
            continue

    conn.close()

    # 結果保存
    if total > 0:
        int_rate = (integrated_wins / total) * 100
        pre_rate = (pre_only_wins / total) * 100

        log(f"悪天候レース検証完了: {total}レース")
        log(f"  統合スコア的中率: {int_rate:.1f}% ({integrated_wins}/{total})")
        log(f"  PRE単体的中率: {pre_rate:.1f}% ({pre_only_wins}/{total})")
        log(f"  改善効果: {int_rate - pre_rate:+.1f}ポイント")

        # 詳細を保存
        with open('temp/overnight/bad_weather_analysis.txt', 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("悪天候時レース精度検証結果\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"検証レース数: {total}\n")
            f.write(f"統合スコア的中率: {int_rate:.1f}% ({integrated_wins}/{total})\n")
            f.write(f"PRE単体的中率: {pre_rate:.1f}% ({pre_only_wins}/{total})\n")
            f.write(f"改善効果: {int_rate - pre_rate:+.1f}ポイント\n\n")

            f.write("【レース詳細】\n")
            f.write("日付       | 会場 | R# | 風速 | 波高 | 天候 | 実際 | 統合 | PRE | 統合結果 | PRE結果\n")
            f.write("-" * 100 + "\n")

            for d in details[:50]:  # 最大50件
                int_mark = '◎' if d['int_hit'] else '×'
                pre_mark = '◎' if d['pre_hit'] else '×'
                f.write(f"{d['date']} | {d['venue']:4s} | {d['race_no']:2d}R | "
                       f"{d['wind']:3.1f}m | {d['wave']:3.0f}cm | {d['weather']:4s} | "
                       f"{d['actual']}号 | {d['integrated']}号 | {d['pre_only']}号 | "
                       f"{int_mark:^8s} | {pre_mark:^7s}\n")

        log("詳細結果を temp/overnight/bad_weather_analysis.txt に保存")
        return True
    else:
        log("評価可能なレースがありませんでした")
        return False


def test_3_large_ab_test():
    """テスト3: 大規模A/Bテスト（1ヶ月）"""
    log("=" * 80)
    log("テスト3: 大規模A/Bテスト開始")
    log("=" * 80)

    ab_test = ABTestDynamicIntegration()

    try:
        comparison = ab_test.run_ab_test(
            start_date='2025-10-18',
            end_date='2025-11-17',
            output_dir='temp/overnight/ab_test_1month'
        )

        log("テスト3完了")
        log(f"  対象レース数: {comparison['total_races']}")
        log(f"  動的統合: {comparison['dynamic']['hit_rate_1st']:.2%}")
        log(f"  レガシー: {comparison['legacy']['hit_rate_1st']:.2%}")
        log(f"  改善率: {comparison['improvement']['hit_rate_1st']:+.2f}%")
        log(f"  結論: {comparison['conclusion']}")

        return True
    except Exception as e:
        log(f"テスト3エラー: {e}")
        import traceback
        log(traceback.format_exc())
        return False


def main():
    """メイン処理"""
    start_time = datetime.now()

    # 出力ディレクトリ作成
    os.makedirs('temp/overnight', exist_ok=True)

    log("=" * 80)
    log("夜間包括的検証開始")
    log("=" * 80)
    log(f"開始時刻: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("")

    results = {
        'test1': False,
        'test2': False,
        'test3': False
    }

    # テスト1: 大規模Walk-forward
    try:
        results['test1'] = test_1_large_walkforward()
    except Exception as e:
        log(f"テスト1で予期しないエラー: {e}")

    log("")

    # テスト2: 悪天候分析
    try:
        results['test2'] = test_2_bad_weather_analysis()
    except Exception as e:
        log(f"テスト2で予期しないエラー: {e}")

    log("")

    # テスト3: 大規模A/Bテスト
    try:
        results['test3'] = test_3_large_ab_test()
    except Exception as e:
        log(f"テスト3で予期しないエラー: {e}")

    # 終了
    end_time = datetime.now()
    elapsed = end_time - start_time

    log("")
    log("=" * 80)
    log("夜間包括的検証完了")
    log("=" * 80)
    log(f"終了時刻: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"実行時間: {elapsed}")
    log("")
    log("【テスト結果】")
    log(f"  テスト1 (大規模Walk-forward): {'成功' if results['test1'] else '失敗'}")
    log(f"  テスト2 (悪天候分析): {'成功' if results['test2'] else '失敗'}")
    log(f"  テスト3 (大規模A/Bテスト): {'成功' if results['test3'] else '失敗'}")
    log("")
    log("全結果は temp/overnight/ に保存されています")
    log("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("\n処理が中断されました")
    except Exception as e:
        log(f"\n致命的エラー: {e}")
        import traceback
        log(traceback.format_exc())
