"""
Discord Webhook通知モジュール

4チャンネル対応:
  #購入 (buy)   — 購入確定/暫定/Gap1  ※即行動が必要
  #監視 (watch) — 候補最終・オッズ変動・重大エラー  ※気になったら確認
  #結果 (result)— 前日突合せ結果  ※毎朝振り返り
  #ログ (log)   — 朝サマリー・Aブロック完了・その他  ※参考記録
"""

import os
import sys
import time
import requests
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

# --- Webhook URL ロード（フォールバックチェーン）---
# BASE       … 最終フォールバック
# ALERT/LOG  … 旧2チャンネル設定（移行期の互換）
# BUY/WATCH/RESULT … 4チャンネル専用（未設定時はALERT/LOGに委譲）
_WEBHOOK_BASE  = os.getenv("DISCORD_WEBHOOK_URL")
_WEBHOOK_ALERT = os.getenv("DISCORD_WEBHOOK_URL_ALERT") or _WEBHOOK_BASE
_WEBHOOK_LOG   = os.getenv("DISCORD_WEBHOOK_URL_LOG")   or _WEBHOOK_BASE

_WEBHOOK_BUY    = os.getenv("DISCORD_WEBHOOK_URL_BUY")    or _WEBHOOK_ALERT
_WEBHOOK_WATCH  = os.getenv("DISCORD_WEBHOOK_URL_WATCH")  or _WEBHOOK_ALERT
_WEBHOOK_RESULT = os.getenv("DISCORD_WEBHOOK_URL_RESULT") or _WEBHOOK_LOG

# 全URL未設定時の起動時警告（指摘4対応）
if not _WEBHOOK_BASE:
    print("[WARN] notify.py: DISCORD_WEBHOOK_URL が未設定です。全通知が無効になります。")


def _get_webhook_url(channel: str):
    """チャンネル名 → Webhook URL"""
    if channel == 'buy':
        return _WEBHOOK_BUY
    elif channel == 'watch':
        return _WEBHOOK_WATCH
    elif channel == 'result':
        return _WEBHOOK_RESULT
    return _WEBHOOK_LOG  # 'log' および未知チャンネルはログへ


def send_discord_notification(message: str, channel: str = 'log') -> bool:
    """
    Discord Webhookでメッセージを送信（429リトライ付き）

    Args:
        message: 送信するメッセージ
        channel: 'buy' / 'watch' / 'result' / 'log'（デフォルト: 'log'）

    Returns:
        bool: 送信成功ならTrue
    """
    url = _get_webhook_url(channel)
    if not url:
        print(f"ERROR: #{channel} のWebhook URLが設定されていません")
        print("ガイド: docs/guides/DISCORD_WEBHOOK_SETUP.md を参照してください")
        return False

    if len(message) > 2000:
        message = message[:1997] + "..."

    data = {"content": message}

    for attempt in range(3):
        try:
            response = requests.post(url, json=data, timeout=30)

            if response.status_code == 204:
                print(f"[OK] Discord送信({channel}): {datetime.now().strftime('%H:%M:%S')}")
                return True
            elif response.status_code == 429:
                # Retry-After ヘッダ優先、JSONフォールバック、最大30秒でキャップ（指摘6対応）
                try:
                    retry_after = float(response.headers.get('Retry-After', 0)) or \
                                  response.json().get('retry_after', 1.0)
                except Exception:
                    retry_after = 1.0
                retry_after = min(retry_after, 30.0)
                print(f"[WARN] Discord 429({channel}), {retry_after:.1f}s後にリトライ ({attempt+1}/3)")
                time.sleep(retry_after + 0.1)
                continue
            else:
                print(f"[ERROR] Discord送信失敗({channel}): {response.status_code} {response.text}")
                return False

        except Exception as e:
            print(f"[ERROR] Discord送信エラー({channel}): {e}")
            if attempt < 2:
                time.sleep(1)
            else:
                return False

    return False


def send_discord_notification_dual(
    primary_msg: str,
    secondary_msg: str,
    *,
    primary_channel: str,
    secondary_channel: str = 'log',
) -> bool:
    """
    2チャンネルに送信（secondary → primary の順）

    詳細ログを先に投稿することで primary のリンクからたどりやすくなる。
    secondary 失敗時もエラーをログ出力して続行する（指摘5対応）。
    primary_channel は必須引数（暗黙デフォルト依存を防止）（指摘3対応）。

    Returns:
        bool: primary 送信成功ならTrue
    """
    ok_secondary = send_discord_notification(secondary_msg, channel=secondary_channel)
    if not ok_secondary:
        print(f"[WARN] secondary送信失敗({secondary_channel}): {secondary_msg[:50]}")
    return send_discord_notification(primary_msg, channel=primary_channel)


# ---------------------------------------------------------------------------
# キャリブレーションテーブル（6年実測値）
# ---------------------------------------------------------------------------

def calculate_bet_amount(confidence: float, odds: float, base_amount: int = 1000) -> int:
    if confidence < 0.3:
        return base_amount
    expected_value = confidence * odds - 1.0
    if expected_value <= 0:
        return base_amount
    kelly_fraction = expected_value / (odds - 1)
    multiplier = min(1 + kelly_fraction * 2, 3.0)
    return int(base_amount * multiplier)


# ---------------------------------------------------------------------------
# 予測スコア計算（0-100）
# スコアの意味: このレースの予測シグナルの強さ（上位3艇の分離度・rank1の支配力）
# ---------------------------------------------------------------------------
_SCORE_BASE = {'A': 60, 'B': 55, 'C': 47, 'D': 36}  # E は購入条件外のため到達しない

# rank3-rank4スコア差ボーナス（上位3艇が4位以下と離れているほど三連単が安定）
# 実証: A信頼度で gap34<2→8.77% / gap34>=15→15.66%（6年データ）
# 負の gap34（rank4>rank3）も最小値 -4 で捕捉する
_GAP34_BONUS = {0: -4, 2: -1, 5: 2, 10: 10, 15: 18}   # キーは下限

# rank1-rank2スコア差ボーナス（rank1の支配力）
# 実証上 D条件のみで有意差（gap12<5: 2.56% / >=20: 4.83%）→ D限定適用
_GAP12_BONUS = {0: -5, 5: 0, 15: 4, 20: 10}            # キーは下限


def _lookup_bonus(table: dict, value: float) -> int:
    """キー=下限のテーブルから value に対応するボーナスを返す。
    value が最小キーを下回る場合も最小キーの値を返す（負値フォールバック）。"""
    sorted_keys = sorted(table)
    bonus = table[sorted_keys[0]]  # 最小キー値で初期化（負値対応）
    for threshold in sorted_keys:
        if value >= threshold:
            bonus = table[threshold]
    return bonus


def calc_prediction_score(confidence: str, gap12: float | None, gap34: float | None) -> int:
    """
    予測スコア（0-100）を算出する。
    confidence: A/B/C/D グレード
    gap12: rank1-rank2スコア差（None の場合はボーナス0扱い）
    gap34: rank3-rank4スコア差（None の場合はボーナス0扱い）
    """
    base = _SCORE_BASE.get(confidence, 40)
    b34 = _lookup_bonus(_GAP34_BONUS, gap34) if gap34 is not None else 0
    # gap12 は D 条件のみ有意差が実証済みのため D 限定
    b12 = _lookup_bonus(_GAP12_BONUS, gap12) if (gap12 is not None and confidence == 'D') else 0
    return min(100, max(0, base + b34 + b12))


# ---------------------------------------------------------------------------
# フォーマット関数
# ---------------------------------------------------------------------------

def format_race_notification(
    race_info: dict,
    prediction: dict,
    odds_info: dict,
    direct_info: dict = None,
    status: str = None
) -> str:
    """レース通知メッセージ（#ログ用・詳細版）"""
    venue = race_info['venue']
    race_num = race_info['race_number']
    deadline = race_info['deadline']

    pit_numbers = prediction['pit_numbers']
    if not isinstance(pit_numbers[0], list):
        pit_numbers = [pit_numbers]

    combinations = ['-'.join(map(str, combo)) for combo in pit_numbers]

    rank1_name = prediction.get('rank1_name')
    name_str = f"  rank１位  {rank1_name}" if rank1_name else ""
    prediction_score = prediction.get('prediction_score')
    score_str = f"  予測スコア {prediction_score}" if prediction_score is not None else ""

    if status == 'TARGET_CONFIRMED':
        header_emoji, label = "🎯", "【購入確定】"
    elif status == 'TARGET_ADVANCE':
        header_emoji, label = "🟡", "【購入対象(advance暫定)】"
    else:
        header_emoji, label = "🎯", "【購入対象】"

    odds = odds_info['trifecta_odds']
    multi_bets = odds_info.get('multi_bets')
    expected_roi = odds_info.get('expected_roi')
    total_bet = odds_info.get('bet_amount')
    reason = odds_info.get('reason', '')
    fetch_elapsed = odds_info.get('odds_fetch_elapsed')
    elapsed_str = f" ※{fetch_elapsed}分前取得" if fetch_elapsed else ""

    roi_str = f"  ROI {expected_roi:.0f}%" if (expected_roi is not None and expected_roi > 0) else ""

    if multi_bets and len(multi_bets) > 1:
        calc_total = sum(b.get('bet_amount', 100) for b in multi_bets)
        bet_total = total_bet if (total_bet is not None and total_bet > 0) else calc_total
        lines = [f"{header_emoji} **{label}{venue} {race_num}R** {deadline}  {len(multi_bets)}点/{bet_total}円{score_str}{roi_str}"]
        for bet in multi_bets:
            amount = bet.get('bet_amount', 100)
            lines.append(f"`{bet['combination']}`  {bet['odds']:.1f}倍 ({amount}円)")
        if name_str:
            lines.append(name_str.strip())
        if elapsed_str:
            lines.append(f"_{elapsed_str.strip()}_")
        if reason:
            lines.append(f"_{reason}_")
        return "\n".join(lines)
    else:
        bet_str = f"  {total_bet}円" if (total_bet is not None and total_bet > 0) else ""
        reason_str = f"\n_{reason}_" if reason else ""
        elapsed_note = f"\n_{elapsed_str.strip()}_" if elapsed_str else ""
        return f"{header_emoji} **{label}{venue} {race_num}R** {deadline}\n`{combinations[0]}`  {odds:.1f}倍{score_str}{roi_str}{bet_str}{name_str}{reason_str}{elapsed_note}"


def format_race_notification_short(
    race_info: dict,
    prediction: dict,
    odds_info: dict,
    status: str = None,
    gap1: bool = False,
) -> str:
    """レース通知メッセージ（#購入用・短縮版）スマホ最適化: 2行構成、内部指標除外"""
    venue = race_info['venue']
    race_num = race_info['race_number']
    deadline = race_info['deadline']

    if gap1:
        header_emoji, suffix = "🆕", "(再通知)"
    elif status == 'TARGET_ADVANCE':
        header_emoji, suffix = "🟡", "(暫定)"
    else:
        header_emoji, suffix = "🎯", ""

    multi_bets = odds_info.get('multi_bets')
    total_bet = odds_info.get('bet_amount', 0)

    rank1_name = prediction.get('rank1_name')
    name_str = f"  rank１位  {rank1_name}" if rank1_name else ""
    reason = odds_info.get('reason', '')
    # "|"以降（会場調整等の補足）は短縮版では不要なので除去してから60文字制限
    reason_short = reason.split('|')[0].strip() if reason else ''
    reason_line = f"\n_{reason_short[:60]}{'…' if len(reason_short) > 60 else ''}_" if reason_short else ""

    if multi_bets and len(multi_bets) > 1:
        combos_str = ' '.join(f"`{b['combination']}`" for b in multi_bets)
        bet_str = f"  計**{total_bet}円**" if total_bet else ""
        return (
            f"{header_emoji} **{venue} {race_num}R{suffix}** 締切{deadline}\n"
            f"{combos_str}{bet_str}{name_str}{reason_line}"
        )

    pit_numbers = prediction.get('pit_numbers', [])
    if not pit_numbers:
        return f"{header_emoji} **{venue} {race_num}R{suffix}** 締切{deadline}\n[買い目未確定]{name_str}{reason_line}"
    if isinstance(pit_numbers[0], list):
        combo = '-'.join(map(str, pit_numbers[0])) if pit_numbers[0] else '?'
    else:
        combo = '-'.join(map(str, pit_numbers)) if pit_numbers else '?'
    odds = odds_info.get('trifecta_odds', 0.0)
    bet_str = f"  **{total_bet}円**" if total_bet else ""
    return (
        f"{header_emoji} **{venue} {race_num}R{suffix}** 締切{deadline}\n"
        f"`{combo}`  {odds:.1f}倍{bet_str}{name_str}{reason_line}"
    )


# ---------------------------------------------------------------------------
# 送信関数
# ---------------------------------------------------------------------------

def send_race_notification(
    race_info: dict,
    prediction: dict,
    odds_info: dict,
    direct_info: dict = None,
    status: str = None
) -> bool:
    """購入通知: #購入(短縮) + #ログ(詳細)"""
    log_msg = format_race_notification(race_info, prediction, odds_info, direct_info, status)
    buy_msg = format_race_notification_short(race_info, prediction, odds_info, status)
    return send_discord_notification_dual(buy_msg, log_msg,
                                          primary_channel='buy', secondary_channel='log')


def send_daily_summary(
    date: str,
    race_count: int,
    target_count: int,
    target_races: list = None,
    advance_races: list = None,
    candidate_races: list = None,
    *,
    first_race_time: str = None,
) -> bool:
    """朝サマリー: #事前予想・結果チャンネルへ送信"""
    from datetime import datetime as _dt, timedelta as _td

    adv_count  = len(advance_races)  if advance_races  else 0
    cand_count = len(candidate_races) if candidate_races else 0

    try:
        short_date = _dt.strptime(date, '%Y-%m-%d').strftime('%m/%d')
    except Exception:
        short_date = date

    if target_count == 0 and adv_count == 0 and cand_count == 0:
        return send_discord_notification(f"📋 **{short_date}** 購入対象なし", channel='result')

    message = f"📋 **{short_date} 予想完了**  確定 {target_count}件 / 暫定 {adv_count}件 / 候補 {cand_count}件"

    est_min = target_count + round(adv_count * 0.5)
    est_max = target_count + adv_count + round(cand_count * 0.3)
    if est_max > 0:
        if est_min == est_max:
            message += f"\n🔮 本日購入見込み: {est_min}件 (確定+暫定{adv_count}件の昇格待ち)"
        else:
            message += f"\n🔮 本日購入見込み: {est_min}〜{est_max}件 (朝は確定0が正常・展示後に判定)"

    if target_races:
        message += "\n"
        for race in target_races:
            odds = race.get('odds', 0.0)
            odds_str = f"  {odds:.1f}倍" if odds else ""
            reason = race.get('reason', '')
            reason_str = f"  _{reason}_" if reason else ""
            message += f"\n🎯 {race.get('venue')} {race.get('race_num')}R  {race.get('race_time')}  `{race.get('combination')}`{odds_str}{reason_str}"

    if advance_races:
        message += "\n"
        for race in advance_races:
            odds = race.get('odds', 0.0)
            odds_str = f"  {odds:.1f}倍" if odds else ""
            reason = race.get('reason', '')
            reason_str = f"  _{reason}_" if reason else ""
            message += f"\n🟡 {race.get('venue')} {race.get('race_num')}R  {race.get('race_time')}  `{race.get('combination')}`{odds_str}  (before後確定){reason_str}"

    if candidate_races:
        grouped: dict = {}
        for r in candidate_races:
            grouped.setdefault(r.get('venue', '?'), []).append(r)
        message += "\n💤 候補:"
        for venue, rs in list(grouped.items())[:5]:
            races_str = ' '.join(f"{r.get('race_num')}R({r.get('race_time', '')})" for r in rs)
            message += f"  {venue} {races_str}"
        remaining_venues = len(grouped) - 5
        remaining_races = sum(len(rs) for rs in list(grouped.values())[5:])
        if remaining_venues > 0:
            message += f"  他{remaining_venues}会場{remaining_races}件"

    if first_race_time:
        from datetime import datetime as _dt2, timedelta as _td2
        try:
            deadline_dt = _dt2.strptime(first_race_time, '%H:%M')
            eval_time = (deadline_dt - _td2(minutes=20)).strftime('%H:%M')
            buy_time  = (deadline_dt - _td2(minutes=10)).strftime('%H:%M')
            message += f"\n⏰ 最初の購入通知: {buy_time}頃 (直前情報判定: {eval_time}頃)"
        except Exception:
            pass

    return send_discord_notification(message, channel='result')


def send_error_notification(error_type: str, error_message: str, *, severity: str = 'warning') -> bool:
    """
    エラー通知を送信
      severity='critical' → #監視(短縮+エラー1行目) + #ログ(詳細)
      severity='warning'  → #ログのみ
    """
    log_msg = f"⚠️ **エラー: {error_type}** {datetime.now().strftime('%m/%d %H:%M')}\n```\n{error_message[:200]}\n```"

    if severity == 'critical':
        first_line = (error_message or '').strip().splitlines()[0] if error_message else ''
        if len(first_line) > 80:
            first_line = first_line[:77] + '...'
        summary = f"\n{first_line}" if first_line else ""
        watch_msg = f"⚠️ **{error_type}** {datetime.now().strftime('%m/%d %H:%M')}{summary}"
        return send_discord_notification_dual(watch_msg, log_msg,
                                              primary_channel='watch', secondary_channel='log')
    else:
        return send_discord_notification(log_msg, channel='log')


def send_reconcile_notification(result: dict) -> bool:
    """
    突合せ結果を送信
      購入あり・なし問わず #事前予想・結果チャンネルに全詳細を表示
    """
    from scripts.automation.reconcile_yesterday_bets import format_reconcile_message

    full_msg = format_reconcile_message(result)
    return send_discord_notification(full_msg, channel='result')


def send_odds_change_alert(
    venue_name: str,
    race_number: int,
    combination: str,
    old_odds: float,
    new_odds: float,
    time_until: float,
) -> bool:
    """オッズ変動アラート: #監視(短縮) + #ログ(詳細)"""
    # old_odds=0 のときは方向・変動率を表示しない（指摘10対応）
    if not (old_odds and old_odds > 0):
        watch_msg = (
            f"⚡ **オッズ判明** {venue_name} {race_number}R  "
            f"`{combination}`  → **{new_odds:.1f}倍**  (締切{round(time_until)}分前)"
        )
        log_msg = watch_msg
    else:
        direction  = "↗" if new_odds > old_odds else "↘"
        change_pct = abs(new_odds - old_odds) / old_odds * 100
        watch_msg = (
            f"⚡ **オッズ変動** {venue_name} {race_number}R  "
            f"`{combination}`  "
            f"{old_odds:.1f}倍{direction}**{new_odds:.1f}倍**  "
            f"({change_pct:.0f}% 締切{round(time_until)}分前)"
        )
        log_msg = (
            f"⚡ **オッズ変動** {venue_name} {race_number}R  "
            f"`{combination}`  "
            f"{old_odds:.1f}倍 {direction} **{new_odds:.1f}倍**  "
            f"変動率: {change_pct:.0f}%（締切{round(time_until)}分前）"
        )

    return send_discord_notification_dual(watch_msg, log_msg,
                                          primary_channel='watch', secondary_channel='log')


if __name__ == "__main__":
    print("Discord Webhook通知テスト（4チャンネル）")
    print("-" * 50)
    for ch in ('buy', 'watch', 'result', 'log'):
        ok = send_discord_notification(f"**テスト** #{ch} チャンネルの確認（ボートレース予想システム）", channel=ch)
        print(f"  {ch}: {'OK' if ok else 'FAIL'}")
