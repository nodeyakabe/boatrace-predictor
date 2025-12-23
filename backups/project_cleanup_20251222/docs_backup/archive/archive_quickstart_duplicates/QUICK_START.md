# クイックスタートガイド

明日以降、このプロジェクトを再開する際の最速手順書

---

## 🚀 まず最初にやること（5分）

```bash
# 1. プロジェクトディレクトリに移動
cd c:\Users\seizo\Desktop\BoatRace

# 2. 仮想環境の有効化（Windowsの場合）
venv\Scripts\activate

# 3. 実験#021（全会場モデル）の結果確認
python -c "import os; print('完了' if os.path.exists('all_venues_output.log') else '未完了')"

# 4. ログファイルの確認
cat all_venues_output.log | grep "AUC\|会場\|完了"
```

---

## 📊 現在の最高性能モデル

### すぐに使えるベストモデル

```bash
# モデルファイル: models/stage2_optimized.json
# 性能: AUC 0.8496, 的中率(0.8+) 87.72%
```

### 予測の実行方法

```python
import xgboost as xgb
import pandas as pd

# モデル読み込み
model = xgb.XGBClassifier()
model.load_model("models/stage2_optimized.json")

# データ準備（適切な特徴量を用意）
X_new = prepare_features(df_new)  # 35個の特徴量

# 予測
y_pred = model.predict_proba(X_new)[:, 1]

# 高確率（0.8+）のレースを抽出
high_confidence = df_new[y_pred >= 0.8]
print(f"推奨レース: {len(high_confidence)}件")
```

---

## 🎯 今日やるべきこと（30分）

### オプションA: 完了確認と新実験（推奨）

```bash
# 1. 実験#021の結果確認（5分）
cat all_venues_output.log

# 2. TensorFlowインストール（5分）
pip install tensorflow

# 3. ディープラーニング実験実行（15分）
python train_deep_learning_model.py

# 4. 結果比較（5分）
echo "=== モデル性能比較 ==="
echo "実験#012 (XGB): AUC 0.8496"
echo "実験#020 (LGB): AUC 0.8492"
grep "AUC" train_deep_learning_output.log
```

### オプションB: ダッシュボード確認

```bash
# Streamlitアプリ起動
streamlit run src/ui/streamlit_app.py

# ブラウザで http://localhost:8501 を開く
```

### オプションC: オッズ戦略の復習

```bash
# オッズ期待値分析の結果確認
cat odds_output.log | grep "ROI\|戦略\|的中率"
```

---

## 📁 重要ファイルの場所

### モデルファイル
```
models/stage2_optimized.json          ⭐ ベストモデル
models/stage2_venue_07.json           会場07専用（AUC 0.9341）
models/stage2_venue_*.json            その他会場別
```

### スクリプト
```
train_stage2_optimized.py             ベストモデルの再学習
odds_value_analyzer.py                オッズ期待値分析
train_place_and_trifecta_models.py    複勝・3連単予測
```

### レポート
```
FINAL_COMPREHENSIVE_REPORT.md         ⭐ 総合レポート（60ページ）
PROJECT_STATUS_AND_NEXT_STEPS.md      現状と次ステップ
```

---

## 💡 よくある質問

### Q1: 実験#021が完了したか確認するには？

```bash
# 方法1: ログファイルの末尾確認
tail -20 all_venues_output.log

# 方法2: "完了"の文字列を検索
grep "完了" all_venues_output.log
```

### Q2: 今すぐ予測を実行したい

```bash
# Streamlitダッシュボードを使うのが最速
streamlit run src/ui/streamlit_app.py
```

### Q3: 最新のデータで再学習したい

```python
# train_stage2_optimized.py の日付を変更
start_date = "2024-01-01"  # 開始日
end_date = "2024-10-31"    # 終了日

# 実行
python train_stage2_optimized.py
```

### Q4: どのモデルを使えばいい？

**用途別推奨**:
- **単勝予測**: `models/stage2_optimized.json` (AUC 0.8496)
- **複勝予測**: `train_place_and_trifecta_models.py` 実行後のモデル
- **会場07**: `models/stage2_venue_07.json` (AUC 0.9341)

---

## 🔄 定期的なメンテナンス

### 週次（10分）

```bash
# データベースの確認
python -c "
import sqlite3
import pandas as pd
conn = sqlite3.connect('data/boatrace.db')
print('レース総数:', pd.read_sql('SELECT COUNT(*) FROM races', conn).iloc[0,0])
print('最新日付:', pd.read_sql('SELECT MAX(race_date) FROM races', conn).iloc[0,0])
conn.close()
"
```

### 月次（1時間）

```bash
# 1. 最新データでの再学習
python train_stage2_optimized.py

# 2. バックテストの実行
python rolling_backtest.py  # 作成が必要

# 3. 性能モニタリング
python performance_monitor.py  # 作成が必要
```

---

## 🛠️ トラブルシューティング

### エラー: "command not found"

```bash
# 仮想環境が有効になっているか確認
which python

# 無効なら有効化
venv\Scripts\activate  # Windows
source venv/bin/activate  # Mac/Linux
```

### エラー: "No module named 'xgboost'"

```bash
# 必要なライブラリを再インストール
pip install -r requirements.txt

# またはYou個別インストール
pip install xgboost lightgbm scikit-learn pandas numpy
```

### エラー: "Database is locked"

```bash
# SQLiteファイルが開かれているか確認
# 開いているプログラムを閉じる、または再起動
```

---

## 📈 次の目標

### 短期（今週）
- [ ] 実験#021の結果確認
- [ ] ディープラーニング実験実行
- [ ] ダッシュボードの改善

### 中期（今月）
- [ ] 実オッズAPIの統合
- [ ] バックテスト期間の延長（6ヶ月）
- [ ] CatBoost、TabNetの追加

### 長期（3ヶ月）
- [ ] 実戦での検証（少額）
- [ ] リアルタイム監視システム
- [ ] 月ROI +10%の達成

---

## 🎓 学習リソース

### プロジェクト内
- [FINAL_COMPREHENSIVE_REPORT.md](FINAL_COMPREHENSIVE_REPORT.md) - 総合レポート
- [PROJECT_STATUS_AND_NEXT_STEPS.md](PROJECT_STATUS_AND_NEXT_STEPS.md) - 詳細な現状分析

### 外部リソース
- XGBoost: https://xgboost.readthedocs.io/
- LightGBM: https://lightgbm.readthedocs.io/
- Optuna: https://optuna.readthedocs.io/
- Streamlit: https://docs.streamlit.io/

---

## 🔑 重要な数値（覚えておくべき）

| 指標 | 値 | 備考 |
|------|-----|------|
| **ベストAUC** | 0.8496 | 実験#012 |
| **的中率(0.8+)** | 87.72% | 高確率帯 |
| **期待ROI** | 40-47% | オッズ戦略 |
| **複勝的中率(0.8+)** | 92.22% | 実験#018 |
| **実験回数** | 22回 | #001-#022 |
| **学習データ** | 57,343件 | 12ヶ月分 |

---

## ⚡ 超速リファレンス

```bash
# モデル再学習
python train_stage2_optimized.py

# ダッシュボード起動
streamlit run src/ui/streamlit_app.py

# オッズ分析
python odds_value_analyzer.py

# ディープラーニング
pip install tensorflow
python train_deep_learning_model.py

# データ確認
sqlite3 data/boatrace.db "SELECT COUNT(*) FROM races;"

# ログ確認
cat all_venues_output.log
cat place_trifecta_output.log
```

---

**このファイルをブックマークして、毎回ここから始めましょう！**
