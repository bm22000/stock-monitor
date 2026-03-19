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

def build_html(prices, disclosures):
    today_str = datetime.today().strftime("%Y%m%d %H:%M")
    price_rows = ""
    for p in prices:
        if "error" in p:
            price_rows += "<tr><td>{}</td><td colspan='4' style='
