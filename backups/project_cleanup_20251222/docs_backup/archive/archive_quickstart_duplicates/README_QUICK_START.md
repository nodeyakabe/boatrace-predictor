# 🚤 競艇予測システム - クイックスタート

## 🎯 今すぐやること

### 1. 動作確認テスト（2分）
```bash
venv\Scripts\python.exe test_one_day_fetch.py
```
✅ 成功すれば次へ進む

### 2. 今晩のデータ収集実行（8〜10時間）
```bash
venv\Scripts\python.exe fetch_3months_with_details_tonight.py
```

---

## 📊 取得されるデータ

- **期間**: 2024年10月〜12月（3ヶ月）
- **対象**: 全24競艇場
- **レース数**: 約26,000レース

### 取得内容
- ✅ 出走表（選手、モーター、ボート）
- ✅ レース結果（着順、オッズ）
- ✅ 天気情報（気温、風、波）
- ✅ **展示タイム**（6艇分）
- ✅ **実際の進入コース**（6艇分）
- △ チルト角度（1艇のみ、要改善）
- ❌ 部品交換（未実装）

---

## 📁 重要ファイル

```
fetch_3months_with_details_tonight.py  ← 今晩実行
test_one_day_fetch.py                  ← 動作確認用
HANDOVER.md                            ← 詳細な引継ぎ資料
data/boatrace.db                       ← データベース
```

---

## 🔍 データ確認方法

### データベース確認
```bash
sqlite3 data/boatrace.db

# レース数
SELECT COUNT(*) FROM races;

# 展示タイム数
SELECT COUNT(*) FROM race_details WHERE exhibition_time IS NOT NULL;

# 進入コース数
SELECT COUNT(*) FROM race_details WHERE actual_course IS NOT NULL;
```

### UIで確認
```bash
venv\Scripts\streamlit.exe run ui/app.py
```
ブラウザで http://localhost:8501 を開く

---

## ⚠️ トラブルシューティング

### エラーが出たら

1. **データベースエラー**
   ```bash
   venv\Scripts\python.exe migrate_add_race_details.py
   ```

2. **ネットワークエラー**
   - 待機時間を長くする
   - インターネット接続を確認

3. **その他のエラー**
   - `HANDOVER.md` の「既知の問題」セクションを確認

---

## 📞 次にやること

データ収集完了後:

1. **結果確認**
   - 成功率
   - データベースの統計

2. **未実装機能の追加**
   - チルト角度（6艇分）
   - 部品交換
   - STタイム

3. **データ分析開始**
   - 選手の成績分析
   - 展示タイムと着順の相関
   - 進入コースと勝率の関係

詳細は `HANDOVER.md` を参照してください。

---

**作成日**: 2025年10月29日
