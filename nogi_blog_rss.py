import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.nogizaka46.com"
FEED_BASE_URL = "https://kiki-o0.github.io/Nogizaka46_blog_rss/"

def get_active_member_ids():
    print("=== メンバーリストを自動取得しています ===")
    
    urls_to_check = [
        f"{BASE_URL}/s/n46/search/artist",
        f"{BASE_URL}/s/n46/diary/MEMBER"
    ]
    member_ids = set()
    
    for url in urls_to_check:
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            res.raise_for_status()
            
            patterns = [
                r'"code"\s*:\s*"?(\d{5})"?',
                r'/s/n46/artist/(\d{5})',
                r'[\?&]ct=(\d{5})'
            ]
            
            for p in patterns:
                for mid in re.findall(p, res.text):
                    if not mid.startswith("10") and mid != "00000":
                        member_ids.add(mid)
        except Exception as e:
            print(f"取得エラー({url}): {e}")
            
    member_list = sorted(list(member_ids))
    print(f"{len(member_list)}人のメンバーを検出しました: {member_list}")
    return member_list

def parse_date_to_iso(date_str):
    m = re.findall(r'\d+', date_str)
    if len(m) >= 3:
        year, month, day = m[0], m[1], m[2]
        hour = m[3] if len(m) >= 4 else "00"
        minute = m[4] if len(m) >= 5 else "00"
        second = m[5] if len(m) >= 6 else "00"
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}T{hour.zfill(2)}:{minute.zfill(2)}:{second.zfill(2)}+09:00"
    return datetime.now(timezone.utc).isoformat()

def parse_article(url):
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    
    title_tag = soup.find(class_="bd--ttl")
    title = title_tag.text.strip() if title_tag else "無題"

    date_tag = soup.find(class_="bd--d")
    detailed_date = date_tag.text.strip() if date_tag else ""

    name_tag = soup.find(class_="bd--prof__name")
    author = name_tag.text.strip() if name_tag else ""
            
    article = soup.find(class_="bd--edit")
    if not article:
        return title, author, "", detailed_date
        
    for img in article.find_all("img"):
        src = img.get("src", "")
        if not src:
            img.decompose()
            continue
            
        img_url = urljoin(BASE_URL, src)
        safe_url = escape(img_url)
        img_html = f'<p><a href="{safe_url}"><img src="{safe_url}" alt="公式ブログ画像"></a></p>'
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
                    elements.append("<p>" + escape(line) + "</p>")
                    
    return title, author, chr(10).join(elements), detailed_date

def generate_feed_for_member(member_id):
    list_url = f"{BASE_URL}/s/n46/diary/MEMBER/list?ct={member_id}"
    try:
        res = requests.get(list_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        res.raise_for_status()
    except Exception as e:
        print(f"[{member_id}] リスト取得エラー: {e}")
        return

    soup = BeautifulSoup(res.text, "html.parser")
    member_name = f"メンバー{member_id}"
    
    post_urls = []
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "/s/n46/diary/detail/" in href:
            full_url = urljoin(BASE_URL, href)
            # URLから「?ima=...」などの変動パラメータを削除して固定化する
            canonical_url = full_url.split('?')[0]
            if canonical_url not in post_urls:
                post_urls.append(canonical_url)
                
    if not post_urls:
        print(f"[{member_id}] 記事が見つかりません")
        return
        
    entries = []
    feed_updated = None
    
    for article_url in post_urls[:3]:
        print(f"  -> 記事取得中: {article_url}")
        try:
            title, author, content, detailed_date = parse_article(article_url)
        except Exception as e:
            print(f"記事取得エラー ({article_url}): {e}")
            continue
            
        time.sleep(1)
        
        if author and member_name == f"メンバー{member_id}":
            member_name = author
            
        entry_updated = parse_date_to_iso(detailed_date)
        
        if not feed_updated:
            feed_updated = entry_updated
        
        entry = f"""
  <entry>
    <title>{escape(title)}</title>
    <id>{escape(article_url)}</id>
    <link href="{escape(article_url)}"/>
    <updated>{escape(entry_updated)}</updated>
    <author>
      <name>{escape(member_name)}</name>
    </author>
    <content type="html"><![CDATA[
{content}
    ]]></content>
  </entry>"""
        entries.append(entry)

    if not entries:
        return
        
    if not feed_updated:
        feed_updated = datetime.now(timezone.utc).isoformat()
        
    feed_filename = f"feed_{member_id}.xml"
    feed_url = f"{FEED_BASE_URL}{feed_filename}"
    
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>乃木坂46｜{escape(member_name)} 公式ブログ</title>
  <id>{escape(feed_url)}</id>
  <updated>{escape(feed_updated)}</updated>
  <link href="{escape(feed_url)}" rel="self"/>{"".join(entries)}
</feed>
"""
    with open(f"feeds/{feed_filename}", "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[{member_id}] {member_name} のフィード生成完了 (feeds/{feed_filename})")

def main():
    print("=== 全メンバーのRSS生成を開始します ===")
    os.makedirs("feeds", exist_ok=True)
    
    member_ids = get_active_member_ids()
    if not member_ids:
        print("メンバーIDが取得できなかったため、処理を終了します。")
        return
        
    for member_id in member_ids:
        generate_feed_for_member(member_id)
        time.sleep(1)
        
    print("=== 全ての処理が完了しました ===")

if __name__ == "__main__":
    main()
