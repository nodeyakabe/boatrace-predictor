#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
invariant_watch_selftest.py -- Invariant Watch v1 Phase 3
破壊テスト: 各不変条件チェックが「壊れた状態」を正しく検知できるか確認する。

実行方法:
    python scripts/monitoring/invariant_watch_selftest.py

出力:
    reports/invariant_watch/invariant_watch_selftest.md

判定基準:
    全5テストが DETECTED (YELLOW or RED) = Phase 3 合格
    1件でも NOT_DETECTED = 合格失敗 → 問題のあるチェックを修正してから再実行

注意:
    - 本スクリプトは一時ファイル (temp SQLite) に書き込むが、
      本番 DB (data/boatrace.db) には一切書き込まない
    - 本スクリプト実行後に「運用開始」を宣言してよい
"""

import sys
import io
# Windows で UTF-8 出力を強制
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import json
import sqlite3
import tempfile
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
BANDS_PATH   = PROJECT_ROOT / "config" / "invariant_bands.json"
REPORTS_DIR  = PROJECT_ROOT / "reports" / "invariant_watch"

# invariant_watch の check 関数をインポート
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "monitoring"))
import importlib.util
spec = importlib.util.spec_from_file_location(
    "invariant_watch",
    str(PROJECT_ROOT / "scripts" / "monitoring" / "invariant_watch.py")
)
iw_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iw_mod)

GREEN  = "GREEN"
YELLOW = "YELLOW"
RED    = "RED"
SKIP   = "SKIP"

DETECTED     = "DETECTED"
NOT_DETECTED = "NOT_DETECTED"
ERROR_TEST   = "ERROR"


def load_bands():
    with open(BANDS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# テスト用 DB ヘルパー
# ============================================================

def make_empty_db():
    """共通テーブルを持つ空の SQLite DB を一時ファイルに作成して返す"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    conn = sqlite3.connect(tmp.name)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE races (
            id INTEGER PRIMARY KEY, race_date TEXT, venue_code TEXT,
            race_number INTEGER, created_at TEXT
        );
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY, race_id INTEGER, pit_number INTEGER,
            racer_number TEXT, racer_name TEXT, racer_rank TEXT,
            created_at TEXT
        );
        CREATE TABLE results (
            id INTEGER PRIMARY KEY, race_id INTEGER, pit_number INTEGER,
            rank TEXT, created_at TEXT
        );
        CREATE TABLE race_details (
            id INTEGER PRIMARY KEY, race_id INTEGER, pit_number INTEGER,
            adjusted_weight REAL, exhibition_time REAL, created_at TEXT
        );
        CREATE TABLE race_predictions (
            id INTEGER PRIMARY KEY, race_id INTEGER, pit_number INTEGER,
            rank_prediction INTEGER, total_score REAL, confidence TEXT,
            prediction_type TEXT, generated_at TEXT, created_at TEXT
        );
        CREATE TABLE bet_notifications (
            id INTEGER PRIMARY KEY, race_id INTEGER, combinations TEXT,
            odds_at_notification REAL, bet_amount INTEGER,
            condition_id TEXT, notified_at TEXT, notification_type TEXT,
            had_exhibition INTEGER, pred_type_used TEXT, is_hit INTEGER,
            actual_payout REAL
        );
        CREATE TABLE shadow_bets (
            id INTEGER PRIMARY KEY, race_id INTEGER, combinations TEXT,
            notification_type TEXT, created_at TEXT
        );
    """)
    conn.commit()
    return conn, tmp.name


def _insert_race(conn, race_id, race_date, venue_code="01"):
    conn.execute(
        "INSERT INTO races VALUES (?,?,?,1,?)",
        (race_id, race_date, venue_code, f"{race_date}T10:00:00")
    )


def _insert_pred(conn, race_id, rank, score=90.0, conf="A", ptype="before", dt=None):
    dt = dt or f"{date.today().isoformat()}T10:00:00"
    conn.execute(
        "INSERT INTO race_predictions(race_id,pit_number,rank_prediction,total_score,confidence,"
        "prediction_type,generated_at,created_at) VALUES (?,?,?,?,?,?,?,?)",
        (race_id, rank, rank, score, conf, ptype, dt, dt)
    )


def _insert_bet(conn, race_id, ntype="confirmed", pred_used="before", had_ex=1, dt=None):
    dt = dt or f"{date.today().isoformat()}T12:00:00"
    conn.execute(
        "INSERT INTO bet_notifications(race_id,combinations,odds_at_notification,bet_amount,"
        "condition_id,notified_at,notification_type,had_exhibition,pred_type_used)"
        " VALUES (?,?,50,100,'COND_A',?,?,?,?)",
        (race_id, "1-2-3", dt, ntype, had_ex, pred_used)
    )


def _insert_shadow(conn, race_id, ntype="confirmed", dt=None):
    dt = dt or f"{date.today().isoformat()}T12:00:00"
    conn.execute(
        "INSERT INTO shadow_bets(race_id,combinations,notification_type,created_at) VALUES (?,?,?,?)",
        (race_id, "1-2-3", ntype, dt)
    )


# ============================================================
# 破壊テスト 5 件
# ============================================================

def test_1_bands_tamper():
    """
    テスト1: 帯域ファイル改ざん検知
    - invariant_bands.json のハッシュを壊す
    - load_bands() が ValueError を raise するはず
    """
    print("[TEST-1] 帯域ファイル改ざん検知...")
    try:
        # 帯域ファイルをコピーして改ざん
        import copy
        with open(BANDS_PATH, encoding="utf-8") as f:
            orig = json.load(f)

        tampered = copy.deepcopy(orig)
        tampered["b4_hit_rate"]["baseline_pct"] = 99.99  # 値を変える

        # 一時ファイルに書き出し、load_bands を差し替えて呼ぶ
        import tempfile as _tf
        with _tf.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(tampered, tf, ensure_ascii=False)
            tf_path = tf.name

        # 差し替えて検証
        orig_path = iw_mod.BANDS_PATH
        iw_mod.BANDS_PATH = Path(tf_path)
        try:
            iw_mod.load_bands()
            detected = False  # 例外が出なかった = 未検知
        except ValueError:
            detected = True
        finally:
            iw_mod.BANDS_PATH = orig_path
            Path(tf_path).unlink(missing_ok=True)

        return detected, "ValueError (ハッシュ不一致)" if detected else "例外なし"
    except Exception as e:
        return False, f"テスト実行エラー: {e}"


def test_2_a4_no_before_prediction():
    """
    テスト2: A-4 — before 予測なし確定購入の検知
    - 確定購入があるが before 予測が存在しない → A-4 が RED のはず
    """
    print("[TEST-2] A-4 before予測なし購入検知...")
    conn, db_path = make_empty_db()
    try:
        today = date.today().isoformat()
        dt_recent = f"{today}T12:00:00"
        _insert_race(conn, 1, today)
        # before 予測なしで確定購入を入れる
        _insert_bet(conn, 1, ntype="confirmed", pred_used="before", had_ex=1, dt=dt_recent)
        _insert_shadow(conn, 1, ntype="confirmed", dt=dt_recent)
        conn.commit()

        r = iw_mod.check_a4(conn)
        detected = r["status"] == RED
        return detected, f"status={r['status']} value={r['value']}"
    except Exception as e:
        return False, f"テスト実行エラー: {traceback.format_exc()}"
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


def test_3_c3_advance_fallback():
    """
    テスト3: C-3 — advance フォールバック購入の検知
    - pred_type_used='advance' の確定購入 → C-3 が RED のはず
    """
    print("[TEST-3] C-3 advanceフォールバック検知...")
    conn, db_path = make_empty_db()
    try:
        today = date.today().isoformat()
        dt_recent = f"{today}T12:00:00"
        _insert_race(conn, 1, today)
        _insert_pred(conn, 1, 1, ptype="advance", dt=dt_recent)
        # pred_type_used = 'advance' で確定購入
        _insert_bet(conn, 1, ntype="confirmed", pred_used="advance", had_ex=1, dt=dt_recent)
        conn.commit()

        r = iw_mod.check_c3(conn)
        detected = r["status"] == RED
        return detected, f"status={r['status']} value={r['value']}"
    except Exception as e:
        return False, f"テスト実行エラー: {traceback.format_exc()}"
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


def test_4_d4_db_shrink():
    """
    テスト4: D-4 — DB サイズ縮小の検知
    - history.jsonl に巨大な前回 DB サイズを書き込み
    - D-4 が RED を返すはず
    """
    print("[TEST-4] D-4 DBサイズ縮小検知...")
    # history として「前回が 100GB だった」と偽装
    fake_history = [{
        "week": "2026-W31",
        "db_size_bytes": 100 * 1024 * 1024 * 1024,  # 100GB (現在の DB より大きい)
    }]
    try:
        r = iw_mod.check_d4(fake_history)
        detected = r["status"] == RED
        return detected, f"status={r['status']} value={r['value']}"
    except Exception as e:
        return False, f"テスト実行エラー: {traceback.format_exc()}"


def test_6_b1_zero_week_detected():
    """
    テスト6: B-1 — 0件週（完全停止週）の検知
    修正前の SQL（GROUP BY のみ）では0件週が行ごと消えて検知されなかった。
    修正後は cnt=0 として補完し、floor_breach（< abs_lo=4）で RED になることを確認。
    """
    print("[TEST-6] B-1 0件週（完全停止週）検知...")
    conn, db_path = make_empty_db()
    try:
        bands = load_bands()
        today = date.today()

        # 直近4週のうち「1週前（先週）」だけ bet なし（停止週）
        # 今週・2週前・3週前には 5件ずつ挿入（abs_lo=4 を超えておく）
        for week_offset in [0, 2, 3]:
            monday = today - timedelta(days=today.weekday() + 7 * week_offset)
            for j in range(5):
                race_id = week_offset * 10 + j + 1
                race_dt = f"{monday.isoformat()}T{10 + j:02d}:00:00"
                _insert_race(conn, race_id, monday.isoformat())
                _insert_bet(conn, race_id, ntype="confirmed", dt=race_dt)
        conn.commit()

        r = iw_mod.check_b1(conn, bands)

        # 0件週が detail に含まれることを確認（例: "2026-W33:0" のような形式）
        detail_str = r.get("detail", "")
        zero_week_in_detail = ":0" in detail_str

        # floor_breach で RED になるはず（0件週が abs_lo=4 未満）
        is_red = r["status"] == RED

        detected = zero_week_in_detail and is_red
        return detected, (
            f"status={r['status']} detail=[{detail_str}] "
            f"(0件週補完={zero_week_in_detail} RED={is_red})"
        )
    except Exception as e:
        return False, f"テスト実行エラー: {traceback.format_exc()}"
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


def test_5_b2_score_drift():
    """
    テスト5: B-2 — スコア分布ドリフトの検知
    - 直近28日の予測スコアが全て異常に低い (P50 < IS基準 - 20pt)
    - B-2 が RED を返すはず
    """
    print("[TEST-5] B-2 スコア分布ドリフト検知...")
    conn, db_path = make_empty_db()
    try:
        bands = load_bands()
        base_p50 = bands["b2_score_distribution"]["p50"]   # 88.5
        cutoff = (date.today() - timedelta(days=20)).isoformat()

        # 直近20日間、各日にスコア = 50.0 (ベースライン P50 より 38pt 低い) の予測を200件挿入
        for i in range(200):
            rdate = (date.today() - timedelta(days=i % 20)).isoformat()
            _insert_race(conn, i + 1, rdate)
            _insert_pred(conn, i + 1, 1, score=50.0, ptype="before",
                         dt=f"{rdate}T10:00:00")
        conn.commit()

        r = iw_mod.check_b2(conn, bands)
        detected = r["status"] in (YELLOW, RED)
        return detected, f"status={r['status']} value={r['value']}"
    except Exception as e:
        return False, f"テスト実行エラー: {traceback.format_exc()}"
    finally:
        conn.close()
        Path(db_path).unlink(missing_ok=True)


# ============================================================
# レポート生成
# ============================================================

def render_selftest_report(test_results):
    now = datetime.now().isoformat(timespec="seconds")
    pass_cnt = sum(1 for _, detected, _ in test_results if detected)
    total = len(test_results)
    overall = "合格" if pass_cnt == total else f"不合格 ({total - pass_cnt} 件 NOT_DETECTED)"

    lines = [
        f"# Invariant Watch v1 — Phase 3 セルフテスト",
        f"",
        f"実行日時: {now}",
        f"",
        f"## 総合結果: {overall}  ({pass_cnt}/{total} 検知)",
        f"",
        f"| テスト | チェック対象 | 破壊内容 | 判定 |",
        f"|:------|:------------|:--------|:----:|",
    ]
    test_names = [
        ("TEST-1", "帯域ファイル改ざん検知", "b4_hit_rate を 99.99% に改ざん"),
        ("TEST-2", "A-4 before予測なし購入", "before 予測なしで確定購入を挿入"),
        ("TEST-3", "C-3 advanceフォールバック", "pred_type_used='advance' で確定購入"),
        ("TEST-4", "D-4 DBサイズ縮小", "前回 DB サイズを 100GB に偽装"),
        ("TEST-5", "B-2 スコア分布ドリフト", "全予測スコアを 50.0 (ベースライン-38pt) に設定"),
        ("TEST-6", "B-1 0件週（完全停止週）補完", "先週 bet を0件にして 0件週が補完・RED 検知されることを確認"),
    ]
    for (tid, tname, tbr), (_, detected, detail) in zip(test_names, test_results):
        verdict = "DETECTED" if detected else "NOT_DETECTED"
        lines.append(f"| {tid} | {tname} | {tbr} | {verdict} |")

    lines.append("")
    lines.append("## 詳細")
    for (tid, tname, tbr), (_, detected, detail) in zip(test_names, test_results):
        verdict = "DETECTED" if detected else "NOT_DETECTED"
        lines.append(f"")
        lines.append(f"### {tid} {tname} — {verdict}")
        lines.append(f"- 破壊内容: {tbr}")
        lines.append(f"- 結果: `{detail}`")

    if pass_cnt == total:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**全テスト合格。Phase 3 完了。Phase 4 (タスクスケジューラ登録) に進んでよい。**")
    else:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**NOT_DETECTED のテストがあります。対応するチェック関数を修正してから再実行してください。**")

    return "\n".join(lines)


def main():
    print("=== Invariant Watch v1 - Phase 3 セルフテスト ===")
    print()

    tests = [
        ("TEST-1", test_1_bands_tamper),
        ("TEST-2", test_2_a4_no_before_prediction),
        ("TEST-3", test_3_c3_advance_fallback),
        ("TEST-4", test_4_d4_db_shrink),
        ("TEST-5", test_5_b2_score_drift),
        ("TEST-6", test_6_b1_zero_week_detected),
    ]

    test_results = []
    for tid, fn in tests:
        try:
            detected, detail = fn()
            verdict = DETECTED if detected else NOT_DETECTED
            symbol = "[PASS]" if detected else "[FAIL]"
            print(f"  {symbol} {tid}: {verdict} — {detail}")
            test_results.append((tid, detected, detail))
        except Exception as e:
            print(f"  [ERROR] {tid}: {e}")
            test_results.append((tid, False, f"例外: {e}"))

    pass_cnt = sum(1 for _, d, _ in test_results if d)
    total = len(test_results)
    print()
    print(f"結果: {pass_cnt}/{total} 検知")

    # レポート保存
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "invariant_watch_selftest.md"
    md = render_selftest_report(test_results)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"レポート: {report_path}")

    if pass_cnt == total:
        print()
        print("Phase 3 合格。Phase 4 (タスクスケジューラ登録) に進んでよい。")
    else:
        print()
        print("Phase 3 不合格。NOT_DETECTED のチェックを修正してから再実行してください。")
        sys.exit(1)


if __name__ == "__main__":
    main()
