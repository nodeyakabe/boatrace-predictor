# データダウンロード解決策の調査結果

**調査日**: 2024-10-30
**目的**: HTMLスクレイピングより高速なデータ取得方法の発見

---

## 調査結果サマリー

### 結論: **公式一括DLは実質不可**

理由:
1. mbrace.or.jpのレース結果・番組表DL → **2025年3月5日終了**
2. 公式LZHファイル → **選手期別成績のみ**（レース結果なし）
3. GitHubスクリプト → **2018年で更新停止**、mbrace依存で動作不可

---

## 詳細調査結果

### 1. BOATRACE公式ダウンロードページ

**URL**: https://www.boatrace.jp/owpc/pc/extra/data/download.html

**提供データ**:
- ✅ **選手期別成績**（ファン手帳）: LZH形式、2002年～2025年
  - 例: `/static_extra/pc_static/download/data/kibetsu/fan2410.lzh`
- ❌ **競走成績**（レース結果）: mbrace.or.jpにリンク → **サービス終了**
- ❌ **番組表**（出走表）: mbrace.or.jpにリンク → **サービス終了**

**判定**: **レース結果・出走表の一括DL不可**

---

### 2. mbrace.or.jp（サービス終了）

**URL**: http://www1.mbrace.or.jp/od2/

**提供されていたデータ**:
- 競走成績: `http://www1.mbrace.or.jp/od2/K/YYYYMM/kYYMMDD.lzh`
- 番組表: `http://www1.mbrace.or.jp/od2/B/YYYYMM/bYYMMDD.lzh`

**終了日**: 2025年3月5日

**判定**: ❌ **使用不可**

---

### 3. GitHub cstenmt/boatrace

**URL**: https://github.com/cstenmt/boatrace

**内容**:
- 公式サイトからLZHファイルをDL
- 選手データ、成績、レース結果をCSV化

**問題点**:
- 最終更新: 2018年1月4日（**6年以上前**）
- mbrace.or.jp依存 → **動作不可**
- Python 3.5（古い）

**判定**: ❌ **使用不可**（依存サービス終了）

---

### 4. Internet Archive（Wayback Machine）

**概要**: 過去のmbrace.or.jpページを確認

**調査方法**:
```bash
# Wayback Machine API
curl "https://web.archive.org/cdx/search/cdx?url=mbrace.or.jp/od2/K/*&output=json"
```

**可能性**:
- 🟡 過去データ（2024年以前）は取得できる可能性
- ❌ 最新データ（2024-2025）は取得不可

**判定**: 🟡 **過去データのみ限定的に使用可能**

---

## 代替案の評価

### 案A: 現在のHTTPスクレイピング継続 ⭐⭐⭐⭐⭐

**内容**: 現在の方法を最適化

**最適化**:
1. ✅ HTTPセッション最適化: 17%高速化（完了）
2. 🔄 selectolax移行: 50-70%高速化（実装中）
3. 🔄 並列HTTPリクエスト: さらに高速化

**最終目標**: 24時間 → **3-5時間**（85%削減）

**判定**: ⭐⭐⭐⭐⭐ **最も現実的**

---

### 案B: Wayback MachineでWayback Machineで過去データ補完 🟡

**内容**: 2024年以前のデータをWayback Machineから取得

**メリット**:
- 過去データの一括取得可能
- HTMLスクレイピング不要

**デメリット**:
- 最新データ（2024-2025）は取得不可
- 保存されていないページあり
- 取得に時間がかかる可能性

**判定**: 🟡 **補完的に使用可能**

---

### 案C: 有料データサービス 🟡

**候補**:
1. team-nave社 BRDB-API
   - **問題**: 2024年12月31日サポート終了
2. 他の競艇予想サイトのAPI
   - **問題**: 見つからず

**判定**: 🟡 **実用的な選択肢なし**

---

## 推奨アクション

### 即座に実行: selectolax移行 ⚡

**期待効果**: 24時間 → 7-12時間（50-70%削減）

**実装内容**:
1. BeautifulSoup → selectolax書き換え
2. HTMLパース時間: 5-8秒 → 0.5-1秒（8-10倍高速）
3. 1レースあたり: 33.96秒 → 10-15秒

**実装時間**: 4-6時間

---

### 並行実行: Wayback Machine調査（オプション）

**目的**: 2023年以前のデータを高速取得できるか確認

**調査対象**:
- mbrace.or.jp/od2/K/202301/ ～ 202312/
- 保存されているLZHファイルを確認

---

## 結論

### 一括DLによる大幅時短は不可能

**理由**:
1. mbrace.or.jpサービス終了
2. 公式DLはレース結果・出走表なし
3. 代替サービスなし

### 現実的な最適解

**selectolax移行 + HTTP最適化**で24時間 → **3-5時間**（85%削減）

**これが現時点での最速・最現実的な方法**

---

## 次のステップ

1. ✅ selectolaxインストール
2. 🔄 race_scraper.py を selectolax化
3. 🔄 result_scraper.py を selectolax化
4. 🔄 beforeinfo_scraper.py を selectolax化
5. 🔄 テスト実行で効果測定

---

**報告者**: Claude Code
**作成日**: 2024-10-30
**ステータス**: selectolax移行を推進
