#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
invariant_watch.py -- Invariant Watch v1  Phase 2
「動いているが正常ではない」状態を不変条件チェックで自動検知する。

絶対制約:
  - DB に対して SELECT のみ（書き込み・修正・自動復旧は一切しない）
  - 帯域ファイルは読み取り専用（変更はユーザー承認が必要）
  - 全チェック 5 分以内に完了
  - 標準ライブラリ + sqlite3 のみ（外部依存なし）

使い方:
    python scripts/monitoring/invariant_watch.py
    python scripts/monitoring/invariant_watch.py --category A
    python scripts/monitoring/invariant_watch.py --category B
    python scripts/monitoring/invariant_watch.py --dry-run   # Discord通知しない

出力:
    reports/invariant_watch/YYYY-WW.md  (週次レポート)
    reports/invariant_watch/history.jsonl

アラートレベル:
    GREEN  = 正常
    YELLOW = 観察対象 (3週連続 YELLOW -> RED)
    RED    = 即時報告 (#watch チャンネルに Discord 通知)
"""

import sys
import io
import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DB_PATH      = PROJECT_ROOT / "data" / "boatrace.db"
BANDS_PATH   = PROJECT_ROOT / "config" / "invariant_bands.json"
REPORTS_DIR  = PROJECT_ROOT / "reports" / "invariant_watch"
HISTORY_PATH = REPORTS_DIR / "history.jsonl"
NOTIFY_SCRIPT = PROJECT_ROOT / "scripts" / "automation" / "notify.py"

# 帯域ファイルの期待 SHA256（Phase 1 実行時に確定）
EXPECTED_BANDS_HASH = "52d9242e6b67a5e9221ee88e54d6eb14faad81286c995567c6e3c7670d8444e2"

GREEN  = "GREEN"
YELLOW = "YELLOW"
RED    = "RED"
SKIP   = "SKIP"       # n_min未満などで判定保留


# ============================================================
# ユーティリティ
# ============================================================

def now_iso():
    return datetime.now().isoformat(timespec="seconds")

def week_label():
    t = date.today()
    return f"{t.year}-W{t.isocalendar()[1]:02d}"

def result(check_id, name, status, value, message, detail=None):
    r = {
        "id": check_id, "name": name, "status": status,
        "value": value, "message": message
    }
    if detail:
        r["detail"] = detail
    return r

def ok(check_id, name, value, message, detail=None):
    return result(check_id, name, GREEN, value, message, detail)

def warn(check_id, name, value, message, detail=None):
    return result(check_id, name, YELLOW, value, message, detail)

def red(check_id, name, value, message, detail=None):
    return result(check_id, name, RED, value, message, detail)

def skip(check_id, name, value, message):
    return result(check_id, name, SKIP, value, message)

def load_bands():
    """帯域ファイルを読み込み、ハッシュ検証する"""
    with open(BANDS_PATH, encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw)
    stored_hash = data.get("_content_hash", "")
    # ハッシュ検証: _content_hash フィールドを除外して再計算
    data_without_hash = {k: v for k, v in data.items() if k != "_content_hash"}
    canonical = json.dumps(data_without_hash, ensure_ascii=False, sort_keys=True)
    actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual_hash != stored_hash:
        raise ValueError(
            f"帯域ファイルのハッシュが一致しません。\n"
            f"  格納値: {stored_hash}\n"
            f"  実計算: {actual_hash}\n"
            f"  -> 無断変更の可能性があります"
        )
    if stored_hash != EXPECTED_BANDS_HASH:
        raise ValueError(
            f"帯域ファイルが Phase 1 実行時と異なります。\n"
            f"  期待値: {EXPECTED_BANDS_HASH}\n"
            f"  実際値: {stored_hash}\n"
            f"  -> ユーザー承認なしの変更"
        )
    return data

def db_connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def load_history():
    """history.jsonl から直近の週次レコードリストを返す"""
    if not HISTORY_PATH.exists():
        return []
    records = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except Exception:
                    pass
    return records

def count_consecutive_yellows(check_id, history):
    """直近の history から check_id の連続 YELLOW 数を返す（最新から遡る）"""
    count = 0
    for rec in reversed(history):
        for r in rec.get("results", []):
            if r.get("id") == check_id:
                if r.get("status") == YELLOW:
                    count += 1
                else:
                    return count
                break
    return count


# ============================================================
# カテゴリ A: 整合系
# ============================================================

def check_a1(conn):
    """A-1: 購入条件一致率 — 確定購入に before 予測が存在するか"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN rp.race_id IS NOT NULL THEN 1 ELSE 0 END) as has_pred
            FROM bet_notifications bn
            LEFT JOIN race_predictions rp
                ON bn.race_id = rp.race_id
               AND rp.prediction_type = 'before'
               AND rp.rank_prediction = 1
            WHERE bn.notification_type = 'confirmed'
              AND DATE(bn.notified_at) >= ?
        """, (cutoff,))
        row = cur.fetchone()
        total, has_pred = row["total"], row["has_pred"]
        if total == 0:
            return skip("A-1", "購入条件一致率", "0件", "直近7日に confirmed 購入なし")
        rate = has_pred / total * 100
        msg = f"{has_pred}/{total} 件 ({rate:.1f}%) に before 予測あり"
        if rate >= 95:
            return ok("A-1", "購入条件一致率", f"{rate:.1f}%", msg)
        elif rate >= 80:
            return warn("A-1", "購入条件一致率", f"{rate:.1f}%", msg)
        else:
            return red("A-1", "購入条件一致率", f"{rate:.1f}%", msg)
    except Exception as e:
        return red("A-1", "購入条件一致率", "ERROR", str(e), detail=traceback.format_exc())


def check_a2(conn):
    """A-2: 通知・購入件数整合 — shadow_bets と bet_notifications の confirmed 件数が一致するか"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=7)).isoformat()

        cur.execute("""
            SELECT COUNT(*) FROM bet_notifications
            WHERE notification_type='confirmed' AND DATE(notified_at) >= ?
        """, (cutoff,))
        bn_cnt = cur.fetchone()[0]

        cur.execute("""
            SELECT COUNT(*) FROM shadow_bets
            WHERE notification_type='confirmed' AND DATE(created_at) >= ?
        """, (cutoff,))
        sb_cnt = cur.fetchone()[0]

        diff = abs(bn_cnt - sb_cnt)
        val  = f"bet_notifications={bn_cnt} / shadow_bets={sb_cnt}"
        if diff == 0:
            return ok("A-2", "通知・購入件数整合", val, "件数一致")
        elif diff <= 2:
            return warn("A-2", "通知・購入件数整合", val, f"差異 {diff} 件 (許容 ≤2)")
        else:
            return red("A-2", "通知・購入件数整合", val, f"差異 {diff} 件 (許容 ≤2)")
    except Exception as e:
        return red("A-2", "通知・購入件数整合", "ERROR", str(e), detail=traceback.format_exc())


def check_a3(conn):
    """A-3: 予測件数 = レース件数 — 直近7日の各日で before 予測カバー率 ≥90%"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        cur.execute("""
            SELECT r.race_date,
                   COUNT(DISTINCT r.id) AS race_cnt,
                   COUNT(DISTINCT rp.race_id) AS pred_cnt
            FROM races r
            LEFT JOIN race_predictions rp
                ON r.id = rp.race_id
               AND rp.prediction_type = 'before'
               AND rp.rank_prediction = 1
            WHERE r.race_date BETWEEN ? AND ?
            GROUP BY r.race_date
            ORDER BY r.race_date
        """, (cutoff, yesterday))
        rows = cur.fetchall()
        if not rows:
            return skip("A-3", "予測カバー率", "0日", "直近7日のデータなし")

        low_days = []
        for row in rows:
            d, rc, pc = row["race_date"], row["race_cnt"], row["pred_cnt"]
            if rc == 0:
                continue
            cov = pc / rc * 100
            if cov < 90:
                low_days.append(f"{d}: {pc}/{rc} ({cov:.0f}%)")

        val = f"{len(rows)}日確認"
        if not low_days:
            return ok("A-3", "予測カバー率", val, "全日 ≥90%")
        elif len(low_days) <= 1:
            return warn("A-3", "予測カバー率", val, f"{len(low_days)}日が<90%", detail="\n".join(low_days))
        else:
            return red("A-3", "予測カバー率", val, f"{len(low_days)}日が<90%", detail="\n".join(low_days))
    except Exception as e:
        return red("A-3", "予測カバー率", "ERROR", str(e), detail=traceback.format_exc())


def check_a4(conn):
    """A-4: before 予測なし購入 = 0"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=60)).isoformat()
        cur.execute("""
            SELECT COUNT(*) FROM bet_notifications bn
            LEFT JOIN race_predictions rp
                ON bn.race_id = rp.race_id
               AND rp.prediction_type = 'before'
               AND rp.rank_prediction = 1
            WHERE bn.notification_type = 'confirmed'
              AND DATE(bn.notified_at) >= ?
              AND rp.race_id IS NULL
        """, (cutoff,))
        cnt = cur.fetchone()[0]
        val = f"{cnt}件"
        if cnt == 0:
            return ok("A-4", "before予測なし購入", val, "before予測なしの購入は 0件")
        else:
            return red("A-4", "before予測なし購入", val,
                       f"before 予測なし確定購入 {cnt} 件 (直近60日)")
    except Exception as e:
        return red("A-4", "before予測なし購入", "ERROR", str(e), detail=traceback.format_exc())


# ============================================================
# カテゴリ B: 分布系
# ============================================================

def check_b1(conn, bands):
    """B-1: 週次発火率 vs 帯域"""
    try:
        cur = conn.cursor()
        b = bands["b1_weekly_fire_rate"]
        lo = b["warn_absolute_lo"]
        hi = b["warn_absolute_hi"]

        # 直近4週の週ごとの confirmed 件数
        cutoff = (date.today() - timedelta(days=28)).isoformat()
        cur.execute("""
            SELECT STRFTIME('%Y-W%W', notified_at) AS wk, COUNT(*) AS cnt
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND DATE(notified_at) >= ?
            GROUP BY wk ORDER BY wk
        """, (cutoff,))
        rows = cur.fetchall()
        if not rows:
            return skip("B-1", "週次発火率", "0件", "直近28日に confirmed データなし")

        week_cnts = [r["cnt"] for r in rows]
        mu = b["confirmed_weekly_mu"]
        band_lo = b["confirmed_band_lo"]
        band_hi = b["confirmed_band_hi"]

        out_of_band = [c for c in week_cnts if c < lo or c > hi]
        val = f"週平均={sum(week_cnts)/len(week_cnts):.1f} (帯域μ={mu:.1f})"
        detail = " | ".join([f"{r['wk']}:{r['cnt']}" for r in rows])

        if not out_of_band:
            return ok("B-1", "週次発火率", val, f"全{len(rows)}週が帯域内", detail=detail)
        elif len(out_of_band) <= 1:
            return warn("B-1", "週次発火率", val,
                        f"{len(out_of_band)}/{len(rows)} 週が絶対帯域外 [lo={lo}, hi={hi}]",
                        detail=detail)
        else:
            return red("B-1", "週次発火率", val,
                       f"{len(out_of_band)}/{len(rows)} 週が絶対帯域外",
                       detail=detail)
    except Exception as e:
        return red("B-1", "週次発火率", "ERROR", str(e), detail=traceback.format_exc())


def check_b2(conn, bands):
    """B-2: スコア分布 vs ベースライン"""
    try:
        cur = conn.cursor()
        b = bands["b2_score_distribution"]
        tol = b["warn_tolerance_pt"]
        cutoff = (date.today() - timedelta(days=28)).isoformat()

        cur.execute("""
            SELECT rp.total_score
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE rp.prediction_type = 'before'
              AND rp.rank_prediction  = 1
              AND r.race_date >= ?
              AND rp.total_score IS NOT NULL
            ORDER BY rp.total_score
        """, (cutoff,))
        scores = [r[0] for r in cur.fetchall()]
        if len(scores) < 100:
            return skip("B-2", "スコア分布", f"N={len(scores)}", "サンプル不足 (<100)")

        def pct(p):
            idx = int(len(scores) * p / 100)
            return scores[min(idx, len(scores)-1)]

        diffs = {
            "P25": pct(25) - b["p25"],
            "P50": pct(50) - b["p50"],
            "P75": pct(75) - b["p75"],
            "P90": pct(90) - b["p90"],
        }
        max_abs = max(abs(v) for v in diffs.values())
        val = f"P25={pct(25):.1f} P50={pct(50):.1f} P75={pct(75):.1f} P90={pct(90):.1f}"
        detail = " | ".join([f"{k}:{v:+.1f}pt" for k, v in diffs.items()])

        if max_abs <= tol:
            return ok("B-2", "スコア分布", val, f"最大乖離 {max_abs:.1f}pt ≤ {tol}pt", detail=detail)
        elif max_abs <= tol * 1.5:
            return warn("B-2", "スコア分布", val,
                        f"最大乖離 {max_abs:.1f}pt > {tol}pt (N={len(scores)})", detail=detail)
        else:
            return red("B-2", "スコア分布", val,
                       f"最大乖離 {max_abs:.1f}pt > {tol*1.5:.1f}pt (N={len(scores)})", detail=detail)
    except Exception as e:
        return red("B-2", "スコア分布", "ERROR", str(e), detail=traceback.format_exc())


def check_b3(conn, bands):
    """B-3: 信頼度構成比 vs ベースライン"""
    try:
        cur = conn.cursor()
        b = bands["b3_confidence_composition"]
        tol = b["warn_tolerance_pt"]
        base = b["composition_pct"]
        cutoff = (date.today() - timedelta(days=28)).isoformat()

        cur.execute("""
            SELECT rp.confidence, COUNT(*) AS cnt
            FROM race_predictions rp
            JOIN races r ON rp.race_id = r.id
            WHERE rp.prediction_type = 'before'
              AND rp.rank_prediction  = 1
              AND r.race_date >= ?
              AND rp.confidence IS NOT NULL
            GROUP BY rp.confidence
        """, (cutoff,))
        rows = {r["confidence"]: r["cnt"] for r in cur.fetchall()}
        total = sum(rows.values())
        if total < 100:
            return skip("B-3", "信頼度構成比", f"N={total}", "サンプル不足 (<100)")

        cur_pct = {k: rows.get(k, 0) / total * 100 for k in ["A","B","C","D","E"]}
        diffs = {k: cur_pct[k] - float(base.get(k, 0)) for k in ["A","B","C","D","E"]}
        max_abs = max(abs(v) for v in diffs.values())

        val = f"A={cur_pct['A']:.1f}% B={cur_pct['B']:.1f}% C={cur_pct['C']:.1f}%"
        detail = " | ".join([f"{k}:{v:+.1f}pt" for k, v in diffs.items()])

        if max_abs <= tol:
            return ok("B-3", "信頼度構成比", val, f"最大乖離 {max_abs:.1f}pt ≤ {tol}pt (N={total})", detail=detail)
        elif max_abs <= tol * 1.5:
            return warn("B-3", "信頼度構成比", val,
                        f"最大乖離 {max_abs:.1f}pt > {tol}pt (N={total})", detail=detail)
        else:
            return red("B-3", "信頼度構成比", val,
                       f"最大乖離 {max_abs:.1f}pt > {tol*1.5:.1f}pt (N={total})", detail=detail)
    except Exception as e:
        return red("B-3", "信頼度構成比", "ERROR", str(e), detail=traceback.format_exc())


def check_b4(conn, bands):
    """B-4: 三連単的中率 — binomial 90%CI チェック"""
    try:
        cur = conn.cursor()
        b = bands["b4_hit_rate"]
        p0 = b["baseline_pct"] / 100
        n_min = b["n_min_to_alert"]
        ci_conf = b["ci_confidence"]
        z = 1.645  # 90% two-sided -> 5% each tail

        cutoff = (date.today() - timedelta(days=90)).isoformat()
        cur.execute("""
            SELECT COUNT(*) AS n,
                   SUM(CASE WHEN is_hit=1 THEN 1 ELSE 0 END) AS hits
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND is_hit IS NOT NULL
              AND DATE(notified_at) >= ?
        """, (cutoff,))
        row = cur.fetchone()
        n, hits = row["n"], row["hits"] or 0

        if n < n_min:
            return skip("B-4", "三連単的中率",
                        f"{hits}/{n} (n_min={n_min})",
                        f"サンプル数 {n} < {n_min} のため判定保留 (ベースライン {p0*100:.2f}%)")

        obs_p = hits / n
        se = math.sqrt(p0 * (1 - p0) / n)
        ci_lo = max(0.0, p0 - z * se)
        ci_hi = p0 + z * se
        val = f"{hits}/{n} ({obs_p*100:.2f}%) CI=[{ci_lo*100:.2f}%, {ci_hi*100:.2f}%]"

        if ci_lo <= obs_p <= ci_hi:
            return ok("B-4", "三連単的中率", val, f"ベースライン {p0*100:.2f}% の90%CI内")
        else:
            direction = "高すぎ" if obs_p > ci_hi else "低すぎ"
            status_fn = warn if abs(obs_p - p0) < 2 * se else red
            return status_fn("B-4", "三連単的中率", val,
                             f"90%CI外 ({direction}) ベースライン={p0*100:.2f}%")
    except Exception as e:
        return red("B-4", "三連単的中率", "ERROR", str(e), detail=traceback.format_exc())


# ============================================================
# カテゴリ C: 鮮度系
# ============================================================

def check_c1(conn):
    """C-1: テーブル鮮度 — 主要テーブルの最終挿入が N 日以内"""
    try:
        cur = conn.cursor()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        checks = [
            ("races",            "SELECT MAX(created_at) FROM races"),
            ("entries",          "SELECT MAX(created_at) FROM entries"),
            ("results",          "SELECT MAX(created_at) FROM results"),
            ("race_details",     "SELECT MAX(created_at) FROM race_details"),
            ("race_predictions", "SELECT MAX(generated_at) FROM race_predictions WHERE prediction_type='before'"),
        ]
        stale = []
        for tbl, sql in checks:
            cur.execute(sql)
            val = cur.fetchone()[0]
            if val is None:
                stale.append(f"{tbl}: NULL")
                continue
            # 日付部分だけ比較
            last_date = val[:10]
            days_ago = (date.today() - date.fromisoformat(last_date)).days
            if days_ago > 3:
                stale.append(f"{tbl}: {last_date} ({days_ago}日前)")

        val = f"{len(checks)}テーブル確認"
        if not stale:
            return ok("C-1", "テーブル鮮度", val, "全テーブル 3日以内に更新あり")
        elif len(stale) == 1:
            return warn("C-1", "テーブル鮮度", val, f"{stale[0]} が古い", detail="\n".join(stale))
        else:
            return red("C-1", "テーブル鮮度", val, f"{len(stale)} テーブルが古い", detail="\n".join(stale))
    except Exception as e:
        return red("C-1", "テーブル鮮度", "ERROR", str(e), detail=traceback.format_exc())


def check_c2(conn):
    """C-2: racer_features ビンテージ — 最終生成が 7 日以内"""
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'racer%features%'")
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            return skip("C-2", "racer_features鮮度", "テーブルなし", "racer_features テーブルが存在しない")

        # テーブルごとに適切な日付カラムを使う
        date_col_map = {
            "racer_features":       "race_date",
            "racer_venue_features": "computed_at",
        }
        stale = []
        for tbl in tables:
            dc = date_col_map.get(tbl, "race_date")
            try:
                cur.execute(f"SELECT MAX({dc}) FROM {tbl}")
                val = cur.fetchone()[0]
                if val is None:
                    stale.append(f"{tbl}: NULL (データなし)")
                    continue
                days_ago = (date.today() - date.fromisoformat(val[:10])).days
                if days_ago > 7:
                    stale.append(f"{tbl}: {val[:10]} ({days_ago}日前)")
            except Exception as ex:
                stale.append(f"{tbl}: クエリ失敗 ({ex})")

        val = ", ".join(tables)
        if not stale:
            return ok("C-2", "racer_features鮮度", val, "7日以内に更新あり")
        else:
            return warn("C-2", "racer_features鮮度", val, " / ".join(stale))
    except Exception as e:
        return red("C-2", "racer_features鮮度", "ERROR", str(e), detail=traceback.format_exc())


def check_c3(conn):
    """C-3: advance フォールバック率 = 0 (直近7日)"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=7)).isoformat()
        cur.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN pred_type_used = 'advance' THEN 1 ELSE 0 END) AS fallback
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND DATE(notified_at) >= ?
        """, (cutoff,))
        row = cur.fetchone()
        total, fallback = row["total"], row["fallback"] or 0
        val = f"{fallback}/{total} 件"
        if fallback == 0:
            return ok("C-3", "advanceフォールバック率", val, "フォールバック購入なし (before予測が使われている)")
        else:
            return red("C-3", "advanceフォールバック率", val,
                       f"before予測なしの advance 購入 {fallback} 件 (直近30日)")
    except Exception as e:
        return red("C-3", "advanceフォールバック率", "ERROR", str(e), detail=traceback.format_exc())


def check_c4(conn):
    """C-4: 展示データ充足 — had_exhibition=0 の確定購入 = 0"""
    try:
        cur = conn.cursor()
        cutoff = (date.today() - timedelta(days=30)).isoformat()
        cur.execute("""
            SELECT COUNT(*) AS no_ex,
                   (SELECT COUNT(*) FROM bet_notifications
                    WHERE notification_type='confirmed' AND DATE(notified_at) >= ?) AS total
            FROM bet_notifications
            WHERE notification_type = 'confirmed'
              AND DATE(notified_at) >= ?
              AND (had_exhibition = 0 OR had_exhibition IS NULL)
        """, (cutoff, cutoff))
        row = cur.fetchone()
        no_ex = row["no_ex"]
        total = row["total"]
        val = f"{no_ex}/{total} 件が展示なし"
        if no_ex == 0:
            return ok("C-4", "展示データ充足", f"0/{total}", "展示なし購入 0件")
        else:
            return red("C-4", "展示データ充足", val,
                       f"had_exhibition=0 の確定購入 {no_ex} 件 (force=True 修正が機能していない可能性)")
    except Exception as e:
        return red("C-4", "展示データ充足", "ERROR", str(e), detail=traceback.format_exc())


def check_c5(conn, bands):
    """C-5: adjusted_weight 欠損率 vs ベースライン"""
    try:
        cur = conn.cursor()
        b = bands["c5_adjusted_weight_missing"]
        warn_thr = b["warn_threshold_pct"]
        red_thr  = b["red_threshold_pct"]
        cutoff = (date.today() - timedelta(days=30)).isoformat()

        cur.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN rd.adjusted_weight IS NULL THEN 1 ELSE 0 END) AS nulls
            FROM race_details rd
            JOIN races r ON rd.race_id = r.id
            WHERE r.race_date >= ?
        """, (cutoff,))
        row = cur.fetchone()
        total, nulls = row["total"], row["nulls"] or 0
        if total == 0:
            return skip("C-5", "adjusted_weight欠損率", "0行", "直近30日の race_details なし")
        null_pct = nulls / total * 100
        base = b["baseline_null_pct"]
        val = f"{null_pct:.1f}% (ベースライン={base}%)"

        if null_pct <= warn_thr:
            return ok("C-5", "adjusted_weight欠損率", val, f"{nulls}/{total} 行が NULL")
        elif null_pct <= red_thr:
            return warn("C-5", "adjusted_weight欠損率", val,
                        f"欠損率 {null_pct:.1f}% > WARN閾値 {warn_thr}%")
        else:
            return red("C-5", "adjusted_weight欠損率", val,
                       f"欠損率 {null_pct:.1f}% > RED閾値 {red_thr}%")
    except Exception as e:
        return red("C-5", "adjusted_weight欠損率", "ERROR", str(e), detail=traceback.format_exc())


# ============================================================
# カテゴリ D: プロセス系
# ============================================================

def _run(cmd, timeout=10):
    """subprocess を実行して stdout を返す。失敗時は None"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return r.stdout
    except Exception:
        return None


def check_d1():
    """D-1: 必須プロセス稼働 — daily_scheduler.py が Python で動いているか"""
    try:
        out = _run(["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"], timeout=10)
        if out is None:
            return skip("D-1", "必須プロセス稼働", "不明", "tasklist 実行失敗")

        lines = out.strip().splitlines()
        python_pids = [l for l in lines if "python" in l.lower()]
        # WMI でコマンドライン引数を確認
        wmi_out = _run(
            ["wmic", "process", "where", "name='python.exe'", "get", "CommandLine", "/FORMAT:CSV"],
            timeout=15
        )
        scheduler_running = False
        if wmi_out:
            scheduler_running = "daily_scheduler" in wmi_out

        val = f"Python {len(python_pids)} プロセス / scheduler={'稼働' if scheduler_running else '未検知'}"
        if scheduler_running:
            return ok("D-1", "必須プロセス稼働", val, "daily_scheduler が稼働中")
        elif len(python_pids) > 0:
            return warn("D-1", "必須プロセス稼働", val,
                        "Python プロセスはあるが daily_scheduler が未検知 (スケジューラ外から手動実行中の可能性)")
        else:
            return warn("D-1", "必須プロセス稼働", val,
                        "Python プロセスなし (daily_scheduler は cron 実行のため常駐しない設計の可能性)")
    except Exception as e:
        return red("D-1", "必須プロセス稼働", "ERROR", str(e), detail=traceback.format_exc())


def check_d2():
    """D-2: 停滞プロセス検知 — 12h 以上動き続ける Python プロセスを警告"""
    try:
        # Windows: wmic process で CreationDate を取得
        out = _run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine,CreationDate", "/FORMAT:CSV"],
            timeout=15
        )
        if out is None:
            return skip("D-2", "停滞プロセス検知", "不明", "wmic 実行失敗")

        stuck = []
        now = datetime.now()
        for line in out.strip().splitlines():
            parts = line.split(",")
            # CSV: Node, CommandLine, CreationDate, ProcessId
            if len(parts) < 4:
                continue
            creation_str = parts[2].strip() if len(parts) > 2 else ""
            cmd_str = parts[1].strip()
            # WMI CreationDate: YYYYMMDDHHmmss.ffffff+offset
            if len(creation_str) >= 14 and creation_str[:8].isdigit():
                try:
                    created = datetime.strptime(creation_str[:14], "%Y%m%d%H%M%S")
                    hours = (now - created).total_seconds() / 3600
                    if hours > 12 and "boatrace" in cmd_str.lower():
                        stuck.append(f"PID={parts[-1].strip()}: {cmd_str[:60]} ({hours:.0f}h)")
                except Exception:
                    pass

        if not stuck:
            return ok("D-2", "停滞プロセス検知", "なし", "12h超の Python プロセスなし")
        else:
            return warn("D-2", "停滞プロセス検知", f"{len(stuck)}件",
                        f"12h超稼働の Python プロセス {len(stuck)} 件", detail="\n".join(stuck))
    except Exception as e:
        return red("D-2", "停滞プロセス検知", "ERROR", str(e), detail=traceback.format_exc())


def check_d3():
    """D-3: 空き RAM ≥ 2GB"""
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(mem)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        avail_gb = mem.ullAvailPhys / (1024 ** 3)
        total_gb = mem.ullTotalPhys / (1024 ** 3)
        used_pct = (total_gb - avail_gb) / total_gb * 100
        val = f"{avail_gb:.1f}GB 空き / {total_gb:.1f}GB ({used_pct:.0f}% 使用)"

        if avail_gb >= 4:
            return ok("D-3", "空きRAM", val, "余裕あり (≥4GB)")
        elif avail_gb >= 2:
            return warn("D-3", "空きRAM", val, f"2〜4GB (注意) — {used_pct:.0f}% 使用中")
        else:
            return red("D-3", "空きRAM", val, f"空き RAM {avail_gb:.1f}GB < 2GB (スケジューラ不安定リスク)")
    except Exception as e:
        return red("D-3", "空きRAM", "ERROR", str(e), detail=traceback.format_exc())


def check_d4(history):
    """D-4: DB サイズ変化 — 前回比で 1% 以上の縮小は異常"""
    try:
        db_size = DB_PATH.stat().st_size
        db_mb = db_size / (1024 ** 2)
        val = f"{db_mb:.0f} MB"

        # history から前回の db_size を取得
        prev_size = None
        for rec in reversed(history):
            if "db_size_bytes" in rec:
                prev_size = rec["db_size_bytes"]
                break

        if prev_size is None:
            return ok("D-4", "DBサイズ変化", val, "初回実行 — ベースラインなし (次回から比較)")

        change_pct = (db_size - prev_size) / prev_size * 100
        detail = f"前回={prev_size/(1024**2):.0f}MB 今回={db_mb:.0f}MB 変化={change_pct:+.2f}%"

        if change_pct < -1.0:
            return red("D-4", "DBサイズ変化", val,
                       f"DB が {abs(change_pct):.1f}% 縮小 — データ削除の可能性", detail=detail)
        elif change_pct < 0:
            return warn("D-4", "DBサイズ変化", val,
                        f"DB が {abs(change_pct):.2f}% 縮小 (<1% 許容)", detail=detail)
        else:
            return ok("D-4", "DBサイズ変化", val, detail)
    except Exception as e:
        return red("D-4", "DBサイズ変化", "ERROR", str(e), detail=traceback.format_exc())


def check_d5():
    """D-5: タスクスケジューラ状態 — BoatRace 関連タスクが有効か"""
    try:
        out = _run(
            ["schtasks", "/query", "/FO", "CSV", "/V"],
            timeout=30
        )
        if out is None:
            return skip("D-5", "タスクスケジューラ", "不明", "schtasks 実行失敗")

        lines = out.strip().splitlines()
        boatrace_tasks = []
        for line in lines:
            if "boatrace" in line.lower() or "boat_race" in line.lower() or "scheduler" in line.lower():
                boatrace_tasks.append(line[:120])

        if not boatrace_tasks:
            return warn("D-5", "タスクスケジューラ", "タスク未検知",
                        "BoatRace 関連タスクがタスクスケジューラに見つからない")

        # 無効化されていないか確認
        disabled = [t for t in boatrace_tasks if "disabled" in t.lower() or "無効" in t.lower()]
        if disabled:
            return warn("D-5", "タスクスケジューラ", f"{len(boatrace_tasks)}件",
                        f"無効化されたタスク {len(disabled)} 件", detail="\n".join(disabled))
        else:
            return ok("D-5", "タスクスケジューラ", f"{len(boatrace_tasks)}件",
                      "BoatRace タスクが登録・有効", detail=boatrace_tasks[0][:200])
    except Exception as e:
        return red("D-5", "タスクスケジューラ", "ERROR", str(e), detail=traceback.format_exc())


# ============================================================
# レポート生成 + 通知
# ============================================================

def render_md(results_list, week, bands_hash):
    """Markdown レポートを生成して返す"""
    now = now_iso()
    status_counts = {GREEN: 0, YELLOW: 0, RED: 0, SKIP: 0}
    for r in results_list:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

    overall = GREEN
    if status_counts[RED] > 0:
        overall = RED
    elif status_counts[YELLOW] > 0:
        overall = YELLOW

    emoji = {"GREEN": "OK", "YELLOW": "WARN", "RED": "RED", "SKIP": "SKIP"}
    lines = [
        f"# Invariant Watch {week}",
        f"",
        f"実行日時: {now}  ",
        f"帯域SHA256: `{bands_hash[:16]}...`  ",
        f"",
        f"## 総合判定: [{overall}] {emoji[overall]}",
        f"",
        f"| 判定 | 件数 |",
        f"|:---:|:---:|",
        f"| GREEN | {status_counts[GREEN]} |",
        f"| YELLOW | {status_counts[YELLOW]} |",
        f"| RED | {status_counts[RED]} |",
        f"| SKIP | {status_counts[SKIP]} |",
        f"",
        f"## チェック結果",
        f"",
        f"| ID | チェック名 | 判定 | 値 | メッセージ |",
        f"|:--|:--|:--:|:--|:--|",
    ]
    for r in results_list:
        st = r["status"]
        tag = {"GREEN": "[OK]", "YELLOW": "[WARN]", "RED": "[RED]", "SKIP": "[SKIP]"}[st]
        lines.append(
            f"| {r['id']} | {r['name']} | {tag} | {r['value']} | {r['message']} |"
        )

    # 詳細セクション (WARN/RED のみ)
    issues = [r for r in results_list if r["status"] in (YELLOW, RED)]
    if issues:
        lines.append("")
        lines.append("## 要確認詳細")
        for r in issues:
            lines.append(f"")
            lines.append(f"### {r['id']} {r['name']} [{r['status']}]")
            lines.append(f"**値**: {r['value']}  ")
            lines.append(f"**メッセージ**: {r['message']}  ")
            if r.get("detail"):
                lines.append(f"```")
                lines.append(str(r["detail"])[:500])
                lines.append(f"```")

    return "\n".join(lines)


def save_report(md_text, week):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{week}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_text)
    return path


def append_history(results_list, week, bands_hash):
    """history.jsonl に今週の集計を追記する"""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "week": week,
        "run_at": now_iso(),
        "db_size_bytes": DB_PATH.stat().st_size,
        "bands_hash": bands_hash,
        "summary": {
            "green": sum(1 for r in results_list if r["status"] == GREEN),
            "yellow": sum(1 for r in results_list if r["status"] == YELLOW),
            "red": sum(1 for r in results_list if r["status"] == RED),
            "skip": sum(1 for r in results_list if r["status"] == SKIP),
        },
        "results": [
            {"id": r["id"], "status": r["status"], "value": r["value"]}
            for r in results_list
        ]
    }
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def notify_red(results_list, week, dry_run):
    """RED がある場合に Discord #watch へ通知する"""
    reds = [r for r in results_list if r["status"] == RED]
    if not reds:
        return
    msg_lines = [f"[Invariant Watch] {week} - RED アラート {len(reds)} 件"]
    for r in reds:
        msg_lines.append(f"  [{r['id']}] {r['name']}: {r['message']}")
    msg = "\n".join(msg_lines)
    print()
    print(f"[RED アラート] Discord #watch へ通知:")
    print(msg)
    if dry_run:
        print("[dry-run] 実際の通知はスキップ")
        return
    try:
        import importlib.util, sys as _sys
        spec = importlib.util.spec_from_file_location("notify", str(NOTIFY_SCRIPT))
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.send_discord_notification(msg, channel="watch")
    except Exception as e:
        print(f"[WARN] Discord 通知失敗: {e}")


# ============================================================
# メイン
# ============================================================

def run_checks(category_filter, bands, history):
    """全チェックを実行してリストで返す"""
    conn = db_connect()
    results_list = []
    try:
        cat_a = [
            lambda: check_a1(conn),
            lambda: check_a2(conn),
            lambda: check_a3(conn),
            lambda: check_a4(conn),
        ]
        cat_b = [
            lambda: check_b1(conn, bands),
            lambda: check_b2(conn, bands),
            lambda: check_b3(conn, bands),
            lambda: check_b4(conn, bands),
        ]
        cat_c = [
            lambda: check_c1(conn),
            lambda: check_c2(conn),
            lambda: check_c3(conn),
            lambda: check_c4(conn),
            lambda: check_c5(conn, bands),
        ]
        cat_d = [
            lambda: check_d1(),
            lambda: check_d2(),
            lambda: check_d3(),
            lambda: check_d4(history),
            lambda: check_d5(),
        ]

        all_checks = {
            "A": cat_a, "B": cat_b, "C": cat_c, "D": cat_d
        }
        if category_filter:
            checks_to_run = all_checks.get(category_filter.upper(), [])
        else:
            checks_to_run = cat_a + cat_b + cat_c + cat_d

        for fn in checks_to_run:
            try:
                r = fn()
                results_list.append(r)
                tag = {"GREEN": "[OK]  ", "YELLOW": "[WARN]", "RED": "[RED] ", "SKIP": "[SKIP]"}
                print(f"  {tag.get(r['status'], r['status'])} {r['id']:4s} {r['name']}: {r['message']}")
            except Exception as e:
                results_list.append(red("??", "不明チェック", "EXCEPTION", str(e)))
    finally:
        conn.close()
    return results_list


def main():
    # Windows では UTF-8 出力を強制する (selftest からのインポート時は適用しない)
    if hasattr(sys.stdout, "buffer") and not isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    elif hasattr(sys.stdout, "buffer"):
        # 既存ラッパーの encoding を確認し、必要なら差し替え
        if getattr(sys.stdout, "encoding", "utf-8").lower() not in ("utf-8", "utf_8"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser(description="Invariant Watch v1")
    parser.add_argument("--category", choices=["A","B","C","D"], help="チェックカテゴリ絞り込み")
    parser.add_argument("--dry-run", action="store_true", help="Discord 通知を送らない")
    parser.add_argument("--skip-hash-check", action="store_true",
                        help="帯域ファイルのハッシュ検証をスキップ (selftest用)")
    parser.add_argument("--db", type=str, default=None,
                        help="代替 DB パス (selftest 用; 省略時は data/boatrace.db)")
    args = parser.parse_args()
    if args.db:
        global DB_PATH
        DB_PATH = Path(args.db)

    print(f"=== Invariant Watch v1  {now_iso()} ===")
    print(f"DB: {DB_PATH}")

    # 帯域ファイル読み込み
    print()
    print("[帯域] config/invariant_bands.json を読み込み中...")
    if args.skip_hash_check:
        with open(BANDS_PATH, encoding="utf-8") as f:
            bands = json.load(f)
        bands_hash = bands.get("_content_hash", "unknown")
        print(f"  [WARN] ハッシュ検証スキップ")
    else:
        try:
            bands = load_bands()
            bands_hash = bands.get("_content_hash", "unknown")
            print(f"  SHA256: {bands_hash[:16]}... OK")
        except ValueError as e:
            print(f"  [ERROR] {e}")
            sys.exit(1)

    # history 読み込み
    history = load_history()
    print(f"  history: {len(history)} 週分")

    week = week_label()
    print()
    print(f"[チェック開始] 週: {week}  カテゴリ: {args.category or '全て'}")
    print()

    results_list = run_checks(args.category, bands, history)

    # レポート生成 + 保存
    md_text = render_md(results_list, week, bands_hash)
    report_path = save_report(md_text, week)
    append_history(results_list, week, bands_hash)

    # Discord 通知 (RED のみ)
    notify_red(results_list, week, args.dry_run)

    print()
    print(f"[完了] レポート: {report_path}")
    print(f"       history: {HISTORY_PATH}")

    # サマリー
    n_red = sum(1 for r in results_list if r["status"] == RED)
    n_warn = sum(1 for r in results_list if r["status"] == YELLOW)
    n_ok   = sum(1 for r in results_list if r["status"] == GREEN)
    n_skip = sum(1 for r in results_list if r["status"] == SKIP)
    print(f"       GREEN={n_ok} YELLOW={n_warn} RED={n_red} SKIP={n_skip}")


if __name__ == "__main__":
    main()
