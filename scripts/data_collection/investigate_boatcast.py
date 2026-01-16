"""
BOATCAST サイトの構造調査スクリプト

使い方:
    python scripts/data_collection/investigate_boatcast.py

機能:
    - ページの構造を解析
    - APIエンドポイントを検出
    - データ形式を確認
"""

import asyncio
import json
from playwright.async_api import async_playwright
import sys
import os
from pathlib import Path

# Windows環境での文字化け対策
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


async def investigate_boatcast():
    """BOATCASTサイトを調査"""

    async with async_playwright() as p:
        # ブラウザを起動（ヘッドレスモードで）
        browser = await p.chromium.launch(headless=False)  # デバッグ用に表示
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()

        # ネットワークリクエストをキャプチャ
        network_requests = []
        api_requests = []

        async def handle_request(request):
            network_requests.append({
                'url': request.url,
                'method': request.method,
                'resource_type': request.resource_type
            })

        async def handle_response(response):
            url = response.url
            # APIっぽいリクエストを記録
            if any(keyword in url.lower() for keyword in ['api', 'json', 'data', 'tenji', 'replay', 'race']):
                try:
                    content_type = response.headers.get('content-type', '')
                    if 'json' in content_type.lower():
                        try:
                            data = await response.json()
                            api_requests.append({
                                'url': url,
                                'status': response.status,
                                'content_type': content_type,
                                'data': data
                            })
                        except:
                            api_requests.append({
                                'url': url,
                                'status': response.status,
                                'content_type': content_type,
                                'data': '(JSON parse error)'
                            })
                    else:
                        api_requests.append({
                            'url': url,
                            'status': response.status,
                            'content_type': content_type,
                            'data': '(not JSON)'
                        })
                except Exception as e:
                    print(f"Error handling response: {e}")

        page.on('request', handle_request)
        page.on('response', handle_response)

        print("=" * 80)
        print("BOATCAST サイト構造調査")
        print("=" * 80)

        # ページにアクセス
        url = 'https://race.boatcast.jp/replay?jo=01&md=T'
        print(f"\n[1] ページアクセス: {url}")

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            print("✓ ページ読み込み完了")

            # 少し待機（動的コンテンツの読み込み）
            await asyncio.sleep(5)

        except Exception as e:
            print(f"✗ ページ読み込みエラー: {e}")

        # ページタイトルを取得
        title = await page.title()
        print(f"\n[2] ページタイトル: {title}")

        # ページのHTML構造を確認
        print("\n[3] HTML構造の解析")

        # 展示関連の要素を探す
        tenji_elements = await page.query_selector_all('[class*="tenji"], [class*="exhibition"], [id*="tenji"], [id*="exhibition"]')
        print(f"   - 展示関連要素: {len(tenji_elements)}個")

        # データ要素を探す（JavaScriptで取得）
        try:
            data_elements_count = await page.evaluate('''() => {
                return document.querySelectorAll('[class], [id]').length;
            }''')
            print(f"   - 要素数: {data_elements_count}個")
        except:
            print(f"   - 要素数: (取得失敗)")

        # テーブル要素を探す
        tables = await page.query_selector_all('table')
        print(f"   - テーブル要素: {len(tables)}個")

        # 動画プレイヤーを探す
        video_elements = await page.query_selector_all('video, iframe')
        print(f"   - 動画/iframe要素: {len(video_elements)}個")

        # ネットワークリクエストの解析
        print(f"\n[4] ネットワークリクエスト解析")
        print(f"   - 総リクエスト数: {len(network_requests)}")

        # リソースタイプ別集計
        resource_types = {}
        for req in network_requests:
            rt = req['resource_type']
            resource_types[rt] = resource_types.get(rt, 0) + 1

        print("   - リソースタイプ別:")
        for rt, count in sorted(resource_types.items(), key=lambda x: x[1], reverse=True):
            print(f"     {rt}: {count}")

        # APIリクエストの詳細
        print(f"\n[5] 検出されたAPIリクエスト: {len(api_requests)}個")
        for i, api_req in enumerate(api_requests[:10], 1):  # 最初の10件
            print(f"\n   [{i}] {api_req['url']}")
            print(f"       Status: {api_req['status']}")
            print(f"       Content-Type: {api_req['content_type']}")
            if isinstance(api_req['data'], dict) or isinstance(api_req['data'], list):
                print(f"       Data keys: {list(api_req['data'].keys()) if isinstance(api_req['data'], dict) else 'list'}")

        # ページのローカルストレージとセッションストレージを確認
        print("\n[6] ストレージの確認")
        try:
            local_storage = await page.evaluate('() => Object.keys(localStorage)')
            session_storage = await page.evaluate('() => Object.keys(sessionStorage)')
            print(f"   - localStorage keys: {local_storage}")
            print(f"   - sessionStorage keys: {session_storage}")
        except Exception as e:
            print(f"   - ストレージ確認エラー: {e}")

        # ページのJavaScript変数を確認
        print("\n[7] グローバル変数の確認")
        try:
            global_vars = await page.evaluate('''() => {
                const vars = {};
                for (let key in window) {
                    if (window.hasOwnProperty(key) &&
                        !key.startsWith('webkit') &&
                        !key.startsWith('chrome') &&
                        typeof window[key] !== 'function') {
                        try {
                            const value = window[key];
                            if (typeof value === 'object' && value !== null) {
                                vars[key] = 'object';
                            } else {
                                vars[key] = typeof value;
                            }
                        } catch(e) {}
                    }
                }
                return vars;
            }''')

            interesting_vars = {k: v for k, v in global_vars.items()
                              if any(keyword in k.lower() for keyword in ['data', 'race', 'tenji', 'config', 'api'])}
            if interesting_vars:
                print("   - 興味深い変数:")
                for key, val in interesting_vars.items():
                    print(f"     {key}: {val}")
            else:
                print("   - データ関連の変数は見つかりませんでした")
        except Exception as e:
            print(f"   - グローバル変数確認エラー: {e}")

        # 結果をファイルに保存
        output_dir = project_root / 'temp' / 'investigation'
        output_dir.mkdir(parents=True, exist_ok=True)

        # スクリーンショットを保存
        screenshot_path = output_dir / 'boatcast_screenshot.png'
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"\n[8] スクリーンショット保存: {screenshot_path}")

        # HTMLを保存
        html_content = await page.content()
        html_path = output_dir / 'boatcast_page.html'
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[9] HTML保存: {html_path}")

        # 調査結果をJSONで保存
        report = {
            'url': url,
            'title': title,
            'elements': {
                'tenji_related': len(tenji_elements),
                'total_elements': data_elements_count if 'data_elements_count' in locals() else 0,
                'tables': len(tables),
                'video_iframe': len(video_elements)
            },
            'network': {
                'total_requests': len(network_requests),
                'resource_types': resource_types,
                'api_requests': api_requests[:20]  # 最初の20件
            }
        }

        report_path = output_dir / 'boatcast_investigation.json'
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"[10] 調査レポート保存: {report_path}")

        print("\n" + "=" * 80)
        print("調査完了")
        print("=" * 80)

        # ブラウザを閉じる前に少し待機
        print("\nブラウザを10秒後に閉じます...")
        await asyncio.sleep(10)

        await browser.close()


if __name__ == '__main__':
    asyncio.run(investigate_boatcast())
