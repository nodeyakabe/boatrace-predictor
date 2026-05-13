"""
ボーターズ オリジナル展示データ 一括収集スクリプト

収集フィールド:
  CrawledRaceOriginalTenji → isshu_time / mawariashi_time / chikusen_time
  CrawledRaceBeforeRacer   → exhibition_time / start_tenji_time

収集期間:
  2025-10-12〜現在（OriginalTenji が正式データとして存在する期間）

DB保存ポリシー:
  2025-10-12〜2026-01-14（欠落期間）: 既存行なし → 全フィールド INSERT
  2026-01-15〜現在（既存期間）      : 既存行あり → exhibition_time / start_tenji_time のみ UPDATE
                                      既存行なし → 全フィールド INSERT

再起動耐性:
  data/collect_boaters_tenji_progress.json に処理済み race_id を記録
  中断後に再実行すると自動的に続きから再開

使い方:
  python scripts/data_collection/collect_boaters_tenji.py
  python scripts/data_collection/collect_boaters_tenji.py --start 2025-10-12 --end 2025-12-31
  python scripts/data_collection/collect_boaters_tenji.py --dry-run   # DB書き込みなし
  python scripts/data_collection/collect_boaters_tenji.py --reset     # チェックポイント削除して最初から
"""

import argparse
import io
import json
import re
import sqlite3
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

# Windows 端末の文字化け対策
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "boatrace.db"
CHECKPOINT_PATH = REPO_ROOT / "data" / "collect_boaters_tenji_progress.json"

# OriginalTenji が正式データとして存在し始めた日付
COLLECT_START = "2025-10-12"

# 既存 exhibition_data が入っている期間の開始日
# これより前は全フィールド INSERT、これ以降は exhibition_time のみ UPDATE
EXISTING_DATA_START = "2026-01-15"

REQUEST_INTERVAL = 0.35  # 秒
MAX_RETRY = 3
RETRY_WAIT = 2.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

# venue_code（ゼロ埋め2桁）→ ボーターズ slug
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
    """
    ボーターズから展示データを取得。

    戻り値: {pit_number_str: {isshu_time, mawariashi_time, chikusen_time,
                               exhibition_time, start_tenji_time}}
    データが取れない場合は None。
    """
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

    # CrawledRaceOriginalTenji → isshu / mawari / chokusen
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

    # CrawledRaceBeforeRacer → tenji / start_tenji
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
# DB 操作
# ---------------------------------------------------------------------------

def ensure_column(conn: sqlite3.Connection) -> None:
    """start_tenji_time カラムが存在しない場合に追加する"""
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(exhibition_data)")
    cols = {row[1] for row in cur.fetchall()}
    if "start_tenji_time" not in cols:
        cur.execute("ALTER TABLE exhibition_data ADD COLUMN start_tenji_time REAL")
        conn.commit()


def load_candidates(conn: sqlite3.Connection, start: str, end: str) -> list[tuple]:
    """
    races テーブルから収集候補を取得。
    venue_code を 2 桁ゼロ埋めに統一して返す。
    戻り値: [(race_id, venue_code, race_date, race_number), ...]
    """
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
        (start, end),
    )
    return cur.fetchall()


def save_to_db(
    conn: sqlite3.Connection,
    race_id: int,
    boat_data: dict,
    full_insert: bool,
    dry_run: bool,
) -> tuple[int, int]:
    """
    boat_data を exhibition_data に保存。

    full_insert=True  → 全フィールド UPSERT
    full_insert=False → exhibition_time / start_tenji_time のみ UPDATE
                        行が存在しない場合は全フィールド INSERT

    戻り値: (inserted件数, updated件数)
    """
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
                # 全フィールド上書き
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
                # exhibition_time / start_tenji_time のみ
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
            # 行なし → 常に全フィールド INSERT
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
        json.dumps({"done_race_ids": sorted(done), "updated_at": datetime.now().isoformat()},
                   ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ボーターズ展示データ一括収集")
    parser.add_argument("--start", default=COLLECT_START, help="収集開始日 YYYY-MM-DD")
    parser.add_argument("--end",   default=str(date.today()), help="収集終了日 YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="DB書き込みなし（動作確認）")
    parser.add_argument("--reset",   action="store_true", help="チェックポイントを削除して最初から")
    parser.add_argument("--interval", type=float, default=REQUEST_INTERVAL,
                        help=f"リクエスト間隔秒（default={REQUEST_INTERVAL}）")
    args = parser.parse_args()

    if args.reset and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print("[INFO] チェックポイントを削除しました")

    print(f"[INFO] 収集期間: {args.start} 〜 {args.end}")
    print(f"[INFO] DB: {DB_PATH}")
    if args.dry_run:
        print("[INFO] DRY-RUN モード（DB書き込みなし）")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_column(conn)

    candidates = load_candidates(conn, args.start, args.end)
    print(f"[INFO] 対象レース: {len(candidates):,} 件")

    done = load_checkpoint()
    print(f"[INFO] 処理済み（チェックポイント）: {len(done):,} 件")

    total = len(candidates)
    ok = skip_no_slug = skip_no_data = skip_done = 0
    ins_total = upd_total = 0
    consec_err = 0
    MAX_CONSEC_ERR = 30

    start_ts = time.time()

    for idx, (race_id, vc, race_date, race_num) in enumerate(candidates, 1):
        # チェックポイントでスキップ
        if race_id in done:
            skip_done += 1
            continue

        # スラッグが存在しない会場はスキップ
        slug = VENUE_SLUG.get(vc)
        if slug is None:
            skip_no_slug += 1
            done.add(race_id)
            continue

        # 期間判定
        full_insert = race_date < EXISTING_DATA_START

        # スクレイピング
        boat_data = fetch_tenji(slug, race_date, race_num)
        time.sleep(args.interval)

        if boat_data is None:
            skip_no_data += 1
            consec_err += 1
            done.add(race_id)
            if consec_err >= MAX_CONSEC_ERR:
                print(f"\n[ABORT] 連続エラー {MAX_CONSEC_ERR} 件超過。ネットワーク確認後に再実行してください。")
                break
            continue

        consec_err = 0

        # DB保存
        ins, upd = save_to_db(conn, race_id, boat_data, full_insert, args.dry_run)
        ins_total += ins
        upd_total += upd
        ok += 1
        done.add(race_id)

        # チェックポイント保存（100件ごと）
        if ok % 100 == 0:
            save_checkpoint(done)

        # 進捗表示（50件ごと）
        if (idx - skip_done) % 50 == 1 or idx == total:
            elapsed = time.time() - start_ts
            remaining = total - idx
            rate = ok / elapsed if elapsed > 0 else 0
            eta = remaining / rate if rate > 0 else 0
            print(
                f"[{idx:>6}/{total}] {race_date} {slug:12} {race_num:2}R "
                f"| 取得OK={ok} データなし={skip_no_data} "
                f"| ins={ins_total} upd={upd_total} "
                f"| ETA={eta/60:.1f}min",
                flush=True,
            )

    # 最終チェックポイント保存
    save_checkpoint(done)
    conn.close()

    elapsed = time.time() - start_ts
    print()
    print("=" * 60)
    print(f"[完了] 経過時間: {elapsed/60:.1f} 分")
    print(f"  処理済み（スキップ含む）: {len(done):,}")
    print(f"  取得成功:   {ok:,}")
    print(f"  データなし: {skip_no_data:,}")
    print(f"  スラッグなし: {skip_no_slug:,}")
    print(f"  INSERT: {ins_total:,}  UPDATE: {upd_total:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
