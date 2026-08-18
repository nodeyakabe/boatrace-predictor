#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
異常チェックスクリプト（経過観察用）

「異常チェックして」と言われたときに実行し、Claude が結果を整形・報告する。

チェック項目:
  1. 自動化パイプライン稼働確認（schedulerログのギャップ）
  2. データ収集欠損チェック（before予測・race_details・trifecta_odds）
  3. A率（信頼度分布）の正常範囲確認
  4. 直近の購入件数・的中率・ROI推移（bet_notifications ベース）

出力: JSON（Claude が解釈して口頭報告する）
"""
import sys, os, json, glob, re
from datetime import datetime, timedelta
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import sqlite3
from config.settings import DATABASE_PATH

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')

# ======================================================================
# 正常範囲の定義（MEMORY.md / CLAUDE.md ベースライン）
# ======================================================================
NORMAL = {
    'a_rate_advance_min': 2.0,   # advance A率 正常下限（%）2026-03以降の正規化済み値
    'a_rate_advance_max': 6.0,   # advance A率 正常上限（%）実績3.86-5.27% + マージン
    'a_rate_before_min': 15.0,   # before  A率 正常下限（%）実績最低20%台に安全マージン
    'a_rate_before_max': 27.0,   # before  A率 正常上限（%）実績上限25.84%（2019）にマージン
    'before_coverage_warn': 90.0,  # before予測カバー率 警告閾値（%）
    'scheduler_gap_warn_days': 2,  # schedulerログ空白 警告閾値（日）
    'bets_per_day_min': 2,         # 1日あたり通知件数 最小（>=1開催日）
    'bets_per_day_max': 15,        # 1日あたり通知件数 最大（多すぎ警告）
}


def check_scheduler_pipeline():
    """1. schedulerログの稼働確認"""
    result = {'status': 'OK', 'details': [], 'warnings': []}

    # scheduler_YYYYMMDD.log を取得（_err.log は除外）
    pattern = os.path.join(LOGS_DIR, 'scheduler_2026*.log')
    files = [f for f in glob.glob(pattern) if not f.endswith('_err.log')]
    if not files:
        result['status'] = 'WARN'
        result['warnings'].append('scheduler ログファイルが見つかりません')
        return result

    # ファイル名ではなく mtime（実際の最終書き込み時刻）で判定する。
    # ファイル名日付はスケジューラの「起動日」であり、長期稼働時は現在日と乖離するため
    # 誤検知を生む（例: 8/15起動→8/18でも"3日前"と判定されWARNになる）。
    latest_file = max(files, key=os.path.getmtime)
    latest_mtime = datetime.fromtimestamp(os.path.getmtime(latest_file))
    now = datetime.now()
    hours_since_write = (now - latest_mtime).total_seconds() / 3600
    days_since_write = hours_since_write / 24

    result['last_log_date'] = latest_mtime.strftime('%Y-%m-%d')
    result['days_since_last_log'] = round(days_since_write, 2)
    result['total_log_days'] = len(files)

    warn_days = NORMAL['scheduler_gap_warn_days']
    if days_since_write > warn_days:
        result['status'] = 'WARN'
        result['warnings'].append(
            f'最終schedulerログが {round(hours_since_write, 1)}時間前 '
            f'({latest_mtime.strftime("%Y-%m-%d %H:%M")})。パイプライン停止の可能性あり。'
        )
    else:
        result['details'].append(
            f'最終schedulerログ書き込み: {latest_mtime.strftime("%Y-%m-%d %H:%M")} '
            f'({round(hours_since_write, 1)}時間前) [OK]'
        )

    return result


def check_data_coverage():
    """2. データ収集の欠損チェック（直近7日）"""
    result = {'status': 'OK', 'details': [], 'warnings': []}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    try:
        today = datetime.now().date()
        start = str(today - timedelta(days=7))
        end = str(today)

        # before予測カバー率（直近7日）
        cur.execute('''
            SELECT
                r.race_date,
                COUNT(DISTINCT r.id) as total_races,
                COUNT(DISTINCT rp.race_id) as has_before
            FROM races r
            LEFT JOIN (
                SELECT DISTINCT race_id
                FROM race_predictions
                WHERE prediction_type = 'before' AND rank_prediction = 1
            ) rp ON r.id = rp.race_id
            WHERE r.race_date >= ? AND r.race_date < ?
            GROUP BY r.race_date ORDER BY r.race_date DESC
        ''', (start, end))
        rows = cur.fetchall()

        coverage_data = []
        for date, total, has_before in rows:
            coverage = 100.0 * has_before / total if total > 0 else 0.0
            coverage_data.append({
                'date': date,
                'total_races': total,
                'has_before': has_before,
                'coverage_pct': round(coverage, 1)
            })
            if coverage < NORMAL['before_coverage_warn']:
                result['status'] = 'WARN'
                result['warnings'].append(
                    f'{date}: before予測カバー率 {coverage:.1f}% ({has_before}/{total}件)'
                )

        result['before_coverage'] = coverage_data

        # race_details 欠損チェック（直近7日）
        cur.execute('''
            SELECT COUNT(DISTINCT r.id) as races_with_rd
            FROM races r
            JOIN race_details rd ON r.id = rd.race_id
            WHERE r.race_date >= ? AND r.race_date < ?
        ''', (start, end))
        races_with_rd = cur.fetchone()[0]

        cur.execute('''
            SELECT COUNT(DISTINCT id) FROM races
            WHERE race_date >= ? AND race_date < ?
        ''', (start, end))
        total_races = cur.fetchone()[0]

        rd_coverage = 100.0 * races_with_rd / total_races if total_races > 0 else 0.0
        result['race_details_coverage'] = round(rd_coverage, 1)
        if rd_coverage < 80.0:
            result['status'] = 'WARN'
            result['warnings'].append(f'race_details カバー率 {rd_coverage:.1f}%')
        else:
            result['details'].append(f'race_details カバー率: {rd_coverage:.1f}% [OK]')

        # trifecta_odds 欠損チェック（直近7日）
        cur.execute('''
            SELECT COUNT(DISTINCT r.id) as races_with_odds
            FROM races r
            JOIN trifecta_odds t ON r.id = t.race_id
            WHERE r.race_date >= ? AND r.race_date < ?
        ''', (start, end))
        races_with_odds = cur.fetchone()[0]

        odds_coverage = 100.0 * races_with_odds / total_races if total_races > 0 else 0.0
        result['trifecta_odds_coverage'] = round(odds_coverage, 1)
        if odds_coverage < 80.0:
            result['status'] = 'WARN'
            result['warnings'].append(f'trifecta_odds カバー率 {odds_coverage:.1f}%')
        else:
            result['details'].append(f'trifecta_odds カバー率: {odds_coverage:.1f}% [OK]')

    finally:
        conn.close()

    return result


def check_a_rate():
    """3. A率（信頼度分布）の正常範囲確認"""
    result = {'status': 'OK', 'details': [], 'warnings': [], 'rates': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    try:
        today = datetime.now().date()
        # 直近30日で確認
        start = str(today - timedelta(days=30))

        for ptype in ['advance', 'before']:
            cur.execute('''
                SELECT
                    confidence,
                    COUNT(*) as cnt
                FROM race_predictions rp
                JOIN races r ON rp.race_id = r.id
                WHERE rp.prediction_type = ?
                  AND rp.rank_prediction = 1
                  AND r.race_date >= ?
                GROUP BY confidence
            ''', (ptype, start))
            rows = cur.fetchall()

            counts = {row[0]: row[1] for row in rows}
            total = sum(counts.values())
            if total == 0:
                result['warnings'].append(f'{ptype}: 直近30日に予測データなし')
                continue

            a_count = counts.get('A', 0)
            a_rate = 100.0 * a_count / total

            result['rates'][ptype] = {
                'A': a_count, 'B': counts.get('B', 0),
                'C': counts.get('C', 0), 'total': total,
                'a_rate_pct': round(a_rate, 2)
            }

            min_r = NORMAL[f'a_rate_{ptype}_min']
            max_r = NORMAL[f'a_rate_{ptype}_max']

            if a_rate < min_r or a_rate > max_r:
                result['status'] = 'WARN'
                result['warnings'].append(
                    f'{ptype} A率: {a_rate:.2f}% → 正常範囲外 [{min_r}-{max_r}%]'
                    + (' ※旧コード混入の可能性' if a_rate > max_r else '')
                )
            else:
                result['details'].append(
                    f'{ptype} A率: {a_rate:.2f}% (正常範囲: {min_r}-{max_r}%) [OK]'
                )

    finally:
        conn.close()

    return result


def check_recent_performance():
    """4. 直近の購入件数・的中率・ROI推移（bet_notifications ベース）"""
    result = {'status': 'OK', 'details': [], 'warnings': [], 'stats': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    try:
        today = datetime.now().date()

        # bet_notifications の最古日確認
        cur.execute("SELECT MIN(notified_at), MAX(notified_at), COUNT(*) FROM bet_notifications")
        min_date, max_date, total_notifs = cur.fetchone()
        result['stats']['notification_range'] = {'min': min_date, 'max': max_date, 'total': total_notifs}

        # 直近30日の通知件数（日別）と的中率
        cur.execute('''
            SELECT
                DATE(bn.notified_at) as d,
                COUNT(*) as notif_cnt,
                SUM(CASE
                    WHEN bn.combinations IS NOT NULL
                    AND bn.combinations =
                        (SELECT CAST(r1.pit_number AS TEXT)||'-'||CAST(r2.pit_number AS TEXT)||'-'||CAST(r3.pit_number AS TEXT)
                         FROM results r1, results r2, results r3
                         WHERE r1.race_id=bn.race_id AND r1.rank='1'
                           AND r2.race_id=bn.race_id AND r2.rank='2'
                           AND r3.race_id=bn.race_id AND r3.rank='3')
                    THEN 1 ELSE 0 END) as hits
            FROM bet_notifications bn
            WHERE DATE(bn.notified_at) >= DATE('now', '-30 days')
            GROUP BY DATE(bn.notified_at)
            ORDER BY d DESC
        ''')
        daily = cur.fetchall()
        result['stats']['daily_last30'] = [
            {'date': row[0], 'bets': row[1], 'hits': row[2] or 0}
            for row in daily
        ]

        # 直近30日合計
        total_bets = sum(r['bets'] for r in result['stats']['daily_last30'])
        total_hits = sum(r['hits'] for r in result['stats']['daily_last30'])
        days_with_bets = len(result['stats']['daily_last30'])

        result['stats']['last30_summary'] = {
            'bets': total_bets,
            'hits': total_hits,
            'hit_rate_pct': round(100.0 * total_hits / total_bets, 2) if total_bets > 0 else 0,
            'days_active': days_with_bets,
        }

        # 月別集計（直近3ヶ月）
        cur.execute('''
            SELECT
                strftime('%Y-%m', bn.notified_at) as ym,
                COUNT(*) as bets,
                SUM(CASE
                    WHEN bn.combinations =
                        (SELECT CAST(r1.pit_number AS TEXT)||'-'||CAST(r2.pit_number AS TEXT)||'-'||CAST(r3.pit_number AS TEXT)
                         FROM results r1, results r2, results r3
                         WHERE r1.race_id=bn.race_id AND r1.rank='1'
                           AND r2.race_id=bn.race_id AND r2.rank='2'
                           AND r3.race_id=bn.race_id AND r3.rank='3')
                    THEN 1 ELSE 0 END) as hits
            FROM bet_notifications bn
            GROUP BY strftime('%Y-%m', bn.notified_at)
            ORDER BY ym DESC
            LIMIT 4
        ''')
        monthly = cur.fetchall()
        result['stats']['monthly'] = [
            {'month': r[0], 'bets': r[1], 'hits': r[2] or 0,
             'hit_rate_pct': round(100.0 * (r[2] or 0) / r[1], 2) if r[1] > 0 else 0}
            for r in monthly
        ]

        if total_bets == 0:
            result['warnings'].append('直近30日に bet_notifications が0件（自動化停止の可能性）')
        else:
            avg_per_day = total_bets / max(days_with_bets, 1)
            result['details'].append(
                f'直近30日: {total_bets}件通知 / {total_hits}的中 '
                f'({result["stats"]["last30_summary"]["hit_rate_pct"]}%) '
                f'/ 平均{avg_per_day:.1f}件/稼働日'
            )

    finally:
        conn.close()

    return result


def check_bet_prediction_quality(days: int = 30) -> dict:
    """5. 購入確定レースの予測品質チェック（展示タイム反映・before/advanceタイプ）

    monitor_race_timing の force=True 修正（2026-06-26）が機能しているかの事後検証。
    had_exhibition=0 または pred_type_used='advance' が1件でもあれば異常。

    正常範囲:
      had_exhibition=0    : 0件（展示なし購入は常に異常）
      advance_fallback    : 0件（before未生成のまま購入は異常）
      had_exhibition=NULL : 修正前(2026-06-26以前)の旧レコード。時間経過とともに0に収束が正常。
    """
    result = {'status': 'OK', 'details': [], 'warnings': [], 'metrics': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            result['details'].append('bet_notifications未作成（運用前）')
            return result

        cur.execute("PRAGMA table_info(bet_notifications)")
        cols = {row[1] for row in cur.fetchall()}
        if 'had_exhibition' not in cols:
            result['details'].append('予測品質列未追加（要DBマイグレーション）')
            return result

        today = datetime.now().date()
        cutoff = str(today - timedelta(days=days))

        # ── 直近N日の集計 ──────────────────────────────────
        cur.execute("""
            SELECT
                COUNT(*)                                                     AS total,
                SUM(CASE WHEN had_exhibition = 1 THEN 1 ELSE 0 END)         AS with_exhib,
                SUM(CASE WHEN had_exhibition = 0 THEN 1 ELSE 0 END)         AS no_exhib,
                SUM(CASE WHEN had_exhibition IS NULL THEN 1 ELSE 0 END)     AS unknown_exhib,
                SUM(CASE WHEN pred_type_used = 'advance' THEN 1 ELSE 0 END) AS advance_fallback,
                SUM(CASE WHEN exhibition_count BETWEEN 1 AND 3
                         THEN 1 ELSE 0 END)                                 AS partial_exhib
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND DATE(notified_at) >= ?
        """, (cutoff,))
        row = cur.fetchone()
        total, with_ex, no_ex, unk_ex, adv_fb, partial = (v or 0 for v in row)

        # ── 修正効果の経過観察 ─────────────────────────────
        # 修正リリース後(2026-06-26〜)に品質データが記録された最初の購入日
        cur.execute("""
            SELECT MIN(DATE(notified_at))
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND had_exhibition IS NOT NULL
        """)
        first_quality_row = cur.fetchone()
        first_quality_date = first_quality_row[0] if first_quality_row and first_quality_row[0] else None

        # 直近の購入N件が全て had_exhibition=1 かどうか（連続正常ストリーク）
        cur.execute("""
            SELECT had_exhibition
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND had_exhibition IS NOT NULL
            ORDER BY notified_at DESC
            LIMIT 20
        """)
        recent_quality = [r[0] for r in cur.fetchall()]
        consecutive_ok = 0
        for v in recent_quality:
            if v == 1:
                consecutive_ok += 1
            else:
                break

        # 修正前の旧レコード数（NULL = スナップショット未記録 = 2026-06-26以前）
        cur.execute("""
            SELECT COUNT(*) FROM bet_notifications
            WHERE notification_type = 'confirmed' AND had_exhibition IS NULL
        """)
        legacy_count = cur.fetchone()[0] or 0

        result['metrics'] = {
            'days': days,
            'total_confirmed': total,
            'with_exhibition': with_ex,
            'no_exhibition': no_ex,
            'unknown_exhibition': unk_ex,
            'advance_fallback': adv_fb,
            # exhibition_count 4-5 は欠場艇由来の可能性があるため除外
            # BETWEEN 1 AND 3 = 半数以下のみ取得できた明確な異常
            'partial_exhibition': partial,
            'first_quality_date': first_quality_date,
            'consecutive_ok_streak': consecutive_ok,
            'legacy_null_records': legacy_count,
        }

        warns = []
        if no_ex > 0:
            warns.append(f"展示タイムなし購入 {no_ex}件（force=True修正未機能の疑い）")
        if adv_fb > 0:
            warns.append(f"advanceフォールバック購入 {adv_fb}件（before未生成のまま購入）")
        if partial > 0:
            warns.append(f"展示取得が半数以下 {partial}件（取得エラーの可能性）")

        if warns:
            result['status'] = 'WARN'
            result['warnings'].extend(warns)
        elif total == 0:
            result['details'].append(f'直近{days}日に確定購入なし（正常 or パイプライン停止）')
        else:
            streak_msg = f"直近{consecutive_ok}件連続OK" if consecutive_ok > 0 else "品質データなし"
            legacy_msg = f" / 旧レコード{legacy_count}件(修正前・時間経過で自然消滅)" if legacy_count > 0 else ""
            result['details'].append(
                f'直近{days}日 {total}件: 全件展示込みbefore予測で購入 [{streak_msg}]{legacy_msg}'
            )
            if first_quality_date:
                result['details'].append(f'修正効果開始日: {first_quality_date}')

    finally:
        conn.close()

    return result


def check_condition_fire_rate(days: int = 30) -> dict:
    """6. 条件別発火率チェック（特定条件が急に0件になっていないか）"""
    result = {'status': 'OK', 'details': [], 'warnings': [], 'rates': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            result['details'].append('bet_notifications未作成（運用前）')
            return result

        today = datetime.now().date()
        cutoff = str(today - timedelta(days=days))

        cur.execute("""
            SELECT condition_id, COUNT(*) AS cnt
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND DATE(notified_at) >= ?
            GROUP BY condition_id
            ORDER BY cnt DESC
        """, (cutoff,))
        rows = cur.fetchall()
        fire_map = {r[0]: r[1] for r in rows}

        # バックテスト6年 / 72ヶ月 × 1ヶ月 ≒ 月期待件数（バックテスト統計は未保持のため簡易チェック）
        total_confirmed = sum(fire_map.values())
        result['rates'] = fire_map
        if total_confirmed == 0:
            result['status'] = 'WARN'
            result['warnings'].append(f'直近{days}日に confirmed 通知が0件（自動化停止の可能性）')
        else:
            result['details'].append(
                f'直近{days}日の条件別件数（合計{total_confirmed}件）: '
                + ', '.join(f'{k}:{v}件' for k, v in sorted(fire_map.items(), key=lambda x: -x[1]))
            )
        # 直近7日でも0件ならWARN（直近30日ありでも直近1週間に全く発火しないのは異常）
        cutoff7 = str(today - timedelta(days=7))
        cur.execute("""
            SELECT COUNT(*) FROM bet_notifications
            WHERE notification_type = 'confirmed' AND DATE(notified_at) >= ?
        """, (cutoff7,))
        recent7 = cur.fetchone()[0] or 0
        if recent7 == 0 and total_confirmed > 0:
            result['status'] = 'WARN'
            result['warnings'].append(f'直近7日に confirmed 通知が0件（条件フィルタ異常 or 開催なし）')
    finally:
        conn.close()
    return result


def check_dismissal_rate(days: int = 7) -> dict:
    """7. 見送り率チェック（dismissedが多すぎる場合はオッズ取得障害 or フィルタ異常）"""
    result = {'status': 'OK', 'details': [], 'warnings': [], 'stats': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            result['details'].append('bet_notifications未作成（運用前）')
            return result

        today = datetime.now().date()
        cutoff = str(today - timedelta(days=days))

        cur.execute("""
            SELECT
                SUM(CASE WHEN notification_type='confirmed' THEN 1 ELSE 0 END) AS confirmed,
                SUM(CASE WHEN notification_type='dismissed' THEN 1 ELSE 0 END) AS dismissed
            FROM bet_notifications
            WHERE DATE(notified_at) >= ?
        """, (cutoff,))
        row = cur.fetchone()
        confirmed = row[0] or 0
        dismissed = row[1] or 0
        total = confirmed + dismissed

        result['stats'] = {'confirmed': confirmed, 'dismissed': dismissed, 'total': total}

        if total == 0:
            result['details'].append(f'直近{days}日に購入・見送り記録なし（開催なし or 自動化停止）')
            return result

        dismissal_rate = 100.0 * dismissed / total
        result['stats']['dismissal_rate_pct'] = round(dismissal_rate, 1)

        # サンプル < 20件は小サンプル誤発火防止のためスキップ
        # 閾値 70%: 14/20件以上見送りで初めてWARN（7日間の低ボリューム週でも偽陽性を抑制）
        if total < 20:
            result['details'].append(
                f'直近{days}日の見送り率: {dismissal_rate:.1f}% '
                f'(confirmed={confirmed}, dismissed={dismissed}, 計{total}件) '
                f'[サンプル不足のためレート判定スキップ]'
            )
        elif dismissal_rate > 70.0:
            result['status'] = 'WARN'
            result['warnings'].append(
                f'見送り率 {dismissal_rate:.1f}% ({dismissed}/{total}件): '
                f'3-7分前再評価でほぼ全件落ちている。Webオッズ取得障害の可能性。'
            )
        elif total > 0 and dismissed == 0 and confirmed > 3:
            result['status'] = 'WARN'
            result['warnings'].append(
                f'見送り記録が0件({confirmed}件全確定): dismissed 保存ロジックの異常の可能性'
            )
        else:
            result['details'].append(
                f'直近{days}日の見送り率: {dismissal_rate:.1f}% '
                f'(confirmed={confirmed}, dismissed={dismissed}) [OK]'
            )
    finally:
        conn.close()
    return result


def check_scheduler_log_errors(recent_days: int = 3) -> dict:
    """8. schedulerログの WARN/ERROR 行数チェック（サイレント例外の早期検知）"""
    result = {'status': 'OK', 'details': [], 'warnings': [], 'log_stats': []}

    pattern = os.path.join(LOGS_DIR, 'scheduler_2026*.log')
    files = sorted(glob.glob(pattern))
    if not files:
        result['details'].append('scheduler ログなし（チェックスキップ）')
        return result

    today = datetime.now().date()
    target_files = []
    for f in files:
        m = re.search(r'scheduler_(\d{8})\.log', os.path.basename(f))
        if m:
            try:
                d = datetime.strptime(m.group(1), '%Y%m%d').date()
                if (today - d).days < recent_days:
                    target_files.append((d, f))
            except ValueError:
                pass

    if not target_files:
        result['details'].append(f'直近{recent_days}日のログなし（チェックスキップ）')
        return result

    WARN_THRESHOLD = 20
    ERROR_THRESHOLD = 3

    for d, fpath in sorted(target_files):
        try:
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                lines = fh.readlines()
            warn_cnt = sum(1 for l in lines if '[WARN]' in l or '[WARNING]' in l)
            error_cnt = sum(1 for l in lines if '[ERROR]' in l)
            stat = {'date': str(d), 'warn_count': warn_cnt, 'error_count': error_cnt}
            result['log_stats'].append(stat)
            if error_cnt >= ERROR_THRESHOLD or warn_cnt >= WARN_THRESHOLD:
                result['status'] = 'WARN'
                result['warnings'].append(
                    f'{d}: ERROR {error_cnt}行 / WARN {warn_cnt}行 '
                    f'(閾値: ERROR>={ERROR_THRESHOLD} / WARN>={WARN_THRESHOLD})'
                )
            else:
                result['details'].append(
                    f'{d}: ERROR {error_cnt}行 / WARN {warn_cnt}行 [OK]'
                )
        except Exception as e:
            result['warnings'].append(f'{d}: ログ読み取りエラー ({e})')

    return result


def check_new_log_fields(days: int = 7) -> dict:
    """9. 新規ログフィールド品質チェック（A-1〜B-2で追加したカラムが正しく保存されているか）

    確認対象:
      bet_notifications（confirmed）: condition_id / minutes_before_deadline / is_gap1
      reconcile_log: hit_count / total_bet / total_return

    days=7 のみチェック（2026-07-09実装。それ以前のレコードはNULLが正常のため除外）
    """
    result = {'status': 'OK', 'details': [], 'warnings': [], 'metrics': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()

    try:
        today = datetime.now().date()
        cutoff = str(today - timedelta(days=days))
        # hit_count/total_bet/total_return / minutes_before_deadline/is_gap1 は 2026-07-09 実装
        # それ以前のNULLは正常。bn/rl両方に同じクランプを適用（非対称防止）
        QUALITY_IMPL_DATE = '2026-07-09'
        bn_cutoff = max(cutoff, QUALITY_IMPL_DATE)
        rl_cutoff = max(cutoff, QUALITY_IMPL_DATE)

        # ── bet_notifications ──────────────────────────────────────
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bet_notifications'")
        if not cur.fetchone():
            result['details'].append('bet_notifications未作成（運用前）')
            return result

        cur.execute("PRAGMA table_info(bet_notifications)")
        bn_cols = {row[1] for row in cur.fetchall()}

        required_bn = ['condition_id', 'minutes_before_deadline', 'is_gap1']
        missing_bn = [c for c in required_bn if c not in bn_cols]
        if missing_bn:
            result['status'] = 'WARN'
            result['warnings'].append(f'bet_notifications にカラム未追加: {missing_bn}（DBマイグレーション未実行）')
            result['metrics']['bn_missing_columns'] = missing_bn
        else:
            # 直近N日の confirmed レコードで各フィールドのNULL件数を確認
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN condition_id IS NULL OR condition_id = '' THEN 1 ELSE 0 END) AS null_cid,
                    SUM(CASE WHEN minutes_before_deadline IS NULL THEN 1 ELSE 0 END) AS null_min,
                    SUM(CASE WHEN is_gap1 IS NULL THEN 1 ELSE 0 END) AS null_gap1
                FROM bet_notifications
                WHERE notification_type = 'confirmed'
                  AND DATE(notified_at) >= ?
            """, (bn_cutoff,))
            row = cur.fetchone()
            total_bn, null_cid, null_min, null_gap1 = (v or 0 for v in row)

            result['metrics']['bn_confirmed_total'] = total_bn
            result['metrics']['bn_null_condition_id'] = null_cid
            result['metrics']['bn_null_minutes_before_deadline'] = null_min
            result['metrics']['bn_null_is_gap1'] = null_gap1

            if total_bn == 0:
                result['details'].append(f'直近{days}日に confirmed 記録なし（チェックスキップ）')
            else:
                warns = []
                if null_cid > 0:
                    warns.append(f'condition_id が未設定の購入: {null_cid}/{total_bn}件')
                if null_min > 0:
                    warns.append(f'minutes_before_deadline が未設定: {null_min}/{total_bn}件')
                if null_gap1 > 0:
                    warns.append(f'is_gap1 が未設定: {null_gap1}/{total_bn}件')

                if warns:
                    result['status'] = 'WARN'
                    result['warnings'].extend(warns)
                else:
                    result['details'].append(
                        f'bet_notifications 直近{days}日 {total_bn}件: '
                        f'condition_id/minutes_before_deadline/is_gap1 全件設定済み [OK]'
                    )

        # ── reconcile_log ──────────────────────────────────────────
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reconcile_log'")
        if not cur.fetchone():
            result['details'].append('reconcile_log未作成（reconcile未実行）')
            return result

        cur.execute("PRAGMA table_info(reconcile_log)")
        rl_col_rows = cur.fetchall()
        rl_cols = {row[1] for row in rl_col_rows}

        required_rl = ['hit_count', 'total_bet', 'total_return']
        missing_rl = [c for c in required_rl if c not in rl_cols]
        if missing_rl:
            result['status'] = 'WARN'
            result['warnings'].append(f'reconcile_log にカラム未追加: {missing_rl}（DBマイグレーション未実行）')
            result['metrics']['rl_missing_columns'] = missing_rl
        else:
            # 日付絞り込みカラムを動的に選択（reconcile_logは'date'カラムを使用）
            date_col = 'race_date' if 'race_date' in rl_cols else (
                'inserted_at' if 'inserted_at' in rl_cols else (
                    'date' if 'date' in rl_cols else None
                )
            )

            if date_col:
                cur.execute(f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN hit_count IS NULL THEN 1 ELSE 0 END) AS null_hc,
                        SUM(CASE WHEN total_bet IS NULL THEN 1 ELSE 0 END) AS null_tb,
                        SUM(CASE WHEN total_return IS NULL THEN 1 ELSE 0 END) AS null_tr
                    FROM reconcile_log
                    WHERE DATE({date_col}) >= ?
                """, (rl_cutoff,))
            else:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN hit_count IS NULL THEN 1 ELSE 0 END) AS null_hc,
                        SUM(CASE WHEN total_bet IS NULL THEN 1 ELSE 0 END) AS null_tb,
                        SUM(CASE WHEN total_return IS NULL THEN 1 ELSE 0 END) AS null_tr
                    FROM reconcile_log
                """)
            row = cur.fetchone()
            total_rl, null_hc, null_tb, null_tr = (v or 0 for v in row)

            result['metrics']['rl_total'] = total_rl
            result['metrics']['rl_null_hit_count'] = null_hc
            result['metrics']['rl_null_total_bet'] = null_tb
            result['metrics']['rl_null_total_return'] = null_tr

            if total_rl == 0:
                result['details'].append(f'直近{days}日に reconcile_log 記録なし（reconcile未実行）')
            else:
                rl_warns = []
                if null_hc > 0:
                    rl_warns.append(f'reconcile_log hit_count が未設定: {null_hc}/{total_rl}件')
                if null_tb > 0:
                    rl_warns.append(f'reconcile_log total_bet が未設定: {null_tb}/{total_rl}件')
                if null_tr > 0:
                    rl_warns.append(f'reconcile_log total_return が未設定: {null_tr}/{total_rl}件')

                if rl_warns:
                    result['status'] = 'WARN'
                    result['warnings'].extend(rl_warns)
                else:
                    result['details'].append(
                        f'reconcile_log 直近{days}日 {total_rl}件: '
                        f'hit_count/total_bet/total_return 全件設定済み [OK]'
                    )

    finally:
        conn.close()

    return result


def check_oos_rolling_roi():
    """実運用OOS ROIの継続監視（kill criteria チェック）

    kill基準（Opusレビュー 2026-07-13 制度化）:
      WARN : 全期間OOS ROI < 120% かつ N >= 30件
      KILL : 全期間OOS ROI < 100% かつ N >= 30件  → 条件レビュー必須
    """
    WARN_THRESHOLD = 120.0
    KILL_THRESHOLD = 100.0
    MIN_BETS = 30  # 判定に最低限必要なベット数（件数不足は参考値扱い）

    result = {'status': 'OK', 'details': [], 'warnings': [], 'metrics': {}}
    conn = sqlite3.connect(DATABASE_PATH)
    cur = conn.cursor()
    try:
        today = datetime.now().date()

        # --- 全期間集計 ---
        cur.execute("""
            SELECT SUM(total_bet), SUM(total_return), SUM(hit_count), COUNT(*), MIN(date), MAX(date)
            FROM reconcile_log
            WHERE total_bet IS NOT NULL AND total_bet > 0
        """)
        row = cur.fetchone()
        all_bet   = row[0] or 0
        all_ret   = row[1] or 0
        all_hits  = row[2] or 0
        all_days  = row[3] or 0
        date_from = row[4] or '-'
        date_to   = row[5] or '-'
        n_all     = int(all_bet // 100)  # 概算件数（100円/件）
        roi_all   = all_ret / all_bet * 100 if all_bet > 0 else None

        # --- 直近30日集計 ---
        cutoff_30 = str(today - timedelta(days=30))
        cur.execute("""
            SELECT SUM(total_bet), SUM(total_return), SUM(hit_count)
            FROM reconcile_log
            WHERE total_bet IS NOT NULL AND total_bet > 0 AND date >= ?
        """, (cutoff_30,))
        row30 = cur.fetchone()
        bet30  = row30[0] or 0
        ret30  = row30[1] or 0
        hits30 = row30[2] or 0
        n30    = int(bet30 // 100)
        roi30  = ret30 / bet30 * 100 if bet30 > 0 else None

        result['metrics'] = {
            'all_time_n':    n_all,
            'all_time_roi':  round(roi_all, 1) if roi_all is not None else None,
            'all_time_hits': int(all_hits or 0),
            'all_time_days': all_days,
            'date_from':     date_from,
            'date_to':       date_to,
            'last30d_n':     n30,
            'last30d_roi':   round(roi30, 1) if roi30 is not None else None,
            'last30d_hits':  int(hits30 or 0),
            'kill_threshold': KILL_THRESHOLD,
            'warn_threshold': WARN_THRESHOLD,
            'min_bets':       MIN_BETS,
        }

        if all_days == 0:
            result['details'].append('reconcile_log に有効データなし（OOS追跡未開始）')
            return result

        if n_all < MIN_BETS:
            result['details'].append(
                f'OOS蓄積中（{n_all}件/{MIN_BETS}件以上で本格判定） '
                f'| 全期間: {n_all}件 / ROI={roi_all:.1f}% / 的中{int(all_hits or 0)}件'
            )
            result['details'].append(
                f'観測期間: {date_from} 〜 {date_to}（{all_days}日分）'
            )
            return result

        # --- 判定 ---
        roi_str = f'{roi_all:.1f}%' if roi_all is not None else 'N/A'
        result['details'].append(
            f'全期間: {n_all}件 / ROI={roi_str} / 的中{int(all_hits or 0)}件 '
            f'({date_from}〜{date_to})'
        )
        roi30_str = f'{roi30:.1f}%' if roi30 is not None else 'N/A'
        result['details'].append(
            f'直近30日: {n30}件 / ROI={roi30_str} / 的中{int(hits30 or 0)}件'
        )

        if roi_all is not None and roi_all < KILL_THRESHOLD:
            result['status'] = 'WARN'
            result['warnings'].append(
                f'🔴 OOS ROI {roi_all:.1f}% < {KILL_THRESHOLD}% → 条件レビュー必須'
            )
        elif roi_all is not None and roi_all < WARN_THRESHOLD:
            result['status'] = 'WARN'
            result['warnings'].append(
                f'⚠️ OOS ROI {roi_all:.1f}% < {WARN_THRESHOLD}%（注意水準）'
            )
        else:
            result['details'].append(
                f'OOS ROI {roi_str} ≥ {WARN_THRESHOLD}% ✓（kill基準クリア）'
            )

    finally:
        conn.close()

    return result


def main():
    print("# 異常チェック結果レポート", flush=True)
    print(f"# 実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(flush=True)

    report = {
        'executed_at': datetime.now().isoformat(),
        'checks': {}
    }

    checks = [
        ('pipeline',        '自動化パイプライン稼働',  check_scheduler_pipeline),
        ('data',            'データ収集欠損',           check_data_coverage),
        ('a_rate',          'A率（信頼度分布）',         check_a_rate),
        ('performance',     '直近購入・的中推移',        check_recent_performance),
        ('pred_quality',    '購入予測品質',              check_bet_prediction_quality),
        ('condition_fire',  '条件別発火率',              check_condition_fire_rate),
        ('dismissal_rate',  '見送り率',                  check_dismissal_rate),
        ('log_errors',      'ログERROR/WARN件数',        check_scheduler_log_errors),
        ('log_fields',      '新規ログフィールド品質',    check_new_log_fields),
        ('oos_roi',         'OOS ROI（kill基準監視）',   check_oos_rolling_roi),
    ]

    overall_status = 'OK'
    for key, label, func in checks:
        r = func()
        report['checks'][key] = r
        status = r['status']
        if status != 'OK':
            overall_status = 'WARN'
        print(f"[{status}] {label}")
        for w in r.get('warnings', []):
            print(f"  [W]  {w}")
        for d in r.get('details', []):
            print(f"     {d}")
        print(flush=True)

    report['overall_status'] = overall_status

    # JSON出力（Claudeが解釈用）
    print("=" * 60)
    print("## JSON DATA ##")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if overall_status == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
