#!/bin/bash
# wind_direction修正後の全年度 before 予測再生成
# 2026-03-27 更新: workers 2→3
cd "c:/Users/User/Desktop/BR/BoatRace_package_20251115_172032"

for year in 2020 2021 2022 2023 2024 2025; do
    echo "=== ${year}年 開始: $(date) ==="
    python scripts/prediction/generate_before_fast_parallel.py \
        --year $year --workers 3 --force
    if [ $? -ne 0 ]; then
        echo "${year}年 失敗" | tee -a logs/regen_before_all.log
        break
    fi
    echo "=== ${year}年 完了: $(date) ===" | tee -a logs/regen_before_all.log
done
echo "全年度再生成完了: $(date)" | tee -a logs/regen_before_all.log
