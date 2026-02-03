# Phase 3 実装サマリー

**作成日**: 2025-12-15
**ステータス**: 完了

---

## 概要

Phase 3では、事前情報と直前情報の明確な分離を実施し、重複加点の問題を解消しました。

## 発見された問題

### 1. 展示タイムの重複評価
- **ExtendedScorer** (`calculate_exhibition_time_score()`, line 638-725)
- **BeforeInfoScorer** (`_calc_exhibition_time_score()`, line 169-197)

両方で展示タイムを評価しており、同じ情報が2回加点されていた可能性。

### 2. チルト角度の重複評価
- **ExtendedScorer** (`calculate_tilt_angle_score()`, line 727-818)
- **BeforeInfoScorer** (`_calc_tilt_wind_score()`, line 326-396)

### 3. 事前/直前情報の混在
**ExtendedScorer**に事前情報と直前情報が混在:
- 事前情報: 級別、F/L持ち、平均ST
- 直前情報: 展示タイム、チルト角度

---

## 実装した新モジュール

### 1. PreInfoScorer (`src/analysis/pre_info_scorer.py`)

**目的**: 事前情報（レース前に確定している情報）のみでスコアリング

**スコア配分** (100点満点):
| 項目 | 点数 | 説明 |
|------|------|------|
| overall | 15.0 | 全国成績 |
| course | 15.0 | コース別成績 |
| venue | 10.0 | 当地成績 |
| recent_form | 10.0 | 直近成績（過去5走） |
| class | 12.0 | 級別 |
| fl_penalty | -10.0 | F/L持ちペナルティ |
| avg_st | 8.0 | 平均ST |
| motor | 10.0 | モーター成績 |
| boat | 5.0 | ボート成績 |
| grade_affinity | 5.0 | グレード適性 |
| kimarite | 5.0 | 決まり手適性 |
| rentai | 5.0 | 連対率 |

**除外した項目**（直前情報のため）:
- 展示タイム
- 展示ST
- チルト角度
- 進入コース
- 前走成績（当日）

### 2. ScoreIntegrator (`src/analysis/score_integrator.py`)

**目的**: 事前スコアと直前スコアを統合

**統合モード**:
| モード | 説明 |
|--------|------|
| FIXED | 固定重み（PRE:BEFORE = 0.6:0.4） |
| DYNAMIC | 動的重み（状況に応じて調整） |
| ADDITIVE | 加算方式（推奨：PRE + BEFORE差分） |
| GATED | ゲート方式（PRE拮抗時のみBEFORE使用） |

**加算方式の計算式**:
```
FINAL_SCORE = PRE_SCORE + (BEFORE_SCORE - 50.0) * before_factor
```

- `PRE_SCORE`: 事前情報スコア（0-100）
- `BEFORE_SCORE`: 直前情報スコア（0-100に正規化）
- `before_factor`: 直前情報の影響係数（デフォルト1.0）
- 50.0: ベースライン（中央値）

### 3. AdjustmentManager (`src/analysis/adjustment_manager.py`)

**目的**: 会場・天候・潮位補正を統一管理

**補正カテゴリ**:
- venue: 会場特性補正
- weather: 天候補正
- tide: 潮位補正
- compound: 複合条件補正（将来拡張用）

**補正範囲制限**:
- 単一補正: -20.0 ～ +20.0
- 合計補正: -30.0 ～ +30.0
- 最終スコア: 0.0 ～ 100.0

---

## モジュール間の関係

```
                           ┌─────────────────┐
                           │    RaceData     │
                           └────────┬────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │  PreInfoScorer  │ │BeforeInfoScorer │ │ PresetLoader    │
          │   (事前情報)     │ │  (直前情報)      │ │  (YAML設定)     │
          └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
                   │                   │                   │
                   ▼                   ▼                   │
          ┌──────────────────────────────────────┐        │
          │          ScoreIntegrator             │        │
          │  (PRE + BEFORE統合, 加算方式)         │        │
          └────────────────┬─────────────────────┘        │
                           │                              │
                           ▼                              │
          ┌──────────────────────────────────────┐        │
          │        AdjustmentManager             │◀───────┘
          │   (会場・天候・潮位補正, プリセット)   │
          └────────────────┬─────────────────────┘
                           │
                           ▼
          ┌──────────────────────────────────────┐
          │          Final Score                 │
          │    (補正履歴完全トレース可能)         │
          └──────────────────────────────────────┘
```

---

## 旧システムとの互換性

### フィーチャーフラグ

`config/feature_flags.py` に以下のフラグを追加済み:

```python
'prediction_engine_v2': False,      # V2エンジン有効化
'preset_based_adjustment': False,   # プリセットベース補正
'adjustment_tracing': False,        # 補正履歴トレース
```

### 段階的移行手順

1. **フラグOFF**: 旧システム（race_predictor.py）を使用
2. **フラグON**: 新システム（PreInfoScorer + ScoreIntegrator + AdjustmentManager）を使用
3. **バックテスト**: 両システムの結果を比較し、精度を検証
4. **本番切り替え**: 検証後にフラグをONに

---

## テスト結果

### ScoreIntegrator テスト

| ケース | PRE | BEFORE | FIXED | ADDITIVE |
|--------|-----|--------|-------|----------|
| PRE優勢 | 75.0 | 50.0 | 62.4 | 68.5 |
| BEFORE優勢 | 50.0 | 90.0 | 61.3 | 78.3 |
| 均等 | 60.0 | 60.0 | 56.9 | 62.2 |

### PreInfoScorer 構造確認

- 最大合計（正のみ）: 100.0点
- F/Lペナルティ: 最大-10.0点
- 事前情報のみで構成（直前情報を含まない）

---

## 今後の課題

### Phase 4: 最適化システムの構築

1. **グリッドサーチ最適化**
   - 補正値の最適パラメータ探索
   - バックテストとの連携

2. **ベイズ最適化**
   - 効率的なパラメータ探索
   - 過学習防止

3. **評価関数**
   - 回収率の最大化
   - 的中率55%以上の制約

---

## 関連ファイル

| ファイル | 説明 |
|----------|------|
| `src/analysis/pre_info_scorer.py` | 事前情報スコアラー（NEW） |
| `src/analysis/score_integrator.py` | スコア統合モジュール（NEW） |
| `src/analysis/adjustment_manager.py` | 補正統一管理（Phase 2） |
| `src/utils/preset_loader.py` | プリセットローダー（Phase 1） |
| `config/presets/*.yaml` | YAMLプリセット（Phase 1） |
| `config/feature_flags.py` | フィーチャーフラグ |
