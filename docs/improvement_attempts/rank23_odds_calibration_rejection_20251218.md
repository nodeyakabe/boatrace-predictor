# rank23_odds_calibration 不採用報告

**検証日**: 2025-12-18
**担当**: Claude Code
**結論**: ❌ **不採用** - 2025年データで効果なし（モデルドリフト）

---

## 概要

2着・3着予測にオッズ情報を統合し、市場確率とMLモデル確率を組み合わせることで三連単的中率を改善する試み。

2024年データでは**+2.04pt**の改善効果が確認されたが、2025年データでは**±0.00pt（効果なし）**という結果となり、不採用とした。

---

## 実装内容

### アプローチ

1. **市場確率の計算**: 三連単オッズから2着・3着の市場確率を逆算
2. **エッジ検出**: `edge = model_prob / market_prob`
3. **スコア校正**: `adjusted_score = base_score × (1.0 + alpha × log(edge))`
4. **統合パラメータ**: `alpha=0.3`（緩やかな補正）

### 実装ファイル

- [`src/analysis/scorers/odds_calibrator.py`](../../src/analysis/scorers/odds_calibrator.py)
  - `OddsCalibrator` クラス
  - `calibrate_rank23_predictions()` メソッド

- [`src/analysis/race_predictor.py`](../../src/analysis/race_predictor.py) (lines 947-950)
  ```python
  if is_feature_enabled('rank23_odds_calibration'):
      predictions = self.odds_calibrator.calibrate_rank23_predictions(
          predictions, race_id, alpha=0.3
      )
  ```

- [`config/feature_flags.py`](../../config/feature_flags.py)
  - `rank23_odds_calibration`: False（無効化）

---

## 検証結果

### 2024年データ検証（49レース）

| 指標 | ベースライン | オッズ校正 | 差分 |
|------|--------------|------------|------|
| **三連単的中率** | 12.24% (6/49) | 14.29% (7/49) | **+2.04pt** ✅ |
| **1着的中率** | 51.02% | 51.02% | ±0.00pt |

- **判定**: [GOOD] 改善効果あり
- **検証日**: 2025-12-18

### 2025年データ検証（100レース）

| 指標 | ベースライン | オッズ校正 | 差分 |
|------|--------------|------------|------|
| **三連単的中率** | 7.00% (7/100) | 7.00% (7/100) | **±0.00pt** ❌ |
| **1着的中率** | 50.00% | 50.00% | ±0.00pt |

- **判定**: [NEUTRAL] 効果なし
- **検証日**: 2025-12-18
- **データ期間**: 2025-01-01 ~ 2025-12-10

---

## 不採用理由

### 1. **モデルドリフト**

2024年データで有効だった手法が、2025年データでは効果を失った。

**原因推定**:
- 市場環境の変化（2着・3着ベッティング市場の効率化）
- オッズ情報の精度向上により、MLモデルとの差が縮小
- 2025年のレース傾向変化

### 2. **追加複雑性に見合わない**

- オッズデータ取得のオーバーヘッド
- 校正ロジックの保守コスト
- 効果がない状態で複雑性だけが残る

### 3. **定期的再検証の必要性**

効果が年度によって変動するため、継続的なモニタリングが必要になるが、その労力に見合う改善効果がない。

---

## 教訓

### ✅ 良かった点

1. **段階的検証**: 1着→2着・3着と順を追って検証
2. **Opus AI活用**: 市場効率の分析に上位AIを活用
3. **feature_flag設計**: 安全な有効化・無効化が可能
4. **検証プロセス**: production_verification_rank23.py で本番コードと同じ検証

### ⚠️ 課題点

1. **時系列分割不足**: 2024年データのみで判断し、2025年データでの再検証が遅れた
2. **サンプル数**: 初回検証が49レースと少なかった（100レース以上推奨）
3. **モデルドリフト未考慮**: 市場環境変化への対応策がなかった

### 📝 今後への示唆

1. **年度別検証の重要性**: 過去データだけでなく、最新データでも必ず検証
2. **市場環境変化のモニタリング**: オッズ市場の効率性は変動する
3. **効果の持続性確認**: 導入後も定期的に効果測定が必要
4. **早期の再検証**: 新年度データが揃い次第、速やかに再検証

---

## 検証スクリプト

### 高速検証スクリプト（推奨）

[`scripts/quick_compare_odds_calibration.py`](../../scripts/quick_compare_odds_calibration.py)

**特徴**:
- RacePredictorを1回だけ初期化（高速化）
- feature_flagを動的に切り替え
- 100レース検証が約4分で完了

**実行方法**:
```bash
# 2025年データで100レース検証
python scripts/quick_compare_odds_calibration.py 100

# 2024年データで検証（オプション）
python scripts/quick_compare_odds_calibration.py 100 2024
```

### その他の検証スクリプト

- [`scripts/test_rank23_odds_calibration.py`](../../scripts/test_rank23_odds_calibration.py) - 基本検証
- [`scripts/measure_rank23_trifecta_improvement.py`](../../scripts/measure_rank23_trifecta_improvement.py) - 2024年データ検証
- [`scripts/production_verification_rank23.py`](../../scripts/production_verification_rank23.py) - 本番コード検証
- [`scripts/large_scale_rank23_verification.py`](../../scripts/large_scale_rank23_verification.py) - 大規模検証

---

## パフォーマンス問題と解決

### 問題: 検証に時間がかかる（100レースで10分以上）

**原因**:
1. RacePredictorを毎回初期化（ベースライン測定と本番測定で2回）
2. v1/v2/v3モデルのロード時間（1回約3秒）
3. beforeinfoモデルのロード時間

**解決策**:
- RacePredictorを1回だけ初期化
- feature_flagを動的に切り替え
- 処理時間: 10分 → 4分（60%削減）

**コード改善**:
```python
# ❌ 遅い方法（旧）
predictor_baseline = RacePredictor(DB_PATH)  # 初期化1回目
# ... ベースライン測定
predictor_calibrated = RacePredictor(DB_PATH)  # 初期化2回目
# ... 本番測定

# ✅ 速い方法（新）
predictor = RacePredictor(DB_PATH)  # 初期化1回のみ

set_feature_flag('rank23_odds_calibration', False)
# ... ベースライン測定

set_feature_flag('rank23_odds_calibration', True)
# ... 本番測定
```

---

## 関連ドキュメント

- [DAILY_REPORT_20251218.md](../DAILY_REPORT_20251218.md) - 実装・検証の詳細記録
- [odds_integration_rank23_results.md](../odds_integration_rank23_results.md) - 2024年検証結果
- [VERIFICATION_PROCESS_IMPROVEMENT_20251217.md](../VERIFICATION_PROCESS_IMPROVEMENT_20251217.md) - 検証プロセス改善

---

## まとめ

| 項目 | 内容 |
|------|------|
| **機能名** | rank23_odds_calibration |
| **目的** | 2着・3着予測にオッズ情報を統合し、三連単的中率を改善 |
| **2024年効果** | +2.04pt ✅ |
| **2025年効果** | ±0.00pt ❌ |
| **不採用理由** | モデルドリフトにより効果消失 |
| **feature_flag** | `rank23_odds_calibration: False` |
| **無効化日** | 2025-12-18 |
| **実装ファイル** | `src/analysis/scorers/odds_calibrator.py` |
| **検証スクリプト** | `scripts/quick_compare_odds_calibration.py` |

---

**重要**: 同様の「オッズ統合」アプローチは、今後検討する際も**必ず最新データで検証すること**。過去データの効果だけで判断せず、モデルドリフトの可能性を考慮する必要がある。
