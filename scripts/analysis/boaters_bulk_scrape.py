"""
ボーターズ大量スクレイピングスクリプト
公式DBのレース一覧からURLを生成して1000件まで蓄積する
"""
import io
import json
import random
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH   = REPO_ROOT / "data" / "boatrace.db"
RACES_DIR = REPO_ROOT / "data" / "boaters_analysis" / "races"
SCRAPER   = REPO_ROOT / "scripts" / "analysis" / "boaters_reverse_engineer.py"

VENUE_CODE_TO_SLUG = {
    "01": "kiryu",    "02": "toda",      "03": "edogawa",  "04": "heiwajima",
    "05": "tamagawa", "06": "hamanako",  "07": "gamagori", "08": "tokoname",
    "09": "tsu",      "10": "mikuni",    "11": "biwako",   "12": "suminoe",
    "13": "amagasaki","14": "naruto",    "15": "marugame", "16": "kojima",
    "17": "miyajima", "18": "tokuyama",  "19": "shimonoseki","20": "wakamatsu",
    "21": "ashiya",   "22": "fukuoka",   "23": "karatsu",  "24": "omura",
}

TARGET      = 1000   # 目標総件数
BATCH_DELAY = 0.35   # リクエスト間隔（秒）
MAX_ERRORS  = 20     # 連続エラー上限


def load_saved_keys() -> set:
    keys = set()
    for f in RACES_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            ri = d["race_info"]
            keys.add((ri["date"], ri["venue_code"].zfill(2), str(ri["race_number"])))
        except Exception:
            pass
    return keys


def get_candidates(start_date: str, end_date: str) -> list:
    """DB から (venue_code, race_date, race_number) を取得"""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT DISTINCT venue_code, race_date, race_number
        FROM races
        WHERE race_date BETWEEN ? AND ?
        ORDER BY race_date, venue_code, race_number
        """,
        (start_date, end_date),
    )
    rows = cur.fetchall()
    con.close()
    return rows


def scrape_one(slug: str, date: str, race: int) -> bool:
    url = f"https://boaters-boatrace.com/race/{slug}/{date}/{race}R/race-prediction"
    r = subprocess.run(
        [sys.executable, str(SCRAPER), "--url", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
    )
    out = r.stdout + r.stderr
    return r.returncode == 0 and "[OK]" in out


def main():
    RACES_DIR.mkdir(parents=True, exist_ok=True)

    saved = load_saved_keys()
    current = len(saved)
    print(f"[START] 保存済み: {current}件 / 目標: {TARGET}件 / 追加必要: {TARGET - current}件")

    # DB から候補取得（2026-03-01〜2026-05-12）
    rows = get_candidates("2026-03-01", "2026-05-12")
    print(f"[INFO] DB候補: {len(rows)}件")

    # フィルタ & シャッフル
    candidates = []
    for vc, rd, rn in rows:
        vc = str(vc).zfill(2)
        slug = VENUE_CODE_TO_SLUG.get(vc)
        if not slug:
            continue
        key = (rd, vc, str(rn))
        if key in saved:
            continue
        candidates.append((slug, rd, rn))

    random.seed(2026)
    random.shuffle(candidates)
    print(f"[INFO] 未取得候補: {len(candidates)}件")

    ok = ng = consec_err = 0
    tried = 0

    for slug, date, race in candidates:
        current_total = len(load_saved_keys())
        if current_total >= TARGET:
            break
        if consec_err >= MAX_ERRORS:
            print(f"[ABORT] 連続エラー{MAX_ERRORS}件超過。ネットワークを確認してください。")
            break

        tried += 1
        success = False
        try:
            success = scrape_one(slug, date, race)
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(f"  [EX] {slug}/{date}/{race}R: {e}")

        if success:
            ok += 1
            consec_err = 0
            new_total = current_total + 1
            print(f"[{new_total:04d}/{TARGET}] OK  {slug}/{date}/{race}R", flush=True)
        else:
            consec_err += 1

        time.sleep(BATCH_DELAY)

    final_total = len(load_saved_keys())
    print(f"\n[DONE] 最終件数: {final_total}件 / 新規追加: {ok}件 / 試行: {tried}件 / エラー: {ng}件")


if __name__ == "__main__":
    main()
