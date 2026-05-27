"""
ボーターズ レースデータ収集スクリプト
λモデル逆算用のサンプルデータを収集する

収集ページ（レースごと）:
  /data        → racerAiProba（λ確率・予測ターゲット）, tenkaiYosous, winMethodAggregations
  /motor       → motorAggregations（モーター品質特徴量）
  /race-prediction → aiBets, aiMarks, manshuRatePercent（検証・活用）

出力先: data/boaters_race_data/{YYYY}/{race_id}.json
チェックポイント: data/collect_boaters_race_data_progress.json

使い方:
  python scripts/data_collection/collect_boaters_race_data.py
  python scripts/data_collection/collect_boaters_race_data.py --start 2023-02-12 --end 2023-12-31
  python scripts/data_collection/collect_boaters_race_data.py --dry-run
  python scripts/data_collection/collect_boaters_race_data.py --reset
  python scripts/data_collection/collect_boaters_race_data.py --sample 500
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
OUT_DIR = REPO_ROOT / "data" / "boaters_race_data"
CHECKPOINT_PATH = REPO_ROOT / "data" / "collect_boaters_race_data_progress.json"

# aiBets が存在し始めた日付
COLLECT_START_DEFAULT = "2023-02-12"

REQUEST_INTERVAL = 0.4   # 秒（ワーカーごと）
PAGE_INTERVAL    = 0.25  # 同一レース内のページ間隔
MAX_RETRY = 3
RETRY_WAIT = 2.0
WORKERS = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

VENUE_SLUG = {
    "01": "kiryu",    "02": "toda",      "03": "edogawa",
    "04": "heiwajima","05": "tamagawa",  "06": "hamanako",
    "07": "gamagori", "08": "tokoname",  "09": "tsu",
    "10": "mikuni",   "12": "suminoe",   "13": "amagasaki",
    "14": "naruto",   "15": "marugame",  "16": "kojima",
    "17": "miyajima", "18": "tokuyama",  "19": "shimonoseki",
    "20": "wakamatsu","21": "ashiya",    "22": "fukuoka",
    "23": "karatsu",  "24": "omura",
}


# ---------------------------------------------------------------------------
# スクレイピング
# ---------------------------------------------------------------------------

def _fetch(url: str) -> str | None:
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
            return r.text
        except requests.RequestException:
            if attempt < MAX_RETRY - 1:
                time.sleep(RETRY_WAIT)
                continue
            return None


def _parse_apollo(html: str) -> dict | None:
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


def _get_target_race(apollo: dict, round_num: int) -> dict | None:
    """指定ラウンドのCrawledRaceエントリを返す"""
    for k, v in apollo.items():
        if (k.startswith("CrawledRace:")
                and not any(x in k for x in ["Racer", "Day", "BeforeRacer", "BeforeInfo"])
                and isinstance(v, dict)
                and v.get("round") == round_num):
            return v
    return None


def _is_redirect_to_today(apollo: dict) -> bool:
    """ページが今日のデータにリダイレクトされているか検出"""
    today = date.today().strftime("%Y-%m-%d")
    race_keys = [k for k in apollo if k.startswith("CrawledRace:")
                 and not any(x in k for x in ["Racer","Day","BeforeRacer","BeforeInfo"])]
    for rk in race_keys[:5]:
        rid = apollo.get(rk, {}).get("raceId", "")
        if rid and today in rid:
            return True
    return False


def fetch_data_page(slug: str, date_str: str, round_num: int) -> dict | None:
    """
    /data ページから取得:
      - racerAiProba1-6 (λ確率・ターゲット)
      - tenkaiYosous (展開予想)
      - winMethodAggregations (決まり手集計)
    """
    url = f"https://boaters-boatrace.com/race/{slug}/{date_str}/{round_num}R/data"
    html = _fetch(url)
    if not html:
        return None
    apollo = _parse_apollo(html)
    if not apollo or _is_redirect_to_today(apollo):
        return None

    rc = _get_target_race(apollo, round_num)
    if not rc:
        return None

    result = {}

    # racerOddsProba → λ確率・市場確率
    rop = rc.get("racerOddsProba")
    if rop and isinstance(rop, dict):
        result["racer_ai_proba"] = {
            str(i): rop.get(f"racerAiProba{i}") for i in range(1, 7)
        }
        result["racer_odds_proba"] = {
            str(i): rop.get(f"racerOddsProba{i}") for i in range(1, 7)
        }

    # tenkaiYosous
    ty = rc.get("tenkaiYosous") or []
    if ty:
        result["tenkai_yosous"] = [
            {"boat": t.get("boatNo"), "proba": t.get("proba"), "win_method": t.get("winMethod")}
            for t in ty if isinstance(t, dict)
        ]

    # winMethodAggregations
    wm_key = next((k for k in rc if "winMethodAggregations" in k), None)
    if wm_key:
        wma = rc.get(wm_key) or []
        result["win_method_aggregations"] = [
            {
                "racer_reg_n": w.get("racerRegN"),
                "waku": w.get("waku"),
                "shinnyu": w.get("shinnyu"),
                "range": w.get("aggregationRange"),
                "race_count": w.get("raceCountWithWaku"),
                "nige_rate": w.get("nigeRate"),
                "sashi_rate": w.get("sashiRate"),
                "makuri_rate": w.get("makuriRate"),
                "makurizashi_rate": w.get("makurizashiRate"),
                "nigashi_rate": w.get("nigashiRate"),
            }
            for w in wma if isinstance(w, dict)
        ]

    return result if result else None


def fetch_motor_page(slug: str, date_str: str, round_num: int) -> dict | None:
    """
    /motor ページから取得:
      - motorAggregations (モーターランク・2連率・1着率・テンジ平均)
    """
    url = f"https://boaters-boatrace.com/race/{slug}/{date_str}/{round_num}R/motor"
    html = _fetch(url)
    if not html:
        return None
    apollo = _parse_apollo(html)
    if not apollo or _is_redirect_to_today(apollo):
        return None

    rc = _get_target_race(apollo, round_num)
    if not rc:
        return None

    ma = rc.get("motorAggregations") or []
    if not ma:
        return None

    return {
        "motor_aggregations": [
            {
                "waku": m.get("waku"),
                "motor_n": m.get("motorN"),
                "motor_rank": m.get("motorRank"),
                "race_cnt": m.get("raceCnt"),
                "result_2ren_avg": m.get("result2renAvg"),
                "result_3ren_avg": m.get("result3renAvg"),
                "result_is1_avg": m.get("resultIs1Avg"),
                "tenji_rank_avg": m.get("tenjiRankAvg"),
                "tenji_time_avg": m.get("tenjiTimeAvg"),
                "yuushou_cnt": m.get("yuushouCnt"),
                "yuushutsu_cnt": m.get("yuushutsuCnt"),
            }
            for m in ma if isinstance(m, dict)
        ]
    }


def fetch_race_prediction_page(slug: str, date_str: str, round_num: int) -> dict | None:
    """
    /race-prediction ページから取得:
      - aiBets (組合せ確率・的中フラグ)
      - aiMarks (艇番ランキング)
      - manshuRatePercent (万舟確率)
    """
    url = f"https://boaters-boatrace.com/race/{slug}/{date_str}/{round_num}R/race-prediction"
    html = _fetch(url)
    if not html:
        return None
    apollo = _parse_apollo(html)
    if not apollo or _is_redirect_to_today(apollo):
        return None

    rc = _get_target_race(apollo, round_num)
    if not rc:
        return None

    if not rc.get("aiBetsExist"):
        return None

    result = {}

    # manshuRatePercent
    manshu = rc.get("manshuRatePercent")
    if manshu is not None:
        result["manshu_rate_percent"] = manshu

    # aiBets
    bets = rc.get("aiBets") or []
    if bets:
        result["ai_bets"] = [
            {
                "ai_type": b.get("aiType"),
                "kaime": b.get("kaime"),
                "proba": b.get("proba"),
                "bet": b.get("bet"),
                "is_hit": b.get("isHit"),
                "is_pikaichi": b.get("isPikaichi"),
            }
            for b in bets if isinstance(b, dict)
        ]

    # aiMarks
    marks = rc.get("aiMarks") or []
    if marks:
        result["ai_marks"] = [
            {
                "ai_type": mk.get("aiType"),
                "marks": [mk.get(f"mark{i}") for i in range(1, 7)],
            }
            for mk in marks if isinstance(mk, dict)
        ]

    return result if result else None


# ---------------------------------------------------------------------------
# チェックポイント管理
# ---------------------------------------------------------------------------

def load_checkpoint() -> set:
    if CHECKPOINT_PATH.exists():
        try:
            return set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_checkpoint(done: set) -> None:
    CHECKPOINT_PATH.write_text(
        json.dumps(sorted(done), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# DB から収集対象を取得
# ---------------------------------------------------------------------------

def load_candidates(start: str, end: str) -> list[tuple]:
    """
    戻り値: [(race_id, venue_code, race_date, race_number), ...]
    venue_code は2桁ゼロ埋め
    """
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        SELECT r.id, r.venue_code, r.race_date, r.race_number
        FROM races r
        WHERE r.race_date >= ? AND r.race_date <= ?
          AND r.race_date >= '2023-02-12'
        ORDER BY r.race_date, r.venue_code, r.race_number
    """, (start, end))
    rows = cur.fetchall()
    con.close()

    result = []
    for race_id, venue_code, race_date, race_number in rows:
        vc = str(venue_code).zfill(2)
        if vc not in VENUE_SLUG:
            continue
        result.append((race_id, vc, race_date, int(race_number)))
    return result


# ---------------------------------------------------------------------------
# 1レース処理（スレッドセーフ）
# ---------------------------------------------------------------------------

def _process_race(race_id: int, vc: str, race_date: str, race_num: int) -> dict:
    """1レース分を取得してJSONに保存。戻り値: {'status': 'fetched'|'skip'|'error'}"""
    slug = VENUE_SLUG[vc]
    year = race_date[:4]
    out_dir = OUT_DIR / year
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{race_id}.json"

    if out_path.exists():
        return {"status": "skip", "race_id": race_id}

    race_result = {
        "race_id": race_id,
        "venue_code": vc,
        "race_date": race_date,
        "race_number": race_num,
        "slug": slug,
    }

    data_result  = fetch_data_page(slug, race_date, race_num)
    time.sleep(PAGE_INTERVAL)
    motor_result = fetch_motor_page(slug, race_date, race_num)
    time.sleep(PAGE_INTERVAL)
    pred_result  = fetch_race_prediction_page(slug, race_date, race_num)
    time.sleep(REQUEST_INTERVAL)

    if data_result:
        race_result["data"] = data_result
    if motor_result:
        race_result["motor"] = motor_result
    if pred_result:
        race_result["prediction"] = pred_result

    race_result["has_data"]       = bool(data_result)
    race_result["has_motor"]      = bool(motor_result)
    race_result["has_prediction"] = bool(pred_result)

    out_path.write_text(
        json.dumps(race_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "status": "fetched",
        "race_id": race_id,
        "race_date": race_date,
        "slug": slug,
        "race_num": race_num,
        "has_data": bool(data_result),
        "has_motor": bool(motor_result),
        "has_prediction": bool(pred_result),
    }


# ---------------------------------------------------------------------------
# メイン収集ループ（並列版）
# ---------------------------------------------------------------------------

def collect(candidates: list[tuple], done: set, dry_run: bool) -> None:
    total = len(candidates)
    lock = threading.Lock()
    fetched = 0
    skip = 0
    errors = 0

    # dry-run は逐次処理
    if dry_run:
        for race_id, vc, race_date, race_num in candidates:
            slug = VENUE_SLUG[vc]
            print(f"[DRY] {race_date} {slug} {race_num}R")
        print(f"\n完了: fetched=0 skip=0 errors=0 (dry-run)")
        return

    # 完了済みを事前除外
    pending = [
        (race_id, vc, race_date, race_num)
        for race_id, vc, race_date, race_num in candidates
        if str(race_id) not in done
    ]
    skip = total - len(pending)
    print(f"ワーカー数: {WORKERS}  処理対象: {len(pending):,}件（スキップ済み: {skip:,}件）")

    def _task(args):
        race_id, vc, race_date, race_num = args
        try:
            return _process_race(race_id, vc, race_date, race_num)
        except Exception as e:
            return {"status": "error", "race_id": race_id, "error": str(e)}

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_task, item): item for item in pending}
        for future in as_completed(futures):
            res = future.result()
            with lock:
                status = res["status"]
                done.add(str(res["race_id"]))
                if status == "skip":
                    skip += 1
                elif status == "fetched":
                    fetched += 1
                    if fetched % 100 == 0:
                        r = res
                        print(
                            f"[{fetched+skip:>6}/{total}] {r['race_date']} {r['slug']:<12} {r['race_num']:>2}R "
                            f"data={'+'if r['has_data']else'-'} "
                            f"motor={'+'if r['has_motor']else'-'} "
                            f"pred={'+'if r['has_prediction']else'-'} "
                            f"(fetched={fetched} skip={skip} err={errors})"
                        )
                        save_checkpoint(done)
                else:
                    errors += 1
                    print(f"[ERROR] race_id={res['race_id']}: {res.get('error','')}")

    save_checkpoint(done)
    print(f"\n完了: fetched={fetched} skip={skip} errors={errors}")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="ボーターズ レースデータ収集")
    parser.add_argument("--start", default=COLLECT_START_DEFAULT)
    parser.add_argument("--end", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true", help="チェックポイントを削除して最初から")
    parser.add_argument("--sample", type=int, default=0, help="サンプル収集（N件のみ）")
    args = parser.parse_args()

    if args.reset and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        print("チェックポイントを削除しました")

    done = load_checkpoint()
    print(f"収集期間: {args.start} 〜 {args.end}")
    print(f"チェックポイント: {len(done)}件 完了済み")

    candidates = load_candidates(args.start, args.end)
    print(f"対象レース: {len(candidates):,}件")

    if args.sample > 0:
        # サンプル収集: 均等間隔でサンプリング
        step = max(1, len(candidates) // args.sample)
        candidates = candidates[::step][:args.sample]
        print(f"サンプルモード: {len(candidates)}件")

    if not candidates:
        print("対象なし")
        return

    if args.dry_run:
        print("--- DRY RUN ---")

    collect(candidates, done, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
