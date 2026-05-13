"""
ボーターズ オリジナル展示データ 並列収集スクリプト

collect_boaters_tenji.py の高速版。ThreadPoolExecutor による並列HTTP取得で
シングルスレッド版比 6〜8倍高速（14時間 → 2時間程度）。

チェックポイントは collect_boaters_tenji.py と同じファイルを共有するため
どちらで中断しても続きから再開できる。

使い方:
  python scripts/data_collection/collect_boaters_tenji_parallel.py
  python scripts/data_collection/collect_boaters_tenji_parallel.py --workers 6
  python scripts/data_collection/collect_boaters_tenji_parallel.py --start 2025-10-12 --end 2025-12-31
  python scripts/data_collection/collect_boaters_tenji_parallel.py --dry-run
  python scripts/data_collection/collect_boaters_tenji_parallel.py --reset
"""

import argparse
import io
import json
import re
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

import requests

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "boatrace.db"
CHECKPOINT_PATH = REPO_ROOT / "data" / "collect_boaters_tenji_progress.json"

COLLECT_START = "2025-10-12"
EXISTING_DATA_START = "2026-01-15"

REQUEST_INTERVAL = 0.35
MAX_RETRY = 3
RETRY_WAIT = 2.0
DEFAULT_WORKERS = 6

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

VENUE_SLUG = {
    "01": "kiryu",       "02": "toda",        "03": "edogawa",
    "04": "heiwajima",   "05": "tamagawa",     "06": "hamanako",
    "07": "gamagori",    "08": "tokoname",     "09": "tsu",
    "10": "mikuni",      "12": "suminoe",      "13": "amagasaki",
    "14": "naruto",      "15": "marugame",     "16": "kojima",
    "17": "miyajima",    "18": "tokuyama",     "19": "shimonoseki",
    "20": "wakamatsu",   "21": "ashiya",       "22": "fukuoka",
    "23": "karatsu",     "24": "omura",
}


# ---------------------------------------------------------------------------
# スクレイピング
# ---------------------------------------------------------------------------

def _parse_next_data(html: str) -> dict | None:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["initialApolloState"]
    except (json.JSONDecodeError, KeyError):
        return None


def fetch_tenji(slug: str, date_str: str, race_num: int) -> dict | None:
    url = (
        f"https://boaters-boatrace.com/race/{slug}/{date_str}/{race_num}R"
        f"/last-minute?last-minute-content=original-tenji"
    )
    for attempt in range(MAX_RETRY):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 404:
                return None
            if r.status_code != 200:
                if attempt < MAX_RETRY - 1:
                    time.sleep(RETRY_WAIT)
                    continue
                return None
            break
        except requests.RequestException:
            if attempt < MAX_RETRY - 1:
                time.sleep(RETRY_WAIT)
                continue
            return None

    state = _parse_next_data(r.text)
    if state is None:
        return None

    result: dict[str, dict] = {}

    for k, v in state.items():
        if k.startswith("CrawledRaceOriginalTenji:") and isinstance(v, dict):
            bn = str(v.get("boatNumber", ""))
            if not bn:
                continue
            result.setdefault(bn, {}).update({
                "isshu_time":      v.get("isshuTime"),
                "mawariashi_time": v.get("mawariashiTime"),
                "chikusen_time":   v.get("chokusenTime"),
            })

    for k, v in state.items():
        if k.startswith("CrawledRaceBeforeRacer:") and isinstance(v, dict):
            bn = str(v.get("boatNumber", ""))
            if not bn:
                continue
            result.setdefault(bn, {}).update({
                "exhibition_time":  v.get("tenjiTime"),
                "start_tenji_time": v.get("startTenjiTime"),
            })

    return result if result else None


# ---------------------------------------------------------------------------
# DB 操作（スレッドごとに個別接続を使う）
# ---------------------------------------------------------------------------

def save_to_db(
    conn: sqlite3.Connection,
    race_id: int,
    boat_data: dict,
    full_insert: bool,
    dry_run: bool,
) -> tuple[int, int]:
    if dry_run:
        return 0, 0

    cur = conn.cursor()
    inserted = updated = 0

    for bn, data in boat_data.items():
        try:
            pit = int(bn)
        except ValueError:
            continue

        cur.execute(
            "SELECT id FROM exhibition_data WHERE race_id=? AND pit_number=?",
            (race_id, pit),
        )
        existing = cur.fetchone()

        if existing:
            if full_insert:
                cur.execute(
                    """
                    UPDATE exhibition_data SET
                        isshu_time      = ?,
                        mawariashi_time = ?,
                        chikusen_time   = ?,
                        exhibition_time = ?,
                        start_tenji_time = ?,
                        data_source     = 'boaters',
                        collected_at    = datetime('now','localtime')
                    WHERE race_id=? AND pit_number=?
                    """,
                    (
                        data.get("isshu_time"),
                        data.get("mawariashi_time"),
                        data.get("chikusen_time"),
                        data.get("exhibition_time"),
                        data.get("start_tenji_time"),
                        race_id, pit,
                    ),
                )
            else:
                cur.execute(
                    """
                    UPDATE exhibition_data SET
                        exhibition_time  = ?,
                        start_tenji_time = ?,
                        collected_at     = datetime('now','localtime')
                    WHERE race_id=? AND pit_number=?
                    """,
                    (
                        data.get("exhibition_time"),
                        data.get("start_tenji_time"),
                        race_id, pit,
                    ),
                )
            updated += 1
        else:
            cur.execute(
                """
                INSERT INTO exhibition_data
                    (race_id, pit_number,
                     isshu_time, mawariashi_time, chikusen_time,
                     exhibition_time, start_tenji_time,
                     data_source, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'boaters', datetime('now','localtime'))
                """,
                (
                    race_id, pit,
                    data.get("isshu_time"),
                    data.get("mawariashi_time"),
                    data.get("chikusen_time"),
                    data.get("exhibition_time"),
                    data.get("start_tenji_time"),
                ),
            )
            inserted += 1

    conn.commit()
    return inserted, updated


# ---------------------------------------------------------------------------
# チェックポイント
# ---------------------------------------------------------------------------

def load_checkpoint() -> set[int]:
    if not CHECKPOINT_PATH.exists():
        return set()
    try:
        data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
        return set(data.get("done_race_ids", []))
    except Exception:
        return set()


def save_checkpoint(done: set[int]) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(
            {"done_race_ids": sorted(done), "updated_at": datetime.now().isoformat()},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# ワーカー関数
# ---------------------------------------------------------------------------

def process_race(
    race_id: int,
    vc: str,
    race_date: str,
    race_num: int,
    interval: float,
    dry_run: bool,
) -> dict:
    """1レース分の取得＋DB保存。スレッド内で実行される。"""
    slug = VENUE_SLUG.get(vc)
    if slug is None:
        return {"status": "no_slug", "race_id": race_id}

    full_insert = race_date < EXISTING_DATA_START

    boat_data = fetch_tenji(slug, race_date, race_num)
    time.sleep(interval)

    if boat_data is None:
        return {"status": "no_data", "race_id": race_id}

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        ins, upd = save_to_db(conn, race_id, boat_data, full_insert, dry_run)
    finally:
        conn.close()

    return {"status": "ok", "race_id": race_id, "ins": ins, "upd": upd}


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ボーターズ展示データ並列収集")
    parser.add_argument("--start",   default=COLLECT_START,      help="収集開始日 YYYY-MM-DD")
    parser.add_argument("--end",     default=str(date.today()),  help="収集終了日 YYYY-MM-DD")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"並列ワーカー数（default={DEFAULT_WORKERS}）")
    parser.add_argument("--dry-run", action="store_true", help="DB書き込みなし")
    parser.add_argument("--reset",   action="store_true", help="チェックポイント削除して最初から")
    parser.add_argument("--interval", type=float, default=REQUEST_INTERVAL,
                        help=f"ワーカーごとのリクエスト間隔秒（default={REQUEST_INTERVAL}）")
    args = parser.parse_args()

    if args.reset and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print("[INFO] チェックポイントを削除しました")

    print(f"[INFO] 収集期間: {args.start} 〜 {args.end}")
    print(f"[INFO] DB: {DB_PATH}")
    print(f"[INFO] 並列ワーカー数: {args.workers}")
    if args.dry_run:
        print("[INFO] DRY-RUN モード（DB書き込みなし）")

    # 候補取得
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id,
               PRINTF('%02d', CAST(venue_code AS INTEGER)) AS vc,
               race_date,
               race_number
        FROM races
        WHERE race_date BETWEEN ? AND ?
        ORDER BY race_date, vc, race_number
        """,
        (args.start, args.end),
    )
    candidates = cur.fetchall()
    conn.close()
    print(f"[INFO] 対象レース: {len(candidates):,} 件")

    done = load_checkpoint()
    print(f"[INFO] 処理済み（チェックポイント）: {len(done):,} 件")

    # 未処理だけに絞る
    pending = [(rid, vc, rd, rn) for rid, vc, rd, rn in candidates if rid not in done]
    print(f"[INFO] 未処理: {len(pending):,} 件")

    if not pending:
        print("[INFO] 全件処理済みです")
        return

    total = len(pending)
    lock = threading.Lock()
    ok = no_data = no_slug = 0
    ins_total = upd_total = 0
    processed = 0
    consec_err = 0
    MAX_CONSEC_ERR = 30
    abort = False

    start_ts = time.time()

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_race, rid, vc, rd, rn, args.interval, args.dry_run
            ): (rid, vc, rd, rn)
            for rid, vc, rd, rn in pending
        }

        for future in as_completed(futures):
            if abort:
                future.cancel()
                continue

            rid, vc, rd, rn = futures[future]
            try:
                result = future.result()
            except Exception as e:
                result = {"status": "error", "race_id": rid}

            with lock:
                processed += 1
                status = result.get("status")

                if status == "ok":
                    ok += 1
                    ins_total += result.get("ins", 0)
                    upd_total += result.get("upd", 0)
                    consec_err = 0
                elif status == "no_data":
                    no_data += 1
                    consec_err += 1
                elif status == "no_slug":
                    no_slug += 1
                else:
                    consec_err += 1

                done.add(rid)

                # チェックポイント保存（100件ごと）
                if ok > 0 and ok % 100 == 0:
                    save_checkpoint(done)

                # 連続エラーチェック
                if consec_err >= MAX_CONSEC_ERR:
                    abort = True

                # 進捗表示（100件ごと）
                if processed % 100 == 0 or processed == total:
                    elapsed = time.time() - start_ts
                    rate = ok / elapsed if elapsed > 0 else 0
                    remaining = total - processed
                    eta = remaining / rate if rate > 0 else 0
                    print(
                        f"[{processed:>6}/{total}] {rd} {VENUE_SLUG.get(vc, vc):12} {rn:2}R "
                        f"| 取得OK={ok} データなし={no_data} "
                        f"| ins={ins_total} upd={upd_total} "
                        f"| ETA={eta/60:.1f}min ({args.workers}並列)",
                        flush=True,
                    )

    if abort:
        print(f"\n[ABORT] 連続エラー {MAX_CONSEC_ERR} 件超過。ネットワーク確認後に再実行してください。")

    save_checkpoint(done)

    elapsed = time.time() - start_ts
    print()
    print("=" * 60)
    print(f"[完了] 経過時間: {elapsed/60:.1f} 分")
    print(f"  処理済み（スキップ含む）: {len(done):,}")
    print(f"  取得成功:   {ok:,}")
    print(f"  データなし: {no_data:,}")
    print(f"  スラッグなし: {no_slug:,}")
    print(f"  INSERT: {ins_total:,}  UPDATE: {upd_total:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
