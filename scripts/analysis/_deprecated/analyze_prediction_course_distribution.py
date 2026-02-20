"""
予測コース分布と精度分析スクリプト

問題: 1コース予測時は精度62.2%だが、2-6コース予測時は精度25%程度
目的: 1コース以外を予測する条件を特定し、改善方針を立てる
"""
import os
import sys
import sqlite3
from datetime import datetime

# プロジェクトルートをパスに追加
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)


def analyze_prediction_course_distribution(db_path: str, year: int = 2025):
    """予測コース別の分布と精度を分析"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("=" * 100)
    print(f"{year}年 予測コース分布と精度分析")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # 1. 予測コース別の分布と精度（信頼度別）
    print("\n" + "=" * 100)
    print("[1] 信頼度×予測コース別の精度")
    print("=" * 100)

    cursor.execute("""
        SELECT
            rp.confidence,
            rp.pit_number as predicted_course,
            COUNT(*) as total,
            SUM(CASE WHEN rp.pit_number = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        GROUP BY rp.confidence, rp.pit_number
        ORDER BY rp.confidence, rp.pit_number
    """, (f'{year}-01-01', f'{year}-12-31'))

    results = cursor.fetchall()

    # 信頼度ごとにサマリー
    confidence_summary = {}
    for conf, course, total, correct in results:
        if conf not in confidence_summary:
            confidence_summary[conf] = {'total': 0, 'correct': 0, 'by_course': {}}
        confidence_summary[conf]['total'] += total
        confidence_summary[conf]['correct'] += correct
        confidence_summary[conf]['by_course'][course] = {
            'total': total,
            'correct': correct,
            'accuracy': (correct / total * 100) if total > 0 else 0
        }

    for conf in ['A', 'B', 'C', 'D', 'E']:
        if conf not in confidence_summary:
            continue
        summary = confidence_summary[conf]
        overall_acc = (summary['correct'] / summary['total'] * 100) if summary['total'] > 0 else 0

        print(f"\n信頼度{conf}: 全体的中率 {overall_acc:.1f}% ({summary['correct']:,}/{summary['total']:,})")
        print("-" * 80)
        print(f"  コース | 予測数 | 的中数 | 精度    | 予測割合")
        print("-" * 80)

        for course in range(1, 7):
            if course in summary['by_course']:
                data = summary['by_course'][course]
                ratio = (data['total'] / summary['total'] * 100) if summary['total'] > 0 else 0
                mark = "" if data['accuracy'] >= 50 else " [低精度]"
                print(f"  {course}コース | {data['total']:>6} | {data['correct']:>6} | {data['accuracy']:>5.1f}% | {ratio:>5.1f}%{mark}")

    # 2. ベースライン比較（1コース常時予測 vs 現システム）
    print("\n" + "=" * 100)
    print("[2] ベースライン比較")
    print("=" * 100)

    # 1コースが実際に勝った割合（ベースライン）
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN res.pit_number = 1 THEN 1 ELSE 0 END) as course1_wins
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    total, course1_wins = cursor.fetchone()
    baseline_acc = (course1_wins / total * 100) if total > 0 else 0

    print(f"\nベースライン（常に1コースを予測した場合）: {baseline_acc:.1f}%")
    print(f"  1コースが実際に勝利: {course1_wins:,} / {total:,}")

    # 現システムの全体精度
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN rp.pit_number = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
    """, (f'{year}-01-01', f'{year}-12-31'))

    total, correct = cursor.fetchone()
    system_acc = (correct / total * 100) if total > 0 else 0

    print(f"\n現システム全体精度: {system_acc:.1f}%")
    print(f"  的中: {correct:,} / {total:,}")
    print(f"\n付加価値: {system_acc - baseline_acc:+.1f}pt")

    # 3. 1コース予測時 vs 非1コース予測時の精度
    print("\n" + "=" * 100)
    print("[3] 1コース予測 vs 非1コース予測")
    print("=" * 100)

    cursor.execute("""
        SELECT
            CASE WHEN rp.pit_number = 1 THEN '1コース予測' ELSE '非1コース予測' END as pred_type,
            COUNT(*) as total,
            SUM(CASE WHEN rp.pit_number = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        GROUP BY CASE WHEN rp.pit_number = 1 THEN '1コース予測' ELSE '非1コース予測' END
    """, (f'{year}-01-01', f'{year}-12-31'))

    for pred_type, total, correct in cursor.fetchall():
        acc = (correct / total * 100) if total > 0 else 0
        ratio = (total / cursor.execute("""
            SELECT COUNT(*) FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
        """, (f'{year}-01-01', f'{year}-12-31')).fetchone()[0] * 100)
        print(f"\n{pred_type}:")
        print(f"  予測数: {total:,} ({ratio:.1f}%)")
        print(f"  的中率: {acc:.1f}%")

    # 4. 信頼度D・Eを除外した場合のシミュレーション
    print("\n" + "=" * 100)
    print("[4] 信頼度D・E除外時のシミュレーション")
    print("=" * 100)

    # 信頼度A-Cのみでの精度
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN rp.pit_number = res.pit_number THEN 1 ELSE 0 END) as correct
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
        WHERE r.race_date >= ? AND r.race_date <= ?
        AND rp.prediction_type = 'advance'
        AND rp.rank_prediction = 1
        AND rp.confidence IN ('A', 'B', 'C')
    """, (f'{year}-01-01', f'{year}-12-31'))

    total_abc, correct_abc = cursor.fetchone()
    acc_abc = (correct_abc / total_abc * 100) if total_abc > 0 else 0

    print(f"\n信頼度A-Cのみ:")
    print(f"  対象レース数: {total_abc:,}")
    print(f"  的中率: {acc_abc:.1f}%")
    print(f"  付加価値: {acc_abc - baseline_acc:+.1f}pt")

    # 5. 非1コース予測の詳細分析（どのような条件で発生するか）
    print("\n" + "=" * 100)
    print("[5] 非1コース予測の発生条件分析")
    print("=" * 100)

    # スコア差による分析
    cursor.execute("""
        WITH predictions_ranked AS (
            SELECT
                rp.race_id,
                rp.pit_number,
                rp.total_score,
                rp.confidence,
                rp.rank_prediction,
                ROW_NUMBER() OVER (PARTITION BY rp.race_id ORDER BY rp.total_score DESC) as score_rank
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
        ),
        score_diffs AS (
            SELECT
                p1.race_id,
                p1.pit_number as predicted_course,
                p1.total_score as top_score,
                p2.total_score as course1_score,
                p1.total_score - p2.total_score as score_diff,
                p1.confidence
            FROM predictions_ranked p1
            LEFT JOIN predictions_ranked p2 ON p1.race_id = p2.race_id AND p2.pit_number = 1
            WHERE p1.score_rank = 1
        )
        SELECT
            CASE
                WHEN predicted_course = 1 THEN '1コース予測'
                ELSE '非1コース予測'
            END as pred_type,
            AVG(score_diff) as avg_score_diff,
            AVG(CASE WHEN predicted_course != 1 THEN score_diff ELSE NULL END) as avg_diff_when_not_1,
            COUNT(*) as count
        FROM score_diffs
        GROUP BY CASE WHEN predicted_course = 1 THEN '1コース予測' ELSE '非1コース予測' END
    """, (f'{year}-01-01', f'{year}-12-31'))

    print("\nスコア差分析:")
    for pred_type, avg_diff, avg_diff_not1, count in cursor.fetchall():
        print(f"  {pred_type}: {count:,}件")
        if avg_diff is not None:
            print(f"    平均スコア差（vs 1コース）: {avg_diff:.1f}pt")

    # 6. 改善提案のシミュレーション
    print("\n" + "=" * 100)
    print("[6] 改善シミュレーション")
    print("=" * 100)

    # オプション1: 非1コース予測を全て1コースに変更
    cursor.execute("""
        WITH current_preds AS (
            SELECT
                rp.race_id,
                rp.pit_number as predicted,
                res.pit_number as actual
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
        ),
        modified_preds AS (
            SELECT
                race_id,
                1 as predicted,  -- 常に1コースを予測
                actual
            FROM current_preds
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN predicted = actual THEN 1 ELSE 0 END) as correct
        FROM modified_preds
    """, (f'{year}-01-01', f'{year}-12-31'))

    total_mod, correct_mod = cursor.fetchone()
    acc_mod = (correct_mod / total_mod * 100) if total_mod > 0 else 0

    print(f"\nオプション1: 全て1コース予測に変更")
    print(f"  予測精度: {acc_mod:.1f}% (= ベースライン)")
    print(f"  現システム比: {acc_mod - system_acc:+.1f}pt")

    # オプション2: 信頼度D・Eの非1コース予測のみ1コースに変更
    cursor.execute("""
        WITH current_preds AS (
            SELECT
                rp.race_id,
                rp.pit_number as predicted,
                rp.confidence,
                res.pit_number as actual
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
        ),
        modified_preds AS (
            SELECT
                race_id,
                CASE
                    WHEN confidence IN ('D', 'E') AND predicted != 1 THEN 1
                    ELSE predicted
                END as new_predicted,
                actual
            FROM current_preds
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN new_predicted = actual THEN 1 ELSE 0 END) as correct
        FROM modified_preds
    """, (f'{year}-01-01', f'{year}-12-31'))

    total_mod2, correct_mod2 = cursor.fetchone()
    acc_mod2 = (correct_mod2 / total_mod2 * 100) if total_mod2 > 0 else 0

    print(f"\nオプション2: 信頼度D・Eの非1コース予測を1コースに変更")
    print(f"  予測精度: {acc_mod2:.1f}%")
    print(f"  現システム比: {acc_mod2 - system_acc:+.1f}pt")
    print(f"  ベースライン比: {acc_mod2 - baseline_acc:+.1f}pt")

    # オプション3: 全ての非1コース予測を1コースに変更
    cursor.execute("""
        WITH current_preds AS (
            SELECT
                rp.race_id,
                rp.pit_number as predicted,
                rp.confidence,
                res.pit_number as actual
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            LEFT JOIN results res ON rp.race_id = res.race_id AND res.rank = '1'
            WHERE r.race_date >= ? AND r.race_date <= ?
            AND rp.prediction_type = 'advance'
            AND rp.rank_prediction = 1
        ),
        modified_preds AS (
            SELECT
                race_id,
                1 as new_predicted,  -- 全て1コースに
                actual
            FROM current_preds
        )
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN new_predicted = actual THEN 1 ELSE 0 END) as correct
        FROM modified_preds
    """, (f'{year}-01-01', f'{year}-12-31'))

    total_mod3, correct_mod3 = cursor.fetchone()
    acc_mod3 = (correct_mod3 / total_mod3 * 100) if total_mod3 > 0 else 0

    print(f"\nオプション3: 全ての非1コース予測を1コースに変更（ベースライン化）")
    print(f"  予測精度: {acc_mod3:.1f}%")

    conn.close()

    print("\n" + "=" * 100)
    print("分析完了")
    print("=" * 100)


if __name__ == '__main__':
    db_path = os.path.join(PROJECT_ROOT, 'data/boatrace.db')
    analyze_prediction_course_distribution(db_path)
