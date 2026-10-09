import os
import re
import time
import json
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.nogizaka46.com"
FEED_BASE_URL = "https://kiki-o0.github.io/Nogizaka46_blog_rss/"
STATE_FILE = "last_blogs.json"

MEMBER_MAPPING = {
    # 3期生
    "36749": "伊藤 理々杏",
    "36750": "岩本 蓮加",
    
    # 期別・スタッフ
    "40001": "新4期生",
    "40003": "運営スタッフ",
    "40004": "3期生",
    "40005": "4期生",
    "40007": "5期生",
    "40008": "6期生",
    
    # 4期生
    "48006": "遠藤 さくら",
    "48008": "賀喜 遥香",
    "48010": "金川 紗耶",
    "48013": "柴田 柚菜",
    "48015": "田村 真佑",
    "48017": "筒井 あやめ",
    
    # 新4期生
    "55383": "黒見 明香",
    "55385": "林 瑠奈",
    "55387": "弓木 奈於",
    
    # 5期生（五十音順）
    "55396": "五百城 茉央",
    "55397": "池田 瑛紗",
    "55390": "一ノ瀬 美空",
    "55389": "井上 和",
    "55401": "岡本 姫奈",
    "55392": "小川 彩",
    "55394": "奥田 いろは",
    "55400": "川﨑 桜",
    "55391": "菅原 咲月",
    "55393": "冨里 奈央",
    "55395": "中西 アルノ",
    
    # 6期生
    "63101": "愛宕 心響",
    "63102": "大越 ひなの",
    "63103": "小津 玲奈",
    "63104": "海邉 朱莉",
    "63105": "川端 晃菜",
    "63106": "鈴木 佑捺",
    "63107": "瀬戸口 心月",
    "63108": "長嶋 凛桜",
    "63109": "増田 三莉音",
    "63110": "森平 麗心",
    "63111": "矢田 萌華"
}

def parse_date_to_iso(date_str):
    m = re.findall(r'\d+', date_str)
    if len(m) >= 3:
        year, month, day = m[0], m[1], m[2]
        hour = m[3] if len(m) >= 4 else "00"
        minute = m[4] if len(m) >= 5 else "00"
        second = m[5] if len(m) >= 6 else "00"
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}T{hour.zfill(2)}:{minute.zfill(2)}:{second.zfill(2)}+09:00"
    return datetime.now(timezone.utc).isoformat()

def parse_article(fetch_url):
    response = requests.get(fetch_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    
    title = ""
    title_tag = soup.find(class_=["bd--ttl", "title", "entrytitle"])
    if title_tag:
        title = title_tag.get_text(strip=True)
        
    if not title:
        head_title = soup.find("title")
        if head_title:
            title = head_title.get_text(strip=True).split("|")[0].strip()
            
    if not title:
        title = "無題"

    # 日付抽出（必ず数字が含まれているタグだけを取得）
    detailed_date = ""
    for tag in soup.find_all(class_=["bd--d", "date", "bd--hd__date"]):
        text = tag.get_text(strip=True)
        if re.search(r'\d{4}', text):
            detailed_date = text
            break
            
    article = soup.find(class_=["bd--edit", "entrybody"])
    if not article:
        return title, "", detailed_date
        
    for img in article.find_all("img"):
        src = img.get("src", "")
        if not src:
            img.decompose()
            continue
            
        img_url = urljoin(BASE_URL, src)
        safe_url = escape(img_url)
        img_html = f'<p><a href="{safe_url}"><img src="{safe_url}" alt=""></a></p>'
        img.replace_with(f"__IMG_START__{img_html}__IMG_END__")
        
    elements = []
    raw_text = article.get_text(separator="\n", strip=True)
    parts = re.split(r'__IMG_START__(.*?)__IMG_END__', raw_text)
    
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
            
        if i % 2 == 1:
            elements.append(part)
        else:
            for line in part.split("\n"):
                line = line.strip()
                if line:
                    safe_line = escape(line)
                    linked_line = re.sub(r'(https?://[a-zA-Z0-9./?=_-]+)', r'<a href="\1" target="_blank">\1</a>', safe_line)
                    elements.append("<p>" + linked_line + "</p>")
                    
    return title, chr(10).join(elements), detailed_date

def generate_feed_for_member(member_id, state):
    member_name = MEMBER_MAPPING.get(member_id, f"メンバー{member_id}")
    
    list_url = f"{BASE_URL}/s/n46/diary/MEMBER/list?ct={member_id}&_={int(time.time())}"
    print(f"[{member_id}] [RSS取得中] {member_name} のブログ一覧にアクセスしています...")
    try:
        res = requests.get(list_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"[{member_id}] [エラー] リスト取得失敗: {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    
    post_urls = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "/s/n46/diary/detail/" in href:
            canonical_url = urljoin(BASE_URL, href).split('?')[0]
            if canonical_url not in post_urls:
                post_urls.append(canonical_url)
                
    for m in re.findall(r'/s/n46/diary/detail/(\d+)', res.text):
        canonical_url = f"{BASE_URL}/s/n46/diary/detail/{m}"
        if canonical_url not in post_urls:
            post_urls.append(canonical_url)
                
    if not post_urls:
        print(f"[{member_id}] [スキップ] {member_name} の新しい記事が見つかりません")
        return
        
    member_state = state.get(member_id, [])
    if not isinstance(member_state, list):
        print(f"[{member_id}] [警告] 古い形式の記憶を見つけたため、新しく作り直します。")
        member_state = []
        
    known_urls = { entry["url"]: entry for entry in member_state if isinstance(entry, dict) and "url" in entry }
    
    new_member_state = []
    feed_updated = None
    
    print(f"[{member_id}] [解析中] {member_name} の記事を処理します（最大15件）")
    
    for article_url in post_urls[:15]:
        if article_url in known_urls:
            known_data = known_urls[article_url]
            if "." not in known_data.get("updated", "") and "+09:00" in known_data.get("updated", ""):
                new_member_state.append(known_data)
                if not feed_updated:
                    feed_updated = known_data["updated"]
                print(f"  -> [高速スキップ] 既知の記事です: {known_data.get('title', '無題')}")
                continue
            else:
                print(f"  -> [修復取得中] 過去のタイムスタンプが不正なため再取得します: {article_url}")
        else:
            print(f"  -> [新規取得中] 記事URL: {article_url}")
            
        fetch_url = f"{article_url}?_={int(time.time())}"
        try:
            title, content, detailed_date = parse_article(fetch_url)
            print(f"     => [成功] タイトル: {title}")
        except Exception as e:
            print(f"     => [エラー] 記事解析失敗 ({article_url}): {e}")
            continue
            
        time.sleep(3)
            
        entry_updated = parse_date_to_iso(detailed_date)
        
        if not feed_updated:
            feed_updated = entry_updated
            
        new_member_state.append({
            "url": article_url,
            "title": title,
            "updated": entry_updated,
            "content": content
        })

    if not new_member_state:
        print(f"[{member_id}] [スキップ] 有効なブログ記事はありませんでした")
        return
        
    if not feed_updated:
        feed_updated = datetime.now(timezone.utc).isoformat()
        
    entries_xml = ""
    for entry_data in new_member_state:
        entries_xml += f"""
  <entry>
    <title>{escape(entry_data['title'])}</title>
    <id>{escape(entry_data['url'])}</id>
    <link href="{escape(entry_data['url'])}"/>
    <updated>{escape(entry_data['updated'])}</updated>
    <author>
      <name>{escape(member_name)}</name>
    </author>
    <content type="html"><![CDATA[
{entry_data['content']}
    ]]></content>
  </entry>"""
        
    feed_filename = f"feed_{member_id}.xml"
    feed_url = f"{FEED_BASE_URL}{feed_filename}"
    
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>乃木坂46｜{escape(member_name)} 公式ブログ</title>
  <id>{escape(feed_url)}</id>
  <updated>{escape(feed_updated)}</updated>
  <link href="{escape(feed_url)}" rel="self"/>{entries_xml}
</feed>
"""
    with open(f"feeds/{feed_filename}", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[{member_id}] [完了] {member_name} のフィード生成 (feeds/{feed_filename})")
    
    state[member_id] = new_member_state

def main():
    print("=== [処理開始] 全メンバーのRSS生成を開始します ===")
    os.makedirs("feeds", exist_ok=True)
    
    if os.path.exists(STATE_FILE):
        print("-> [読込] 過去のブログ履歴データを読み込みます...")
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception as e:
            print(f"-> [警告] 履歴ファイルの読み込みに失敗しました。新規で作成します: {e}")
            state = {}
    else:
        print("-> [読込] 過去の履歴がありません。新規で全取得します。")
        state = {}
        
    for member_id in MEMBER_MAPPING.keys():
        generate_feed_for_member(member_id, state)
        time.sleep(3)
        
    print(f"=== [保存] ブログ履歴データを {STATE_FILE} に保存します ===")
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"-> [エラー] 履歴ファイルの保存に失敗しました: {e}")
        
    print("=== [処理完了] 全てのRSS生成が正常に終了しました ===")

if __name__ == "__main__":
    main()
