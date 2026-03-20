import os
import requests
from datetime import datetime, timedelta
from pykrx import stock
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

DART_API_KEY = os.environ.get("DART_API_KEY", "")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER", "")

STOCKS = {
    "180640": "한진칼",
    "046440": "모빌리언스",
    "347860": "알체라",
    "052770": "아이톡시",
    "289220": "자이언트스텝",
    "031430": "신세계인터내셔날",
    "042000": "카페24",
    "048530": "인바디",
    "139480": "이마트",
    "035760": "CJENM",
    "253450": "스튜디오드래곤",
    "122870": "YG엔터테인먼트",
    "000120": "CJ대한통운",
    "006800": "미래에셋증권",
}

DART_CORP_CODES = {
    "180640": "00983040",  # 한진칼
    "046440": "00405278",  # KG모빌리언스
    "347860": "01405451",  # 알체라
    "052770": "00346911",  # 아이톡시
    "289220": "01264438",  # 자이언트스텝
    "031430": "00234412",  # 신세계인터내셔날
    "042000": "00260879",  # 카페24
    "048530": "00269922",  # 인바디
    "139480": "00872984",  # 이마트
    "035760": "00265324",  # CJENM
    "253450": "01168684",  # 스튜디오드래곤
    "122870": "00613318",  # YG엔터테인먼트
    "000120": "00113410",  # CJ대한통운
    "006800": "00111722",  # 미래에셋증권
}

def get_stock_prices():
    today = datetime.today().strftime("%Y%m%d")
    start = (datetime.today() - timedelta(days=5)).strftime("%Y%m%d")
    results = []
    for code, name in STOCKS.items():
        try:
            df = stock.get_market_ohlcv_by_date(start, today, code)
            if df.empty:
                results.append({"name": name, "code": code, "error": "데이터 없음"})
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else latest
            close = int(latest["종가"])
            prev_close = int(prev["종가"])
            change = close - prev_close
            change_pct = round((change / prev_close * 100), 2) if prev_close else 0
            results.append({
                "name": name,
                "code": code,
                "close": close,
                "change": change,
                "change_pct": change_pct,
                "volume": int(latest["거래량"]),
                "date": df.index[-1].strftime("%Y-%m-%d"),
            })
        except Exception as e:
            results.append({"name": name, "code": code, "error": str(e)})
    return results

def parse_rss_date(date_str):
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return None

def fetch_news_rss(query, max_items=10):
    from datetime import timezone
    url = "https://news.google.com/rss/search?q=" + requests.utils.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")
        news = []
        for item in items:
            title = item.find("title").get_text(strip=True) if item.find("title") else ""
            link = item.find("link").get_text(strip=True) if item.find("link") else ""
            pub_date = item.find("pubDate").get_text(strip=True) if item.find("pubDate") else ""
            source = item.find("source").get_text(strip=True) if item.find("source") else ""
            dt = parse_rss_date(pub_date)
            if dt and dt < cutoff:
                continue
            if title:
                news.append({"title": title, "link": link, "date": pub_date, "source": source})
            if len(news) >= max_items:
                break
        return news
    except Exception:
        return []

def get_news_google(company_name, max_items=10):
    from datetime import timezone
    seen = set()
    all_news = []
    general = fetch_news_rss(company_name, max_items=max_items)
    for n in general:
        if n["title"] not in seen:
            seen.add(n["title"])
            all_news.append(n)
    thebell = fetch_news_rss(company_name + " 더벨", max_items=max_items)
    for n in thebell:
        if n["title"] not in seen:
            seen.add(n["title"])
            all_news.append(n)
    all_news.sort(key=lambda x: parse_rss_date(x["date"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return all_news[:max_items]

def get_all_news():
    all_news = {}
    for code, name in STOCKS.items():
        news = get_news_google(name, max_items=10)
        if news:
            all_news[name] = news
    return all_news

def get_dart_disclosures(days=1):
    end_date = datetime.today().strftime("%Y%m%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")
    all_disclosures = []
    for stock_code, corp_code in DART_CORP_CODES.items():
        name = STOCKS.get(stock_code, stock_code)
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "pblntf_ty": "B",
            "page_count": 10,
        }
        try:
            resp = requests.get("https://opendart.fss.or.kr/api/list.json", params=params, timeout=10)
            data = resp.json()
            if data.get("status") == "000" and data.get("list"):
                for item in data["list"]:
                    all_disclosures.append({
                        "company": name,
                        "title": item.get("report_nm", ""),
                        "date": item.get("rcept_dt", ""),
                        "submitter": item.get("flr_nm", ""),
                        "link": "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + item.get("rcept_no", ""),
                    })
        except Exception:
            pass
    return all_disclosures

KIND_ISUR_CODES = {
    "180640": "18064",
    "046440": "04644",
    "347860": "34786",
    "052770": "05277",
    "289220": "28922",
    "031430": "03143",
    "042000": "04200",
    "048530": "04183",
    "139480": "13948",
    "035760": "03576",
    "253450": "25345",
    "122870": "12287",
    "000120": "00012",
    "006800": "00680",
}

def get_kind_stock_issue(stock_code, company_name, days=1):
    today = datetime.today().strftime("%Y-%m-%d")
    start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
    isur_cd = KIND_ISUR_CODES.get(stock_code, stock_code[:5])
    repl_srt_cd = "A" + stock_code
    url = "https://kind.krx.co.kr/corpgeneral/stockissuelist.do"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://kind.krx.co.kr/corpgeneral/stockissuelist.do?method=loadInitPage",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
    }
    data = {
        "method": "searchStockIssueList",
        "pageIndex": "1",
        "currentPageSize": "15",
        "searchCodeType": "",
        "searchCorpName": stock_code,
        "orderMode": "1",
        "orderStat": "D",
        "replsuSrtCd": repl_srt_cd,
        "replsuCd": "",
        "forward": "searchStockIssueList",
        "searchMode": "",
        "bzProcsNo": "",
        "isurCd": isur_cd,
        "paxreq": "",
        "outsvcno": "",
        "marketType": "all",
        "comAbbrv": company_name,
        "listingType": "",
        "fromDate": start,
        "toDate": today,
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=10)
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table tbody tr")
        results = []
        for row in rows:
            cols = row.find_all("td")
            if len(cols) >= 6:
                list_date = cols[1].get_text(strip=True)
                list_type = cols[2].get_text(strip=True)
                shares = cols[3].get_text(strip=True)
                reason = cols[5].get_text(strip=True)
                link = ""
                onclick = row.get("onclick", "")
                if onclick:
                    import re
                    match = re.search(r"fnDetailView\('([^']+)'\)", onclick)
                    if match:
                        bz_no = match.group(1)
                        link = "https://kind.krx.co.kr/corpgeneral/stockissuelist.do?method=loadInitPage&bzProcsNo=" + bz_no
                if not link:
                    link = "https://kind.krx.co.kr/corpgeneral/stockissuelist.do?method=loadInitPage&searchCorpName=" + stock_code
                if list_date and list_type:
                    results.append({
                        "company": company_name,
                        "date": list_date,
                        "type": list_type,
                        "shares": shares,
                        "reason": reason,
                        "link": link,
                    })
        return results
    except Exception:
        return []

def get_all_kind_issues(days=1):
    all_issues = []
    for code, name in STOCKS.items():
        issues = get_kind_stock_issue(code, name, days=days)
        all_issues.extend(issues)
    return all_issues

def build_html(prices, disclosures, all_news, kind_issues):
    today_str = datetime.today().strftime("%Y년 %m월 %d일 %H:%M")

    price_rows = ""
    for p in prices:
        if "error" in p:
            price_rows += "<tr><td>{}</td><td colspan='4' style='color:#999'>{}</td></tr>".format(p["name"], p["error"])
            continue
        arrow = "▲" if p["change"] >= 0 else "▼"
        color = "#e63946" if p["change"] >= 0 else "#1d7ccd"
        sign = "+" if p["change"] >= 0 else ""
        price_rows += "<tr><td><b>{name}</b><br><span style='color:#999;font-size:11px'>{code}</span></td><td style='text-align:right'>{close:,}원</td><td style='text-align:right;color:{color}'>{arrow} {sign}{change:,}원</td><td style='text-align:right;color:{color}'>{sign}{pct}%</td><td style='text-align:right;color:#999'>{volume:,}</td></tr>".format(
            name=p["name"], code=p["code"], close=p["close"],
            color=color, arrow=arrow, sign=sign,
            change=abs(p["change"]), pct=p["change_pct"], volume=p["volume"]
        )

    if kind_issues:
        kind_rows = ""
        for k in kind_issues:
            company_cell = "<td><a href='{link}' style='color:#1d7ccd'><b>{company}</b></a></td>".format(**k)
            kind_rows += "<tr>" + company_cell + "<td>{date}</td><td>{type}</td><td style='text-align:right'>{shares}</td><td>{reason}</td></tr>".format(**k)
        kind_section = "<h2 style='color:#222;margin-top:36px'>KIND 주식발행내역 (증자/소각 등)</h2><table style='width:100%;border-collapse:collapse;font-size:13px;table-layout:fixed'><colgroup><col width='20%'><col width='20%'><col width='20%'><col width='20%'><col width='20%'></colgroup><tr style='background:#f4f4f4'><th style='padding:8px;text-align:left'>회사</th><th style='padding:8px;text-align:left'>상장(예정)일</th><th style='padding:8px;text-align:left'>상장방식</th><th style='padding:8px;text-align:right'>발행주식수</th><th style='padding:8px;text-align:left'>발행사유</th></tr>" + kind_rows + "</table>"
    else:
        kind_section = "<h2 style='color:#222;margin-top:36px'>KIND 주식발행내역 (증자/소각 등)</h2><p style='color:#999'>오늘 주식 발행 내역이 없습니다.</p>"

    news_section = "<h2 style='color:#222;margin-top:36px'>뉴스 (더벨 포함)</h2>"
    if all_news:
        for company, news_list in all_news.items():
            news_section += "<h3 style='color:#444;font-size:14px;margin-top:20px;margin-bottom:6px'>" + company + "</h3><table style='width:100%;border-collapse:collapse;font-size:12px'>"
            for n in news_list:
                if "더벨" in n["source"] or "thebell" in n["source"].lower():
                    badge = "<span style='background:#e63946;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px'>더벨</span>"
                else:
                    badge = "<span style='background:#888;color:#fff;font-size:10px;padding:1px 5px;border-radius:3px;margin-right:4px'>" + n["source"] + "</span>"
                news_section += "<tr><td style='padding:4px 0;border-bottom:1px solid #f0f0f0'>" + badge + "<a href='" + n["link"] + "' style='color:#1d7ccd;text-decoration:none'>" + n["title"] + "</a><br><span style='color:#aaa;font-size:10px'>" + n["date"] + "</span></td></tr>"
            news_section += "</table>"
    else:
        news_section += "<p style='color:#999'>오늘 관련 뉴스가 없습니다.</p>"

    if disclosures:
        disc_rows = ""
        for d in disclosures:
            disc_rows += "<tr><td><b>{company}</b></td><td><a href='{link}' style='color:#1d7ccd'>{title}</a></td><td>{submitter}</td><td>{date}</td></tr>".format(**d)
        disc_section = "<h2 style='color:#222;margin-top:36px'>DART 지분 변동 공시</h2><table style='width:100%;border-collapse:collapse;font-size:13px'><tr style='background:#f4f4f4'><th style='padding:8px;text-align:left'>회사</th><th style='padding:8px;text-align:left'>공시 제목</th><th style='padding:8px;text-align:left'>제출인</th><th style='padding:8px;text-align:left'>일자</th></tr>" + disc_rows + "</table>"
    else:
        disc_section = "<h2 style='color:#222;margin-top:36px'>DART 지분 변동 공시</h2><p style='color:#999'>오늘 지분 변동 공시가 없습니다.</p>"

    return "<html><body style='font-family:Malgun Gothic,sans-serif;color:#222;max-width:700px;margin:auto;padding:20px'><h1 style='font-size:20px;border-bottom:2px solid #222;padding-bottom:8px'>주식 모니터링 리포트 " + today_str + "</h1><h2 style='color:#222;margin-top:28px'>주가 현황</h2><table style='width:100%;border-collapse:collapse;font-size:13px'><tr style='background:#f4f4f4'><th style='padding:8px;text-align:left'>종목</th><th style='padding:8px;text-align:right'>종가</th><th style='padding:8px;text-align:right'>전일대비</th><th style='padding:8px;text-align:right'>등락률</th><th style='padding:8px;text-align:right'>거래량</th></tr>" + price_rows + "</table>" + kind_section + news_section + disc_section + "<p style='color:#aaa;font-size:11px;margin-top:40px;border-top:1px solid #eee;padding-top:12px'>자동 생성 리포트 | 주가: pykrx | 주식발행: KIND | 뉴스: Google News | 공시: DART</p></body></html>"

def send_email(html_content):
    today_str = datetime.today().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "주식 모니터링 리포트 " + today_str
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    print("이메일 발송 완료: " + EMAIL_RECEIVER)

if __name__ == "__main__":
    print("주가 조회 중...")
    prices = get_stock_prices()
    print("KIND 주식발행내역 조회 중...")
    kind_issues = get_all_kind_issues(days=1)
    print("뉴스 조회 중...")
    all_news = get_all_news()
    print("DART 공시 조회 중...")
    disclosures = get_dart_disclosures(days=1)
    print("이메일 발송 중...")
    html = build_html(prices, disclosures, all_news, kind_issues)
    send_email(html)
    print("완료!")
