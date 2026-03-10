# 引継ぎ資料（HANDOVER）

**最終更新**: 2026-03-09
**目的**: セッション間の引継ぎ情報を一元管理（常に最新状態に上書き更新）

---

## 📋 プロジェクト現状（一目でわかる）

### システム構成

```
【戦略B】順位予測
    ↓ ExtendedScorer（スコアリング）
    ↓ hierarchical_predictor（信頼度A-E判定）
    ↓ _recalculate_race_confidence（スコア差ベース再判定）
【フィルターC】購入判定
    ↓ BetTargetEvaluator（信頼度×オッズで買うか判断）
【パターンH】買い目生成
    ↓ MultiBetGenerator（1-2軸3点買い: 200円/100円/100円）
```

### 📊 6年間バックテスト結果（現在の最新値・2026-03-09）

> ⚠️ **2026-03-09更新**: 2020-2023年 before予測がst_time修正+P7/P8コード変更後に再生成された結果、ROIが大きく変動。
> 2024/2025年 before予測は旧コードのまま（未再生成）。現在は混在状態。全年度の再生成が完了すれば再評価が必要。

> 旧バージョン（v2.3.0〜v2.6.0）の詳細 → [docs/archive/version_history.md](archive/version_history.md)

| 指標 | 値 |
|------|:--:|
| **6年間ROI** | **116.0%** |
| **6年間収支** | **+43,500円** |
| **黒字年数** | **2/6年** ※2020-2023赤字 |
| 購入レース数（重複除外） | 1,843件 |
| 的中数 | 55件 |
| **的中率** | **2.98%** |

#### 年度別パフォーマンス（ユニーク版・2026-03-09）

| 年度 | 件数 | ROI | 収支 | 判定 | 備考 |
|:----:|:---:|:---:|:----:|:----:|------|
| 2020 | 169 | 95.9% | -1,010 | 赤字 | st_time修正後に再生成（新コード） |
| 2021 | 364 | 92.1% | -4,281 | 赤字 | st_time修正後に再生成（新コード） |
| 2022 | 363 | 78.0% | -11,840 | 赤字 | st_time修正後に再生成（新コード） |
| 2023 | 387 | 87.3% | -6,850 | 赤字 | st_time修正後に再生成（新コード） |
| 2024 | 391 | 134.4% | +20,690 | 黒字 | 旧コードのまま（未再生成） |
| 2025 | 169 | 283.5% | +46,790 | 黒字 | 旧コードのまま（未再生成） |

#### 条件別成績（4条件）

| 条件 | 方式 | 件数 | ROI | 収支 |
|:-----|:---:|:---:|:---:|:----:|
| B×50-100×冬+4月除外+6会場 | P.H | 642 | 88.7% | -10,320 |
| 唐津×C×B1×20-30 | 1点 | 439 | 103.9% | +1,720 |
| 児島×C×B1×30-50×1点買い | 1点 | 357 | 140.4% | +14,429 |
| D×5コース予測×A2除外×桐生+平和島+鳴門 | P.H | 405 | 137.3% | +37,670 |
| **合計** | - | **1,843** | **116.0%** | **+43,500** |

※方式: P.H=パターンH（3点買い400円）、1点=1点買い（100円）

> **旧ベースライン (v2.7.0 / 2026-03-05 / 旧コード統一時)**:
> 1,862件 / ROI 160.6% / +165,130円 / 5/6年黒字

---

### ⚠️ データ充足状況（2026-03-05 DB実測確認）

| 年度 | races | entries% | results% | details% | trifecta% | payouts% | conditions% |
|:----:|------:|:--------:|:--------:|:--------:|:---------:|:--------:|:-----------:|
| 2020 | 29,436 | 100% | 98.9% | 100% | 97.2% | 98.9% | 98.9% |
| 2021 | 55,728 | 100% | 98.6% | 100% | 98.6% | 98.6% | 98.6% |
| 2022 | 56,436 | 97.8% | 96.3% | 100% | 98.5% | 96.3% | 98.5% |
| 2023 | 55,992 | 100% | 98.9% | 100% | 98.9% | 98.9% | 98.9% |
| 2024 | 55,167 | 100% | 100% | 100% | 99.5% | 97.7% | 99.6% |
| 2025 | 25,041 | 97.0% | 99.2% | 100% | 99.2% | 99.1% | 100% |
| 2026 | ~10,800 | - | - | 100% | 97-99% | - | - |

---

### 🔴 P1: st_time 2スケール混在問題（根本原因確定・修正中）

**根本原因**: beforeinfo_scraper（`{pit番号}.{ST}`=1.17）vs result_scraper（`0.{ST}`=0.17）のフォーマット差異。
`補完_レース詳細データ_改善版v4.py` がresult_scraper方式でst_timeを上書き → スケール混在。
パターンボーナスが `abs(st_time)` でST順位を計算 → 予測順位が逆転。2023年が最大被害（混入率38.2%→B信頼度48%）。

**修正状況（P4として実行中）**:
- DB修正完了: `st_time - FLOOR(st_time)` で813,804件更新（2026-03-06）
- before予測再生成: 2020-2023完了 / **2024生成中（〜08-14まで完了, ETA: 2026-03-10 16:00頃）** / **2025生成中（2026-03-09 開始）**
- B信頼度1位的中率: 2023年 48% → 64%（修正効果確認済み）
- **推定効果**: 2023年赤字解消 → 6/6年黒字の可能性
- 両年度完了後: `import_features_from_predictions.py --full --force` → `fast_backtest.py --full` で新ベースライン確認

**関連ファイル**: `src/scraper/beforeinfo_scraper.py`(L457-462)、`src/analysis/race_predictor.py`(L2079-2093)

---

### 予測ロジック改善（2026-03-09 コード変更完了・検証待ち）

P4完了後に全年度 advance+before 再生成 → バックテストで効果確認が必要。

| # | 変更内容 | 状態 |
|:-:|---------|:----:|
| P7 | class_score重複排除（class重み10→0） | 完了 |
| P8 | compound_buff展示系60%縮小（exhibition重み8→4） | 完了 |
| 予測改善 | motor_second_rate重み有効化（0→3）、chikusen_time無効化（4→0）、entry_dictバグ修正 | 完了 |

### fast_backtest 実装完了（2026-03-09）

高速パラメータテスト基盤が完成した。

| ファイル | 役割 |
|---------|------|
| `scripts/backtest/fast_backtest.py` | 高速バックテスト（信頼度閾値・重みテスト） |
| `scripts/prediction/generate_features.py` | prediction_features 生成（predict_race() 再実行方式） |
| `scripts/prediction/import_features_from_predictions.py` | 高速インポート（race_predictions から数分で完了） |
| `scripts/validation/validate_fast_backtest.py` | 精度検証スクリプト |

**使い方**:
```bash
# データ準備（数分）
python scripts/prediction/import_features_from_predictions.py --full --force

# デフォルト設定テスト（標準バックテストと完全一致）
python scripts/backtest/fast_backtest.py --full

# 信頼度閾値変更テスト（P5）
python scripts/backtest/fast_backtest.py --full --conf-a-gap 12
```

**注意事項**:
- `--conf-*` 変更時: `total_score_final`（compound_buff込み）から近似再計算 → 参考値として使用
- `--motor-weight` 等の重み変更（full モード）: `generate_features.py` で完全再生成が必要
- `import_features_from_predictions.py` 再実行後は `fast_backtest.py` も再実行すること

### 未着手タスク

| 優先度 | タスク | 概要 |
|:------:|--------|------|
| 最高 | 2024/2025 before予測 再生成 | **実行中**（2024: ETA 03-10 16:00, 2025: 03-09開始）完了後に import+fast_backtest で新ベースライン確認 |
| P5 | Stage 2 A基準緩和 | gap 15→12（C判定が多すぎる問題）→ fast_backtest でテスト可能（再生成完了後が有効） |
| P6 | motor_score基礎点引き下げ | 12→8（モーター差の識別力改善） |

---

## 📝 最近の作業

### 朝の通知「対象0件・候補0件」バグ修正（2026-03-09 完了）

**根本原因**: `odds_data = {}` がfalsy → `odds = 0` → `is None` チェック素通り → 候補0件
**修正**: `generate_daily_predictions.py` L121: `is None` → `is None or bet_target.odds == 0`
**追加**: `daily_scheduler.py` にファイルログ追加、`today_prediction.py` にデバッグログ追加

> **スケジューラー再起動が必要**: PID 11984 kill → `start_discord_notification.bat` で再起動。
> 再起動後: `logs/scheduler_YYYYMMDD.log` に全出力が保存される。

---

## 📁 主要ファイル

| ファイル | 役割 |
|---------|------|
| [残タスク一覧.md](残タスク一覧.md) | 唯一の最新状態情報源 |
| [HANDOVER.md](HANDOVER.md) | このファイル（引継ぎ情報） |
| [DATABASE_SCHEMA.md](architecture/DATABASE_SCHEMA.md) | DB構造 |
| [archive/version_history.md](archive/version_history.md) | 旧バージョン詳細 |

---

## 🎛️ 有効なフィーチャーフラグ

```python
FEATURE_FLAGS = {
    'hierarchical_predictor': True,
    'ab_rank_special_betting': True,
    'pairwise_scoring': True,
    'kimarite_flow_prediction': True,
    'makuri_risk_adjustment': True,
    'negative_pattern_filter': True,
    'upset_pattern_filter': True,
    'score_gap_confidence': True,
}
```

詳細は [config/feature_flags.py](../config/feature_flags.py) 参照

---

## ⚠️ システム更新時の注意点

| 更新内容 | 対応 | 一致率検証 | 標準テスト |
|---------|------|:--------:|:--------:|
| 条件追加・変更 | `priority`設定のみ | 不要 | 推奨 |
| 予測ロジック更新 | 予測データ再生成 | 推奨 | **必須** |
| 新フィルター追加 | Tier 2/3の両方を同期更新 | **必須** | **必須** |

---

## 🔄 データ同期方針

| データ種類 | 同期方法 | 場所 |
|-----------|---------|------|
| コード・設定 | Git (push/pull) | GitHub |
| DB（boatrace.db） | 手動コピー | OneDrive: `BoatRace/data/` |

```bash
# OneDrive → ローカル（作業開始時）
copy "C:\Users\User\OneDrive\BoatRace\data\boatrace.db" "data\boatrace.db"
# ローカル → OneDrive（作業終了時）
copy "data\boatrace.db" "C:\Users\User\OneDrive\BoatRace\data\boatrace.db"
```

---

**更新ルール**: セッション終了時に必ずこのファイルを更新（上書き）。古いHANDOVER_YYYYMMDD.mdは作成しない。
