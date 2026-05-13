"""
朝の予想生成モジュール

毎朝実行し、本日のレース予想を生成
UIの「今日の予想を生成」と同じ処理を実行
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.automation.notify import send_daily_summary, send_error_notification
from src.workflow.today_prediction import TodayPredictionWorkflow
from src.betting.evaluator_helpers import create_standard_evaluator


def get_todays_target_and_candidates(db_path: str) -> tuple:
    """
    本日の購入対象レースと候補レースを取得

    Args:
        db_path: データベースパス

    Returns:
        tuple: (確定購入対象レース数, 確定購入対象レースリスト, 暫定購入対象レースリスト, 候補レースリスト)
    """
    import sqlite3
    from src.betting.bet_target_evaluator import BetStatus

    today = datetime.now().strftime('%Y-%m-%d')

    # BetTargetEvaluatorを初期化（標準設定を使用）
    evaluator = create_standard_evaluator(db_path=db_path)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    target_races = []
    advance_races = []
    candidate_races = []

    try:
        cursor = conn.cursor()

        # 本日の全レースを取得
        cursor.execute("""
            SELECT r.id, r.venue_code, r.race_number, r.race_time
            FROM races r
            WHERE r.race_date = ?
            ORDER BY r.race_time
        """, (today,))

        for row in cursor.fetchall():
            race_id = row['id']
            venue_code = row['venue_code']
            race_number = row['race_number']
            race_time = row['race_time']

            # レースデータを取得
            race_data = _get_race_data_for_eval(cursor, race_id)
            if not race_data:
                continue

            # 予測データを取得（before優先、なければadvance）
            predictions, prediction_type = _get_predictions_for_eval(cursor, race_id)
            if not predictions:
                continue

            has_beforeinfo = prediction_type == 'before'

            # オッズデータを取得（全組み合わせ）
            odds_data = _get_odds_data_for_eval(cursor, race_id)

            # advance予測の1-2-3位を取得（advance/beforeフィルタ用・before時のみ意味あり）
            advance_top3 = _get_advance_top3(cursor, race_id) if has_beforeinfo else None

            # BetTargetEvaluatorで購入判定
            try:
                bet_target = evaluator.evaluate_race(
                    race_data=race_data,
                    predictions=predictions,
                    odds_data=odds_data,
                    has_beforeinfo=has_beforeinfo,
                    advance_top3=advance_top3
                )

                # 会場名マップ（venue_codeは"01", "02"などのテキスト型）
                venue_map = {
                    '01': '桐生', '02': '戸田', '03': '江戸川', '04': '平和島',
                    '05': '多摩川', '06': '浜名湖', '07': '蒲郡', '08': '常滑',
                    '09': '津', '10': '三国', '11': 'びわこ', '12': '住之江',
                    '13': '尼崎', '14': '鳴門', '15': '丸亀', '16': '児島',
                    '17': '宮島', '18': '徳山', '19': '下関', '20': '若松',
                    '21': '芦屋', '22': '福岡', '23': '唐津', '24': '大村'
                }
                # venue_codeを文字列に変換して2桁0埋め
                venue_code_str = str(venue_code).zfill(2) if isinstance(venue_code, int) else str(venue_code)
                venue_name = venue_map.get(venue_code_str, f'会場{venue_code}')

                # 買い目を整形（パターンH対応）
                if bet_target.multi_bet_result and bet_target.multi_bet_result.bets:
                    # パターンH（3点買い）- betsから各買い目を抽出
                    combinations = [bet.combination for bet in bet_target.multi_bet_result.bets]
                    combination_str = f"{len(combinations)}点買い: " + ', '.join(combinations)
                else:
                    # 1点買い
                    combination_str = bet_target.combination

                # 確定購入対象（before予測で確定済み）
                if bet_target.status == BetStatus.TARGET_CONFIRMED:
                    target_races.append({
                        'venue': venue_name,
                        'race_num': race_number,
                        'race_time': race_time,
                        'combination': combination_str,
                        'odds': bet_target.odds if (bet_target.odds is not None and bet_target.odds != 0) else 0.0,
                        'reason': bet_target.reason,
                    })
                # 暫定購入対象（advance予測のみ・before予測未確定）
                elif bet_target.status == BetStatus.TARGET_ADVANCE:
                    advance_races.append({
                        'venue': venue_name,
                        'race_num': race_number,
                        'race_time': race_time,
                        'combination': combination_str,
                        'odds': bet_target.odds if (bet_target.odds is not None and bet_target.odds != 0) else 0.0,
                        'reason': bet_target.reason,
                    })
                # 候補レース（オッズが条件の80%以上ある場合のみ）
                elif bet_target.status == BetStatus.CANDIDATE:
                    # オッズが条件に近い場合のみ候補とする
                    if bet_target.odds is None or bet_target.odds == 0:
                        # オッズ未取得（None or 0）の場合は候補に含める
                        candidate_races.append({
                            'venue': venue_name,
                            'race_num': race_number,
                            'race_time': race_time,
                            'combination': combination_str,
                            'reason': bet_target.reason
                        })
                    else:
                        # オッズが判明している場合、条件の80%以上なら候補とする
                        # 例: 条件が20-30倍なら、オッズ16倍以上を候補とする
                        odds_range_str = bet_target.odds_range
                        try:
                            # "20-30倍" から最小値を抽出
                            min_odds = float(odds_range_str.split('-')[0])
                            threshold = min_odds * 0.8

                            if bet_target.odds >= threshold:
                                candidate_races.append({
                                    'venue': venue_name,
                                    'race_num': race_number,
                                    'race_time': race_time,
                                    'combination': combination_str,
                                    'reason': bet_target.reason
                                })
                        except:
                            # パース失敗時は候補に含める
                            candidate_races.append({
                                'venue': venue_name,
                                'race_num': race_number,
                                'race_time': race_time,
                                'combination': combination_str,
                                'reason': bet_target.reason
                            })
            except Exception:
                continue

        return len(target_races), target_races, advance_races, candidate_races
    finally:
        conn.close()


def _get_race_data_for_eval(cursor, race_id: int):
    """評価用のレースデータを取得"""
    cursor.execute("""
        SELECT r.id, r.venue_code, r.race_number, r.race_date, r.race_time
        FROM races r WHERE r.id = ?
    """, (race_id,))
    race_row = cursor.fetchone()
    if not race_row:
        return None

    # 気象情報
    cursor.execute("SELECT wind_speed FROM race_conditions WHERE race_id = ?", (race_id,))
    conditions_row = cursor.fetchone()
    wind_speed = conditions_row['wind_speed'] if conditions_row and conditions_row['wind_speed'] else 0.0

    # エントリー情報
    cursor.execute("""
        SELECT pit_number, racer_number, racer_name, racer_rank, motor_second_rate, second_rate
        FROM entries WHERE race_id = ? ORDER BY pit_number
    """, (race_id,))
    entries = [dict(row) for row in cursor.fetchall()]

    return {
        'id': race_row['id'],
        'venue_code': race_row['venue_code'],
        'race_number': race_row['race_number'],
        'race_date': race_row['race_date'],
        'race_time': race_row['race_time'],
        'wind_speed': wind_speed,
        'entries': entries
    }


def _get_predictions_for_eval(cursor, race_id: int):
    """評価用の予測データを取得（before優先、なければadvance）

    Returns:
        tuple: (predictions_dict, prediction_type) or (None, None)
    """
    for prediction_type in ('before', 'advance'):
        cursor.execute("""
            SELECT pit_number, rank_prediction, confidence, total_score
            FROM race_predictions
            WHERE race_id = ? AND prediction_type = ?
            ORDER BY rank_prediction
        """, (race_id, prediction_type))
        rows = [dict(row) for row in cursor.fetchall()]
        if len(rows) >= 3:
            all_pred = [p['pit_number'] for p in rows]  # 全件（パターンH用に5位以上が必要）

            # 1着予測選手の登録番号を取得（逃げ率/バイアスフィルター用）
            first_racer_number = None
            if all_pred:
                cursor.execute(
                    "SELECT racer_number FROM entries WHERE race_id = ? AND pit_number = ?",
                    (race_id, all_pred[0])
                )
                row = cursor.fetchone()
                if row:
                    first_racer_number = row['racer_number']

            return {
                'confidence': rows[0]['confidence'],
                'total_score': rows[0].get('total_score'),  # スコアフィルター用（2026-04-21追加）
                'old_prediction': all_pred,
                'new_prediction': all_pred,
                'first_racer_number': first_racer_number,
            }, prediction_type
    return None, None


def _get_advance_top3(cursor, race_id: int):
    """advance予測の1-2-3位ピット番号を取得（advance/beforeフィルタ用）

    Returns:
        list[int] or None: [1位pit, 2位pit, 3位pit] or None（advance予測なし）
    """
    cursor.execute("""
        SELECT pit_number, rank_prediction
        FROM race_predictions
        WHERE race_id = ? AND prediction_type = 'advance' AND rank_prediction IN (1, 2, 3)
        ORDER BY rank_prediction
    """, (race_id,))
    rows = cursor.fetchall()
    if len(rows) < 3:
        return None
    rank_to_pit = {row['rank_prediction']: row['pit_number'] for row in rows}
    if 1 in rank_to_pit and 2 in rank_to_pit and 3 in rank_to_pit:
        return [rank_to_pit[1], rank_to_pit[2], rank_to_pit[3]]
    return None


def _get_odds_data_for_eval(cursor, race_id: int):
    """評価用のオッズデータを取得（全組み合わせ）"""
    cursor.execute(
        "SELECT combination, odds FROM trifecta_odds WHERE race_id = ?",
        (race_id,)
    )
    result = {row['combination']: row['odds'] for row in cursor.fetchall() if row['odds']}
    return result if result else None


def progress_callback(step: str, message: str, progress: int):
    """進捗表示用コールバック"""
    print(f"[{progress}%] {step}: {message}")


def generate_todays_predictions() -> bool:
    """
    本日のレース予想を生成（UIと同じワークフロー）

    Returns:
        bool: 成功ならTrue
    """
    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')

    print("=" * 60)
    print(f"本日の予想生成開始: {today_str}")
    print("=" * 60)

    # データベースパス
    db_path = project_root / "data" / "boatrace.db"

    if not db_path.exists():
        error_msg = f"データベースが見つかりません: {db_path}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("予想生成失敗", error_msg)
        return False

    # TodayPredictionWorkflowを使用（UIと同じ処理）
    try:
        workflow = TodayPredictionWorkflow(
            db_path=str(db_path),
            project_root=str(project_root),
            progress_callback=progress_callback
        )

        result = workflow.run()

        if result['success']:
            print("\n[OK] 予想生成完了")
            print(f"  取得レース: {result['races_fetched']}")
            print(f"  予測生成: {result['predictions_generated']}")
            print(f"  オッズ取得: {result['odds_fetched']}")

            # 購入対象レースと候補レースを取得
            target_count, target_races, advance_races, candidate_races = get_todays_target_and_candidates(str(db_path))

            print(f"  確定購入対象レース数: {target_count}件")
            print(f"  暫定購入対象レース数: {len(advance_races)}件")
            print(f"  候補レース数: {len(candidate_races)}件")

            # 本日最初のレース締切時刻を取得（通知時刻の見通し用）
            all_races = (target_races or []) + (advance_races or []) + (candidate_races or [])
            first_race_time = None
            if all_races:
                times = [r.get('race_time', '') for r in all_races if r.get('race_time')]
                if times:
                    first_race_time = min(times)

            # 完了通知送信
            send_daily_summary(
                date=today_str,
                race_count=result['races_fetched'],
                target_count=target_count,
                target_races=target_races,
                advance_races=advance_races,
                candidate_races=candidate_races,
                first_race_time=first_race_time,
            )

            return True
        else:
            error_msg = f"予想生成失敗: {', '.join(result['errors'])}"
            print(f"[ERROR] {error_msg}")
            send_error_notification("予想生成失敗", error_msg)
            return False

    except Exception as e:
        error_msg = f"予想生成中にエラーが発生: {str(e)}"
        print(f"[ERROR] {error_msg}")
        send_error_notification("予想生成エラー", error_msg)
        return False


def main():
    """メイン処理"""
    print("\n" + "=" * 60)
    print("朝の予想生成")
    print(f"実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    success = generate_todays_predictions()

    print("\n" + "=" * 60)
    if success:
        print("[OK] 予想生成完了")
    else:
        print("[ERROR] 予想生成失敗")
    print("=" * 60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
