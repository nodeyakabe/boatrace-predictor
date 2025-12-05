"""
レース直前データを使った予測更新スクリプト

使い方:
1. 初期予測を生成（generate_one_date.py など）
2. 展示データを収集（collect_exhibition_data.py）
3. レース条件を収集（collect_race_conditions.py）
4. 実際の進入コースを収集（collect_actual_courses.py）
5. 本スクリプトで予測を更新
"""

import sys
import os

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
from config.settings import DATABASE_PATH
from src.analysis.prediction_updater import PredictionUpdater


def display_prediction_changes(race_id: int):
    """予測の変更点を詳細表示"""

    updater = PredictionUpdater()

    # レース情報を取得
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.race_date, r.venue_code, r.race_number
        FROM races r
        WHERE r.id = ?
    """, (race_id,))

    race_info = cursor.fetchone()
    if not race_info:
        print(f"エラー: レースID {race_id} が見つかりません")
        return

    race_date, venue_code, race_number = race_info

    print("=" * 80)
    print(f"予測更新: {race_date} 会場{int(venue_code):02d} {int(race_number):2d}R")
    print("=" * 80)

    # 利用可能なデータをチェック
    cursor.execute("SELECT COUNT(*) FROM exhibition_data WHERE race_id = ?", (race_id,))
    has_exhibition = cursor.fetchone()[0] > 0

    cursor.execute("SELECT COUNT(*) FROM race_conditions WHERE race_id = ?", (race_id,))
    has_conditions = cursor.fetchone()[0] > 0

    cursor.execute("SELECT COUNT(*) FROM actual_courses WHERE race_id = ?", (race_id,))
    has_courses = cursor.fetchone()[0] > 0

    print("\n利用可能なデータ:")
    print(f"  展示データ: {'✓' if has_exhibition else '×'}")
    print(f"  レース条件: {'✓' if has_conditions else '×'}")
    print(f"  実際の進入: {'✓' if has_courses else '×'}")

    if not (has_exhibition or has_conditions or has_courses):
        print("\nエラー: レース直前データが1つもありません")
        print("先にデータ収集スクリプトを実行してください:")
        print("  • python collect_exhibition_data.py <race_id>")
        print("  • python collect_race_conditions.py <race_id>")
        print("  • python collect_actual_courses.py <race_id>")
        conn.close()
        return

    conn.close()

    # 予測を更新
    print("\n予測を更新中...")
    result = updater.update_prediction_with_exhibition_data(race_id)

    if not result['success']:
        print(f"\nエラー: {result.get('error', '不明なエラー')}")
        return

    changes = result['changes']

    print("\n" + "=" * 80)
    print("予測更新完了")
    print("=" * 80)

    if not changes:
        print("\n変更なし（すべての予測が変更前と同じです）")
        return

    print(f"\n変更があった艇: {len(changes)}艇")
    print("-" * 80)

    # 変更を詳細表示
    for pit_number in sorted(changes.keys()):
        change = changes[pit_number]
        initial = change['initial']
        updated = change['updated']
        adj = change['adjustments']

        print(f"\n【{pit_number}号艇】")

        # スコア変更
        score_diff = updated['total_score'] - initial['total_score']
        print(f"  総合点: {initial['total_score']:.1f} → {updated['total_score']:.1f} ({score_diff:+.1f})")

        # 信頼度変更
        if updated['confidence'] != initial['confidence']:
            print(f"  信頼度: {initial['confidence']} → {updated['confidence']} ⚠ 変更")
        else:
            print(f"  信頼度: {updated['confidence']} (変更なし)")

        # 内訳
        print(f"  内訳:")
        if adj['course'] != 0:
            print(f"    コース: {initial['course_score']:.1f} → {updated['course_score']:.1f} ({adj['course']:+.1f})")
        if adj['racer'] != 0:
            print(f"    選手:   {initial['racer_score']:.1f} → {updated['racer_score']:.1f} ({adj['racer']:+.1f})")
        if adj['motor'] != 0:
            print(f"    モーター: {initial['motor_score']:.1f} → {updated['motor_score']:.1f} ({adj['motor']:+.1f})")

        # 変更理由
        print(f"  理由:")
        for reason in change['reasons']:
            if reason and reason not in ['展示データなし', '進入コース情報なし', '気象データなし',
                                          '展示データ影響なし', '気象影響軽微']:
                print(f"    • {reason}")

    # 最終予測順位を表示
    print("\n" + "=" * 80)
    print("更新後の予測")
    print("=" * 80)

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            rp.rank_prediction,
            rp.pit_number,
            e.racer_name,
            rp.total_score,
            rp.confidence
        FROM race_predictions rp
        JOIN entries e ON rp.race_id = e.race_id AND rp.pit_number = e.pit_number
        WHERE rp.race_id = ?
        ORDER BY rp.rank_prediction
    """, (race_id,))

    predictions = cursor.fetchall()

    print("\n順位 | 艇番 | 選手名           | スコア | 信頼度 | 変更")
    print("-" * 80)
    for rank, pit, name, score, conf in predictions:
        changed_mark = "⚠" if pit in changes else " "
        print(f" {rank}位  |  {pit}  | {name:16s} | {score:5.1f}  |   {conf}   |  {changed_mark}")

    conn.close()

    print("=" * 80)


def main():
    if len(sys.argv) < 2:
        print("使用方法: python repredict_race.py <race_id>")
        print("例: python repredict_race.py 12345")
        print()
        print("事前準備:")
        print("  1. 初期予測を生成済みであること")
        print("  2. 以下のいずれかのデータを収集済みであること:")
        print("     • python collect_exhibition_data.py <race_id>")
        print("     • python collect_race_conditions.py <race_id>")
        print("     • python collect_actual_courses.py <race_id>")
        return

    try:
        race_id = int(sys.argv[1])
        display_prediction_changes(race_id)
    except ValueError:
        print("エラー: race_id は整数で指定してください")
    except Exception as e:
        print(f"エラー: {e}")


if __name__ == "__main__":
    main()
