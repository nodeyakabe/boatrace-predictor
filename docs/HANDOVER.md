# 引継ぎ資料（HANDOVER）

**最終更新**: 2026-03-11
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

### 📊 6年間バックテスト結果（暫定値・2026-03-11）

> ⚠️ **2026-03-11更新**: 2025年before予測を再生成中（exhibition_buff_rules.py修正後）。
> 完了後に再バックテストが必要。2024年は最終値（st_time修正後・正しいcompound_buff）。

> 旧バージョン（v2.3.0〜v2.6.0）の詳細 → [docs/archive/version_history.md](archive/version_history.md)

| 指標 | 値 |
|------|:--:|
| **6年間ROI** | **暫定 81.7%**（2025再生成後に変わる） |
| **6年間収支** | **暫定 -52,920円** |
| **黒字年数** | **0/6年**（2025再生成後に変わる） |
| 購入レース数（重複除外） | 1,964件 |

#### 年度別パフォーマンス（ユニーク版・暫定 2026-03-11）

| 年度 | 件数 | ROI | 収支 | 判定 | 備考 |
|:----:|:---:|:---:|:----:|:----:|------|
| 2020 | 169 | 95.9% | -1,010 | 赤字 | st_time修正後・正常コード ✓ |
| 2021 | 364 | 92.1% | -4,280 | 赤字 | st_time修正後・正常コード ✓ |
| 2022 | 363 | 78.0% | -11,840 | 赤字 | st_time修正後・正常コード ✓ |
| 2023 | 387 | 87.3% | -6,850 | 赤字 | st_time修正後・正常コード ✓ |
| 2024 | 340 | 86.7% | -6,990 | 赤字 | st_time修正後・正常コード ✓（チェーン実行分） |
| 2025 | — | — | — | **再生成中** | exhibition_buff修正後に再生成中 ⚠️ |

#### 条件別成績（4条件・暫定）

| 条件 | 方式 | 件数 | ROI | 収支 |
|:-----|:---:|:---:|:---:|:----:|
| B×50-100×冬+4月除外+6会場 | P.H | 680 | 69.3% | -29,370 |
| 唐津×C×B1×20-30 | 1点 | 462 | 104.9% | +2,270 |
| 児島×C×B1×30-50×1点買い | 1点 | 375 | 132.2% | +12,080 |
| D×5コース予測×A2除外+最適化 | P.H | 447 | 65.7% | -37,900 |
| **合計** | - | **1,964** | **81.7%** | **-52,920** |

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

### 🔴 P4: st_time 2スケール混在問題（修正完了）

**根本原因**: beforeinfo_scraper（`{pit番号}.{ST}`=1.17）vs result_scraper（`0.{ST}`=0.17）のフォーマット差異。
`補完_レース詳細データ_改善版v4.py` がresult_scraper方式でst_timeを上書き → スケール混在。

**修正状況（完了）**:
- DB修正: 813,804件 → 2026-03-06 完了
- 追加修正: 2,378件 → 2026-03-11 完了（修正後に新規挿入されたレコード）
- before予測再生成: 2020-2024 完了 / **2025 再生成中**（exhibition_buff修正後のコードで実行中 2026-03-11）

**st_time正常値確認（2026-03-11）**:
- 残存 `>= 1.0`: 0件
- 範囲: min=-0.75, max=0.99（正常）

---

### 🔴 exhibition_buff_rules.py 修正（2026-03-11 完了）

**問題**: 2026-03-09の `ab12e54` コミットでP8変更（compound_buff値60%圧縮）が混入。
`9258c8c` リバートで `race_predictor.py` は戻されたが、`exhibition_buff_rules.py` が見落とされた。

**影響**: 2025年before予測が60%縮小された展示buffで生成 → ROI 57.4%/341件（本来の169件/283%と大幅乖離）。

**修正内容（コミット 2e877e6）**:

| ルール | 修正前 | 修正後 |
|--------|:------:|:------:|
| exhibition_1st_course1 | 12.0 | **20.0** |
| exhibition_1st_course2_3 | 2.4 | **4.0** |
| exhibition_1st_course4_6 | 0.9 | **1.5** |
| exhibition_low_course_outer | -2.4 | **-4.0** |
| exhibition_1st_a1 | 7.2 | **12.0** |
| exhibition_1st_a2 | 1.8 | **3.0** |
| exhibition_1st_b1 | 0.9 | **1.5** |
| exhibition_1st_b2 | 0.3 | **0.5** |
| exhibition_top2_st_good_inner | 3.6 | **6.0** |
| exhibition_top2_st_normal_inner | 1.8 | **3.0** |
| exhibition_low_st_normal_outer | -3.0 | **-5.0** |

**次のステップ**: 2025年 before予測 再生成完了 → `import_features_from_predictions.py --full --force` → バックテスト

---

### 現在実行中のタスク（2026-03-11）

| タスク | 状態 | ETA |
|--------|:----:|-----|
| 2025年 before予測 Jan-Apr, May-Aug（2並列） | **実行中** | 〜6〜7時間 |
| 2025年 before予測 Sep-Dec（完了後に1プロセスで実行） | **待機中** | 上記完了後さらに5〜6時間 |

> **補足**: 当初6並列で起動したが、PC負荷軽減のため2並列に削減（2026-03-11）。
> Sep-Dec 担当プロセスが停止済み（Sep 22 まで完了）。Jan-Apr / May-Aug 完了後に再開すること。
> 再開コマンド: `python scripts/prediction/generate_before_fast.py --year 2025 --start-date 2025-09-23 --end-date 2025-12-31`

---

### 未着手タスク

| 優先度 | タスク | 概要 |
|:------:|--------|------|
| 最高 | バックテスト再実行 | 2025年再生成完了後に `import_features_from_predictions.py --full --force` → `standard_backtest_unique.py --full` |
| 高 | 条件の再評価 | 正しいデータでバックテスト後、全条件を再評価（B_50_100・D_course5の廃止検討） |
| P5 | Stage 2 A基準緩和 | gap 15→12（C判定が多すぎる問題）→ fast_backtest でテスト可能（再生成完了後） |
| P6 | motor_score基礎点引き下げ | 12→8（モーター差の識別力改善） |

---

## 📝 最近の作業

### 2026-03-11 exhibition_buff_rules.py修正 + st_time追加修正

**問題発見**: git diff で f0d6d10 と現在HEADを比較したところ `exhibition_buff_rules.py` の全buff値が60%圧縮されていることが判明。`9258c8c` リバートの見落とし。

**修正完了**:
1. `exhibition_buff_rules.py`: 全11値をf0d6d10相当に復元（コミット 2e877e6）
2. `race_details.st_time`: 追加2,378件を修正（修正後の補完で発生したもの）
3. 2025年 before予測: 正しいコードで再生成中（6並列、〜10時間）

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

**教訓（2026-03-11）: exhibition_buff_rules.py 見落としリバートの根本原因**

| フェーズ | 問題 | 対策（実装済み） |
|---------|------|----------------|
| **混入** | `ab12e54`「プロジェクト整理」に P8 コード変更（60%圧縮）が混入。60ファイル変更の中に `src/analysis/exhibition_buff_rules.py` 変更が隠れた | コード変更とドキュメント整理を別コミットに分ける |
| **リバート漏れ** | `9258c8c` リバートが `race_predictor.py` のみ対象。`git diff f0d6d10 HEAD -- src/ config/` を実行せず、他ファイルの確認を省略 | リバート後は必ず `git diff <target> HEAD -- src/ config/` で全差分確認 |
| **検証なし実行** | リバート直後に検証なしで 2025年 before 予測生成を開始 → 誤ったコードで全件生成 | **`safety_check.py` に exhibition_buff 値チェックを追加（2026-03-11）** → 生成スクリプト起動時に自動検出 |

```bash
# リバート後の必須確認コマンド
git diff <target_commit> HEAD -- src/ config/
python scripts/safety_check.py  # exhibition_buff 値の自動チェック
```

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
