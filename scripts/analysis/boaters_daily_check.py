"""
boaters_daily_check.py
本日の高信頼度レースに対してボーターズのAI万舟率を一括取得・表示する

使い方:
  python scripts/analysis/boaters_daily_check.py                # 本日
  python scripts/analysis/boaters_daily_check.py --date 2026-05-13
  python scripts/analysis/boaters_daily_check.py --min-manshu 20  # 万舟率>=20%のみ表示

出力:
  * 本ツール信頼度A/BのレースにボーターズのAI万舟率を付加して表示
  * 万舟率>=30%はHighlight表示（ROI 105.7%の独立シグナル）
  * data/boaters_analysis/daily/{date}.json に保存
"""
import argparse
import io
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH   = REPO_ROOT / "data" / "boatrace.db"
DAILY_DIR = REPO_ROOT / "data" / "boaters_analysis" / "daily"
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

VENUE_CODE_TO_NAME = {
    "01": "桐生",   "02": "戸田",    "03": "江戸川",  "04": "平和島",
    "05": "多摩川", "06": "浜名湖",  "07": "蒲郡",    "08": "常滑",
    "09": "津",     "10": "三国",    "11": "びわこ",  "12": "住之江",
    "13": "尼崎",   "14": "鳴門",    "15": "丸亀",    "16": "児島",
    "17": "宮島",   "18": "徳山",    "19": "下関",    "20": "若松",
    "21": "芦屋",   "22": "福岡",    "23": "唐津",    "24": "大村",
}

BATCH_DELAY = 0.4


def get_todays_high_conf_races(date: str) -> list:
    """本ツールの当日advance予測でA/B信頼度のレースを取得"""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
        SELECT DISTINCT
            r.id as race_id,
            r.race_date,
            r.venue_code,
            r.race_number,
            r.race_time,
            rp.confidence,
            rp.rank_prediction,
            rp.total_score,
            rp.racer_name
        FROM race_predictions rp
        JOIN races r ON rp.race_id = r.id
        WHERE r.race_date = ?
          AND rp.prediction_type = 'advance'
          AND rp.confidence IN ('A', 'B')
          AND rp.rank_prediction = 1
        ORDER BY r.venue_code, r.race_number
    """, (date,))
    rows = cur.fetchall()
    con.close()
    return [dict(r) for r in rows]


def load_existing_manshu(date: str) -> dict:
    """既存のdailyファイル or racesファイルからmanshu_rateをロード"""
    result = {}
    date_str = date.replace('-', '')

    # 1. dailyファイル優先（前回実行済みキャッシュ）
    daily_file = DAILY_DIR / f"{date_str}.json"
    if daily_file.exists():
        try:
            data = json.loads(daily_file.read_text(encoding='utf-8'))
            for entry in data.get('races', []):
                vc = str(entry.get('venue_code', '')).zfill(2)
                rn = entry.get('race_number')
                mr = entry.get('manshu_rate')
                if vc and rn is not None and mr is not None:
                    result[(date, vc, str(rn))] = mr
            return result
        except Exception:
            pass

    # 2. racesフォルダから個別JSONファイルを検索
    # ファイル名形式: {YYYYMMDD}_{VC}_{RN}R.json 例: 20260513_08_1R.json
    for f in RACES_DIR.glob(f"{date_str}_*.json"):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            ri = d.get('race_info', {})
            vc = str(ri.get('venue_code', '')).zfill(2)
            rn  = ri.get('race_number')
            mr  = ri.get('boaters_ai_manshu_rate')
            if vc and rn is not None and mr is not None:
                result[(date, vc, str(rn))] = mr
        except Exception:
            pass
    return result


def scrape_manshu(venue_code: str, date: str, race_num: int) -> int | None:
    """ボーターズからmanshu_rateを取得しJSONに保存、値を返す"""
    vc   = str(venue_code).zfill(2)
    slug = VENUE_CODE_TO_SLUG.get(vc)
    if not slug:
        return None
    url = (f"https://boaters-boatrace.com/race/{slug}/"
           f"{date}/{race_num}R/race-prediction")
    try:
        r = subprocess.run(
            [sys.executable, str(SCRAPER), "--url", url],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=25,
        )
        if r.returncode != 0 or "[OK]" not in (r.stdout + r.stderr):
            return None
        # 保存されたJSONから値を読み出す (形式: {YYYYMMDD}_{VC}_{RN}R.json)
        date_str = date.replace('-', '')
        saved = RACES_DIR / f"{date_str}_{vc}_{race_num}R.json"
        if saved.exists():
            d = json.loads(saved.read_text(encoding='utf-8'))
            return d.get('race_info', {}).get('boaters_ai_manshu_rate')
        # フォールバック: race_infoのrace_numberで照合
        for f in RACES_DIR.glob(f"{date_str}_{vc}_*.json"):
            d = json.loads(f.read_text(encoding='utf-8'))
            ri = d.get('race_info', {})
            if ri.get('race_number') == race_num:
                return ri.get('boaters_ai_manshu_rate')
    except Exception:
        pass
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--min-manshu', type=int, default=0,
                        help='この万舟率以上のみ表示（0=全件）')
    parser.add_argument('--no-scrape', action='store_true',
                        help='スクレイピングせず既存データのみ使用')
    args = parser.parse_args()
    date = args.date

    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"ボーターズ万舟率チェック [{date}]")
    print(f"{'='*60}\n")

    # 本ツールの高信頼度レース取得
    races = get_todays_high_conf_races(date)
    if not races:
        print(f"[INFO] {date} の advance 高信頼度予測が見つかりません")
        print("       (before予測後に再実行するか --no-scrape を外してください)")
        return

    print(f"本ツール信頼度A/B レース数: {len(races)}件\n")

    # 既存manshu_rateをロード
    existing = load_existing_manshu(date)

    results = []
    scraped = 0
    for race in races:
        vc  = str(race['venue_code']).zfill(2)
        rn  = race['race_number']
        key = (date, vc, str(rn))

        manshu = existing.get(key)

        if manshu is None and not args.no_scrape:
            print(f"  取得中: {VENUE_CODE_TO_NAME.get(vc, vc)} {rn}R ...", end='', flush=True)
            manshu = scrape_manshu(vc, date, rn)
            if manshu is not None:
                print(f" 万舟率{manshu}%")
                scraped += 1
            else:
                print(" (取得失敗)")
            time.sleep(BATCH_DELAY)

        results.append({
            'venue_code':  vc,
            'venue_name':  VENUE_CODE_TO_NAME.get(vc, vc),
            'race_number': rn,
            'race_time':   race.get('race_time', ''),
            'confidence':  race['confidence'],
            'total_score': race.get('total_score'),
            'rank1_racer': race.get('racer_name', ''),
            'manshu_rate': manshu,
        })

    # 表示
    print(f"\n{'='*60}")
    print(f"{'会場':<6} {'R':>3} {'時刻':>6} {'信'} {'スコア':>6} {'万舟率':>6}  予測1着")
    print(f"{'-'*60}")

    flagged = []
    for r in sorted(results, key=lambda x: (x['manshu_rate'] or 0), reverse=True):
        mr = r['manshu_rate']
        mr_str = f"{mr}%" if mr is not None else "  -  "
        flag = " <<HIGH" if (mr or 0) >= 30 else (" <mid" if (mr or 0) >= 20 else "")
        if (mr or 0) >= args.min_manshu:
            print(f"{r['venue_name']:<6} {r['race_number']:>3}R {r['race_time']:>6}"
                  f" {r['confidence']} {r['total_score'] or '':>6.1f}"
                  f" {mr_str:>6}  {r['rank1_racer']}{flag}")
        if (mr or 0) >= 30:
            flagged.append(r)

    print(f"\n万舟率>=30% レース: {len(flagged)}件")
    if flagged:
        print("  ※ 高オッズ条件（D_P143等）で買い目が出る場合、優先的に確認推奨")
        for r in flagged:
            print(f"    {r['venue_name']} {r['race_number']}R 万舟率{r['manshu_rate']}%")

    # 保存
    daily_file = DAILY_DIR / f"{date.replace('-', '')}.json"
    daily_file.write_text(
        json.dumps({
            'date': date,
            'generated_at': datetime.now().isoformat(),
            'races': results,
            'flagged_high_manshu': flagged,
        }, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    print(f"\n[保存] {daily_file}")
    if scraped > 0:
        print(f"[新規取得] {scraped}件")


if __name__ == '__main__':
    main()
