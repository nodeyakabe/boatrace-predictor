#!/bin/bash
cd "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"

LOG="logs/2025_brute_force_$(date +%Y%m%d_%H%M%S).log"
echo "[$(date)] 2025年brute-force収集 開始" | tee -a "$LOG"

months=(
  "01:2025-01-01:2025-01-31"
  "02:2025-02-01:2025-02-28"
  "03:2025-03-01:2025-03-31"
  "04:2025-04-01:2025-04-30"
  "05:2025-05-01:2025-05-31"
  "06:2025-06-01:2025-06-30"
  "07:2025-07-01:2025-07-31"
  "08:2025-08-01:2025-08-31"
  "09:2025-09-01:2025-09-30"
  "10:2025-10-01:2025-10-31"
  "11:2025-11-01:2025-11-30"
  "12:2025-12-01:2025-12-31"
)

for entry in "${months[@]}"; do
  m="${entry%%:*}"
  rest="${entry#*:}"
  start="${rest%%:*}"
  end="${rest##*:}"
  outdir="data/csv/2025_補完_${m}"

  # 既存CSVが十分あればスキップ
  if [ -f "${outdir}/races.csv" ]; then
    lines=$(wc -l < "${outdir}/races.csv")
    if [ "$lines" -gt 2000 ]; then
      echo "[$(date)] ${m}月: スキップ（既存CSV ${lines}行）" | tee -a "$LOG"
      continue
    fi
  fi

  echo "[$(date)] ${m}月: 収集開始 (${start}〜${end})" | tee -a "$LOG"
  python scripts/data_collection/fetch_to_csv_parallel_improved.py \
    --start "$start" --end "$end" \
    --output "$outdir" --brute-force --workers 8 \
    >> "$LOG" 2>&1
  rc=$?

  if [ $rc -eq 0 ] && [ -f "${outdir}/races.csv" ]; then
    lines=$(wc -l < "${outdir}/races.csv")
    echo "[$(date)] ${m}月: 収集完了 races.csv=${lines}行" | tee -a "$LOG"
  else
    echo "[$(date)] ${m}月: 異常終了（終了コード=${rc}）" | tee -a "$LOG"
  fi
done

echo "[$(date)] === 全月収集完了 → DBインポート開始 ===" | tee -a "$LOG"

import_dirs=""
for m in 01 02 03 04 05 06 07 08 09 10 11 12; do
  if [ -f "data/csv/2025_補完_${m}/races.csv" ]; then
    import_dirs="$import_dirs --dir data/csv/2025_補完_${m}"
  fi
done

python scripts/data_collection/import_races_csv.py $import_dirs >> "$LOG" 2>&1
echo "[$(date)] === DBインポート完了 ===" | tee -a "$LOG"

echo "[$(date)] === 最終確認 ===" | tee -a "$LOG"
python3 - << 'PYEOF' | tee -a "$LOG"
import sqlite3
conn = sqlite3.connect('data/boatrace.db')
cur = conn.cursor()
cur.execute("SELECT strftime('%Y-%m', race_date), COUNT(*) FROM races WHERE race_date LIKE '2025%' GROUP BY 1 ORDER BY 1")
total = 0
for ym, cnt in cur.fetchall():
    print(f"  {ym}: {cnt:,}件")
    total += cnt
cur.execute("SELECT COUNT(*) FROM races WHERE race_date LIKE '2025%'")
print(f"  合計: {cur.fetchone()[0]:,}件")
conn.close()
PYEOF

echo "[$(date)] 処理完了" | tee -a "$LOG"
