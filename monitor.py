"""
주식 모니터링 자동화 스크립트
- 실시간 주가 조회 (pykrx)
- 네이버 금융 뉴스 크롤링
- DART 공시 (지분 변동) 조회
- 이메일 발송
"""

import os
import json
import requests
from datetime import datetime, timedelta
from pykrx import stock
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

# ─────────────────────────────────────────
# ✅ 설정 (여기만 수정하세요)
# ─────────────────────────────────────────

DART_API_KEY = os.environ.get("DART_API_KEY", "여기에_DART_API키_입력")

EMAIL_SENDER   = os.environ.get("EMAIL_SENDER", "보내는이메일@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "앱비밀번호_16자리")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER", "받는이메일@gmail.com")

# 모니터링 종목 (종목코드: 회사명)
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

# ─────────────────────────────────────────
# 1. 주가 조회
# ─────────────────────────────────────────

def get_stock_prices():
    today = datetime.today().strftime("%Y%m%d")
    yesterday = (datetime.today() - timedelta(days=5)).strftime("%Y%m%d")
    results = []

    for code, name in STOCKS.items():
        try:
            df = stock.get_market_ohlcv_by_date(yesterday, today, code)
            if df.empty:
                results.append({"name": name, "code": code, "error": "데이터 없음"})
                continue

            latest = df.iloc[-1]
            prev   = df.iloc[-2] if len(df) >= 2 else latest

            close      = int(latest["종가"])
            prev_close = int(prev["종가"])
            change     = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            volume     = int(latest["거래량"])

            results.append({
                "name":       name,
                "code":       code,
                "close":      close,
                "change":     change,
                "change_pct": round(change_pct, 2),
                "volume":     volume,
                "date":       df.index[-1].strftime("%Y-%m-%d"),
            })
        except Exception as e:
            results.append({"name": name, "code": code, "error": str(e)})

    return results


# ─────────────────────────────────────────
# 2. 네이버 뉴스 크롤링
# ─────────────────────────────────────────

def get_news(company_name, max_items=3):
    url = (
        "https://openapi.naver.com/v1/search/news.json"
        f"?query={requests.utils.quote(company_name)}&display={max_items}&sort=date"
    )
    # 네이버 API 키 없이도 동작하는 RSS 방식
    rss_url = f"https://finance.naver.com/item/news_search.naver?query={requests.utils.quote(company_name)}&sm=tab_itm.top"

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(rss_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".newsTitle a")[:max_items]
        news = []
        for item in items:
            title = item.get_text(strip=True)
            link  = "https://finance.naver.com" + item["href"] if item.get("href", "").startswith("/") else item.get("href", "")
            news.append({"title": title, "link": link})
        return news
    except Exception as e:
        return [{"title": f"뉴스 로딩 실패: {e}", "link": ""}]


# ─────────────────────────────────────────
# 3. DART 공시 조회 (지분 변동)
# ─────────────────────────────────────────

DART_CORP_CODES = {
    "180640": "00164779",  # 한진칼
    "046440": "00124693",  # 모빌리언스
    "347860": "00926717",  # 알체라
    "052770": "00132128",  # 아이톡시
    "289220": "00713007",  # 자이언트스텝
    "031430": "00108082",  # 신세계인터내셔날
    "042000": "00154509",  # 카페24
    "048530": "00126114",  # 인바디
    "139480": "00421072",  # 이마트
    "035760": "00096775",  # CJENM
    "253450": "00667793",  # 스튜디오드래곤
    "122870": "00356361",  # YG엔터테인먼트
    "000120": "00104830",  # CJ대한통운
    "006800": "00119690",  # 미래에셋증권
}

def get_dart_disclosures(days=1):
    """지분 변동 관련 공시 조회"""
    end_date   = datetime.today().strftime("%Y%m%d")
    start_date = (datetime.today() - timedelta(days=days)).strftime("%Y%m%d")

    all_disclosures = []

    # 지분 관련 보고서 유형
    report_types = [
        ("SPIT", "대량보유보고서"),   # 5% 이상 대량 보유
        ("ESPIT", "임원·주요주주 특수관계인 주식"),
    ]

    corp_codes = list(DART_CORP_CODES.values())

    for corp_code in corp_codes:
        stock_code = next((k for k, v in DART_CORP_CODES.items() if v == corp_code), "")
        name = STOCKS.get(stock_code, stock_code)

        url = "https://opendart.fss.or.kr/api/list.json"
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de":    start_date,
            "end_de":    end_date,
            "pblntf_ty": "B",   # B = 지분공시
            "page_count": 10,
        }

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("status") == "000" and data.get("list"):
                for item in data["list"]:
                    all_disclosures.append({
                        "company":   name,
                        "title":     item.get("report_nm", ""),
                        "date":      item.get("rcept_dt", ""),
                        "submitter": item.get("flr_nm", ""),
                        "link":      f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no','')}",
                    })
        except Exception as e:
            pass  # API 오류 시 건너뜀

    return all_disclosures


# ─────────────────────────────────────────
# 4. HTML 이메일 조합
# ─────────────────────────────────────────

def build_html(prices, disclosures):
    today_str = datetime.today().strftime("%Y년 %m월 %d일")

    # 주가 테이블
    price_rows = ""
    for p in prices:
        if "error" in p:
            price_rows += f"<tr><td>{p['name']}</td><td colspan='4' style='color:#999'>{p['error']}</td></tr>"
            continue
        arrow  = "▲" if p["change"] >= 0 else "▼"
        color  = "#e63946" if p["change"] >= 0 else "#1d7ccd"
        sign   = "+" if p["change"] >= 0 else ""
        price_rows += f"""
        <tr>
          <td><b>{p['name']}</b><br><span style='color:#999;font-size:11px'>{p['code']}</span></td>
          <td style='text-align:right'>{p['close']:,}원</td>
          <td style='text-align:right;color:{color}'>{arrow} {sign}{p['change']:,}원</td>
          <td style='text-align:right;color:{color}'>{sign}{p['change_pct']}%</td>
          <td style='text-align:right;color:#999'>{p['volume']:,}</td>
        </tr>"""

    # 공시 섹션
    if disclosures:
        disc_rows = ""
        for d in disclosures:
            disc_rows += f"""
            <tr>
              <td><b>{d['company']}</b></td>
              <td><a href="{d['link']}" style='color:#1d7ccd'>{d['title']}</a></td>
              <td>{d['submitter']}</td>
              <td>{d['date']}</td>
            </tr>"""
        disc_section = f"""
        <h2 style='color:#222;margin-top:36px'>📋 지분 변동 공시</h2>
        <table style='width:100%;border-collapse:collapse;font-size:13px'>
          <tr style='background:#f4f4f4'>
            <th style='padding:8px;text-align:left'>회사</th>
            <th style='padding:8px;text-align:left'>공시 제목</th>
            <th style='padding:8px;text-align:left'>제출인</th>
            <th style='padding:8px;text-align:left'>일자</th>
          </tr>
          {disc_rows}
        </table>"""
    else:
        disc_section = "<p style='color:#999'>오늘 지분 변동 공시가 없습니다.</p>"

    html = f"""
    <html><body style='font-family:Apple SD Gothic Neo,Malgun Gothic,sans-serif;color:#222;max-width:700px;margin:auto;padding:20px'>
      <h1 style='font-size:20px;border-bottom:2px solid #222;padding-bottom:8px'>
        📈 주식 모니터링 리포트 — {today_str}
      </h1>

      <h2 style='color:#222;margin-top:28px'>💹 주가 현황</h2>
      <table style='width:100%;border-collapse:collapse;font-size:13px'>
        <tr style='background:#f4f4f4'>
          <th style='padding:8px;text-align:left'>종목</th>
          <th style='padding:8px;text-align:right'>종가</th>
          <th style='padding:8px;text-align:right'>전일대비</th>
          <th style='padding:8px;text-align:right'>등락률</th>
          <th style='padding:8px;text-align:right'>거래량</th>
        </tr>
        {price_rows}
      </table>

      {disc_section}

      <p style='color:#aaa;font-size:11px;margin-top:40px;border-top:1px solid #eee;padding-top:12px'>
        본 리포트는 자동 생성되었습니다. 주가 데이터: pykrx / 공시: DART OpenAPI
      </p>
    </body></html>
    """
    return html


# ─────────────────────────────────────────
# 5. 이메일 발송
# ─────────────────────────────────────────

def send_email(html_content):
    today_str = datetime.today().strftime("%Y-%m-%d")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📈 주식 모니터링 리포트 {today_str}"
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECEIVER
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    print(f"✅ 이메일 발송 완료 → {EMAIL_RECEIVER}")


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────

if __name__ == "__main__":
    print("📊 주가 조회 중...")
    prices = get_stock_prices()

    print("📋 DART 공시 조회 중...")
    disclosures = get_dart_disclosures(days=1)

    print("📧 이메일 작성 및 발송...")
    html = build_html(prices, disclosures)
    send_email(html)
    print("🎉 완료!")
