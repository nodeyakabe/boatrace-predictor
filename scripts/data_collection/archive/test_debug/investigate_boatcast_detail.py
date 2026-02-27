"""
BOATCAST サイトの詳細調査スクリプト（展示データの構造を特定）

使い方:
    python scripts/data_collection/investigate_boatcast_detail.py

機能:
    - 展示データの構造を解析
    - データの取得方法を特定
    - 各競艇場のデータフォーマットを確認
"""

import asyncio
import json
from playwright.async_api import async_playwright
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


async def investigate_tenji_data(page, venue_code):
    """展示データの構造を調査"""

    url = f'https://race.boatcast.jp/replay?jo={venue_code:02d}&md=T'
    print(f"\n{'='*80}")
    print(f"場コード {venue_code:02d} の展示データ調査")
    print(f"URL: {url}")
    print(f"{'='*80}")

    try:
        await page.goto(url, wait_until='networkidle', timeout=30000)
        await asyncio.sleep(3)

        # 展示関連の要素を詳細に調査
        print("\n[1] 展示関連要素の詳細調査")

        # テキストコンテンツを取得
        tenji_texts = await page.evaluate('''() => {
            const results = [];

            // 展示タイムや展示順位などのテキストを探す
            const patterns = ['展示', 'tenji', 'exhibition', 'タイム', '順位', 'ST'];

            document.querySelectorAll('*').forEach(el => {
                const text = el.textContent;
                const className = el.className || '';
                const id = el.id || '';

                for (const pattern of patterns) {
                    if (text && text.includes(pattern) && text.length < 200) {
                        results.push({
                            tag: el.tagName,
                            class: className,
                            id: id,
                            text: text.trim().substring(0, 100),
                            parent_class: el.parentElement ? el.parentElement.className : ''
                        });
                        break;
                    }
                }
            });

            return results.slice(0, 20);
        }''')

        if tenji_texts:
            print("   展示関連テキスト:")
            for i, item in enumerate(tenji_texts[:10], 1):
                print(f"   [{i}] {item['tag']} (class: {item['class'][:50]})")
                print(f"       Text: {item['text']}")
        else:
            print("   展示関連のテキストが見つかりません")

        # data属性を探す
        print("\n[2] data属性の調査")
        data_attrs = await page.evaluate('''() => {
            const results = [];
            document.querySelectorAll('[class*="tenji"], [class*="exhibition"], [class*="replay"]').forEach(el => {
                const attrs = {};
                for (const attr of el.attributes) {
                    if (attr.name.startsWith('data-')) {
                        attrs[attr.name] = attr.value;
                    }
                }
                if (Object.keys(attrs).length > 0) {
                    results.push({
                        tag: el.tagName,
                        class: el.className,
                        data_attrs: attrs,
                        text: el.textContent.trim().substring(0, 50)
                    });
                }
            });
            return results;
        }''')

        if data_attrs:
            print("   data属性付き要素:")
            for i, item in enumerate(data_attrs[:5], 1):
                print(f"   [{i}] {item['tag']}: {item['data_attrs']}")
        else:
            print("   data属性付き要素が見つかりません")

        # React/Vueコンポーネントを探す
        print("\n[3] JavaScriptフレームワークの検出")
        framework_info = await page.evaluate('''() => {
            const info = {
                react: !!window.React || !!document.querySelector('[data-reactroot], [data-reactid]'),
                vue: !!window.Vue || !!document.querySelector('[data-v-]'),
                angular: !!window.angular,
                jquery: !!window.jQuery
            };

            // Reactコンポーネントのpropsを探す
            if (info.react) {
                const reactEl = document.querySelector('[data-reactroot]');
                if (reactEl) {
                    const keys = Object.keys(reactEl);
                    info.reactKeys = keys.filter(k => k.startsWith('__react'));
                }
            }

            return info;
        }''')

        print(f"   React: {framework_info.get('react')}")
        print(f"   Vue: {framework_info.get('vue')}")
        print(f"   Angular: {framework_info.get('angular')}")
        print(f"   jQuery: {framework_info.get('jquery')}")

        # ページ内のJSONデータを探す
        print("\n[4] ページ内のJSONデータ検索")
        json_data = await page.evaluate('''() => {
            const results = [];

            // script タグ内のJSONを探す
            document.querySelectorAll('script[type="application/json"]').forEach(script => {
                try {
                    const data = JSON.parse(script.textContent);
                    results.push({
                        type: 'json_script',
                        id: script.id,
                        keys: Object.keys(data).slice(0, 10),
                        sample: JSON.stringify(data).substring(0, 200)
                    });
                } catch(e) {}
            });

            // window オブジェクトの中のデータ
            for (const key in window) {
                if (key.includes('data') || key.includes('config') || key.includes('tenji')) {
                    try {
                        const val = window[key];
                        if (typeof val === 'object' && val !== null && !val.nodeType) {
                            results.push({
                                type: 'window_var',
                                name: key,
                                keys: Object.keys(val).slice(0, 10)
                            });
                        }
                    } catch(e) {}
                }
            }

            return results;
        }''')

        if json_data:
            print("   検出されたJSONデータ:")
            for i, item in enumerate(json_data[:5], 1):
                print(f"   [{i}] {item['type']}: {item.get('id') or item.get('name')}")
                if 'keys' in item:
                    print(f"       Keys: {item['keys']}")
        else:
            print("   JSONデータが見つかりません")

        # ネットワークリクエストからAPIを探す
        print("\n[5] APIエンドポイントの検出")
        api_requests = []

        def handle_response(response):
            url = response.url
            if any(keyword in url.lower() for keyword in ['api', 'data', 'tenji', 'replay', 'race']):
                if 'boatcast.jp' in url:
                    api_requests.append({
                        'url': url,
                        'status': response.status,
                        'content_type': response.headers.get('content-type', '')
                    })

        page.on('response', handle_response)

        # ページをリロードしてAPIリクエストをキャプチャ
        await page.reload(wait_until='networkidle')
        await asyncio.sleep(2)

        if api_requests:
            print("   検出されたAPI:")
            for i, req in enumerate(api_requests[:10], 1):
                print(f"   [{i}] {req['url']}")
                print(f"       Status: {req['status']}, Type: {req['content_type']}")
        else:
            print("   APIエンドポイントが見つかりません")

        return {
            'venue_code': venue_code,
            'tenji_texts': tenji_texts[:10] if tenji_texts else [],
            'data_attrs': data_attrs[:5] if data_attrs else [],
            'framework': framework_info,
            'json_data': json_data[:5] if json_data else [],
            'api_requests': api_requests[:10] if api_requests else []
        }

    except Exception as e:
        print(f"   エラー: {e}")
        return None


async def main():
    """メイン処理"""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # 主要な競艇場をサンプル調査（桐生、戸田、浜名湖）
        venues = [1, 2, 18]  # 桐生、戸田、浜名湖
        results = []

        for venue in venues:
            result = await investigate_tenji_data(page, venue)
            if result:
                results.append(result)
            await asyncio.sleep(2)

        # 結果を保存
        output_dir = project_root / 'temp' / 'investigation'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / 'boatcast_tenji_detail.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*80}")
        print(f"詳細調査レポート保存: {output_path}")
        print(f"{'='*80}")

        print("\nブラウザを10秒後に閉じます...")
        await asyncio.sleep(10)

        await browser.close()


if __name__ == '__main__':
    asyncio.run(main())
