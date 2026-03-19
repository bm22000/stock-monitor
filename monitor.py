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
    "180640": "00164779",
    "046440": "00124693",
    "347860": "00926717",
    "052770": "00132128",
    "289220": "00713007",
    "031430": "00108082",
    "042000": "00154509",
    "048530": "00126114",
    "139480": "00421072",
    "035760": "00096775",
    "253450": "00667793",
    "122870": "00356361",
    "000120": "00104830",
    "006800": "00119690",
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

def get_news_google(company_name, max_items=5):
    query = company_name + " 더벨"
    url = "https://news.google.com/rss/search?q=" + requests.utils.quote(query) + "&hl=ko&gl=KR&ceid=KR:ko"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:max_items]
        news = []
        for item in items:
            title = item.find("title").get_text(strip=True) if item.find("title") else ""
            link = item.find("link").get_text(strip=True) if item.find("link") else ""
            pub_date = item.find("pubDate").get_text(strip=True) if item.find("pubDate") else ""
            source = item.find("source").get_text(strip=True) if item.find("source") else ""
            news.append({"title": title, "link": link, "date": pub_date, "source": source})
        return news
    except Exception:
        return []

def get_all_news():
    all_news = {}
    for code, name in STOCKS.items():
        news = get_news_google(name, max_items=5)
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
    "048530": "04853",
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
            if len(cols) >= 5:
                date = cols[0].get_text(strip=True)
                issue_type = cols[1].get_text(strip=True)
                shares = cols[2].get_text(strip=True)
                face_value = cols[3].get_text(strip=True)
                reason = cols[4].get_text(strip=True)
                link_tag = row.find("a")
                link = ""
                if link_tag and link_tag.get("href"):
                    href = link_tag["href"]
                    if href.startswith("http"):
                        link = href
                    else:
                        link = "https://kind.krx.co.kr" + href
                if date and issue_type:
                    results.append({
                        "company": company_name,
                        "date": date,
                        "type": issue_type,
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
            if k.get("link"):
                company_cell = "<td><a href='{link}' style='color:#1d7ccd'><b>{company}</b></a></td>".format(**k)
            else:
                company_cell = "<td><b>{company}</b></td>".format(**k)
            kind_rows += "<tr>" + company_cell + "<td>{date}</td><td>{type}</td><td style='text-align:right'>{shares}</td><td>{reason}</td></tr>".format(**k)
        kind_section = "<h2 style='color:#222;margin-top:36px'>KIND 주식발행내역 (증자/소각 등)</h2><table style='width:100%;border-collapse:collapse;font-size:13px'><tr style='background:#f4f4f4'><th style='padding:8px;text-align:left'>회사</th><th style='padding:8px;text-align:left'>상장일</th><th style='padding:8px;text-align:left'>상장방식</th><th style='padding:8px;text-align:right'>발행주식수</th><th style='padding:8px;text-align:left'>발행사유</th></tr>" + kind_rows + "</table>"
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
