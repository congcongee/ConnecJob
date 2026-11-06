"""민간 채용 사이트 공고 수집 (01_python ch14 두 방식).

- 인크루트 : 정적 웹크롤링 (requests + User-Agent + BeautifulSoup) - 목록·상세가 서버 렌더링 HTML
- 잡다     : 동적 웹크롤링 (selenium) - 카드를 클릭해야 오른쪽 패널에 공고 본문이 그려짐

수집 기준 (2026.11.04 robots.txt·이용약관 확인, 상세는 data/출처.txt)
- robots.txt 가 허용한 경로만 요청 (잡다 /api, 인크루트 jobpostcontpartner.asp 는 Disallow 라 호출 안 함)
- 사람 한 명 수준 : 요청 간격 1초 이상, 직종별 상한(INCRUIT_TARGETS)·잡다 MAX_POSTINGS 건, 429 를 받으면 즉시 중단
- 숨지 않음 : User-Agent 에 프로젝트명과 저장소 주소 표시, 차단(403)되면 우회하지 않고 중단
- 개인정보 제외 : 본문의 이메일·전화번호는 마스킹
- 원 서비스와 충돌하지 않게 : 결과는 분석용으로만 쓰고 공개 저장소에 올리지 않음 (.gitignore 의 private_*.csv)
  슈퍼루키는 봇 UA 를 403 으로 막고, 피플앤잡은 robots.txt 에서 일반 봇(*)을 Disallow 해서 제외

원본은 data/raw/private_{site}.csv, 전처리 결과는 data/processed/private_{site}.csv (utf-8-sig)
"""
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"

USER_AGENT = "Mozilla/5.0 (compatible; ConnecJob-study/0.1; +https://github.com/congcongee/ConnecJob)"
REQUEST_INTERVAL = 1.0
MAX_POSTINGS = 100  # 사이트별 상한 (DB 의 상당 부분을 가져가지 않도록)

INCRUIT_LIST = "https://job.incruit.com/jobdb_list/searchjob.asp"
INCRUIT_POST = "https://job.incruit.com/jobdb_info/jobpost.asp?job={}"
INCRUIT_CONT = "https://job.incruit.com/s_common/jobpost/jobpostcont.asp?job={}"  # 상세 페이지 iframe 본문
JOBDA_LIST = "https://www.jobda.im/position"
# 인크루트 직종 필터 (목록 주소 조건, 이름, 상한) : 데이터·AI·웹 대상 직무만 (data/job_group_dictionary.csv 묶음)
# 잡다는 직군 필터가 주소에 안 남고 체크해도 목록이 안 바뀌어 첫 화면 60건만 수집
INCRUIT_TARGETS = [
    ("occ2=632", "AI·빅데이터", 120),
    ("occ2=405", "데이터베이스·DBA", 60),
    ("occ2=583", "조사·분석·통계", 60),
    ("occ2=574", "웹개발자", 120),
    ("occ2=110", "마케팅", 120),
]

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"\b0\d{1,2}[-.)\s]?\d{3,4}[-.\s]?\d{4}\b")


def mask_contacts(text):
    return PHONE.sub("[전화번호]", EMAIL.sub("[이메일]", text)) if isinstance(text, str) else text


# ---------- 1) 정적 : 인크루트 ----------
def get_soup(session, url, max_retries=3):
    """타임아웃은 2·4·8초 쉬고 재시도, 403/429 는 재시도 없이 중단"""
    for attempt in range(max_retries):
        time.sleep(REQUEST_INTERVAL)
        try:
            resp = session.get(url, timeout=30)
            break
        except requests.exceptions.RequestException:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 * 2 ** attempt)
    if resp.status_code in (403, 429):
        raise RuntimeError(f"{resp.status_code} 응답 → 차단/요청 제한이라 수집 중단 ({url})")
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")  # content 로 넘겨 euc-kr 을 bs4 가 판별


def list_incruit(session, query, limit):
    """목록 페이지 → 카드 정보 (페이지 링크는 '?조건&page=N' 형식, '?page=N' 만 주면 '검색결과 없음' 카드 하나만 옴, 60건/페이지)"""
    rows = []
    for page in range(1, limit // 60 + 2):
        cards = get_soup(session, f"{INCRUIT_LIST}?{query}&page={page}").select("li.c_col")
        if not any(li.select_one('a[href*="jobpost.asp?job="]') for li in cards):
            break
        for li in cards:
            a = li.select_one('div.cell_mid a[href*="jobpost.asp?job="]')
            if a is None:
                continue
            rows.append({
                "공고ID": a["href"].split("job=")[-1],
                "기업명": li.select_one("a.cpname").get_text(strip=True),
                "제목": a.get_text(strip=True),
                "조건": " · ".join(s.get_text(strip=True) for s in li.select("div.cell_mid div.cl_md span")),
                "직무": li.select_one("div.cell_mid div.cl_btm").get_text(" ", strip=True),
                "마감": li.select_one("div.cell_last div.cl_btm span").get_text(strip=True),
            })
        if len(rows) >= limit:
            break
    return rows[:limit]


def collect_incruit():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    # 이미 받은 공고는 상세 요청을 다시 보내지 않고 이전 원본 행을 그대로 씀 (요청 수 줄이기)
    old_path = RAW_DIR / "private_incruit.csv"
    old = pd.read_csv(old_path, dtype=str) if old_path.exists() else pd.DataFrame(columns=["공고ID"])
    seen = set(old["공고ID"])
    rows = []
    for query, label, limit in INCRUIT_TARGETS:
        new = [r for r in list_incruit(session, query, limit) if r["공고ID"] not in seen]
        seen |= {r["공고ID"] for r in new}
        rows += [{**r, "수집직종": label} for r in new]
        print(f"  인크루트 [{label}] 새 공고 {len(new)}건")

    for i, r in enumerate(rows, 1):
        info = get_soup(session, INCRUIT_POST.format(r["공고ID"])).select_one("div.job_info_detail")
        items = [li.get_text(" ", strip=True) for li in info.select("li")] if info else []
        for key in ["고용형태", "경력", "근무지역", "학력", "급여조건"]:
            r[key] = next((t[len(key):].strip() for t in items if t.startswith(key)), np.nan)
        # 본문이 이미지뿐인 공고가 많아 텍스트가 있을 때만 남김 (iframe 문서의 title 만 있으면 결측)
        body = get_soup(session, INCRUIT_CONT.format(r["공고ID"])).body
        text = body.get_text("\n", strip=True) if body else ""
        r["본문"] = text if len(text) > len(r["제목"]) + 20 else np.nan
        r["출처URL"] = INCRUIT_POST.format(r["공고ID"])
        print(f"  인크루트 {i}/{len(rows)}")
    old["수집직종"] = old.get("수집직종", pd.Series(dtype=str)).fillna("전체")  # 첫 수집(2026.11.05)은 직종 필터 없이 '오늘 등록' 목록
    return pd.concat([old, pd.DataFrame(rows)], ignore_index=True)


# ---------- 2) 동적 : 잡다 ----------
def collect_jobda():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument(f"--user-agent={USER_AGENT}")
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    rows = []
    try:
        driver.get(JOBDA_LIST)
        time.sleep(3)  # 카드 목록이 그려질 때까지 대기
        cards = driver.find_elements(By.CSS_SELECTOR, "[class*='splitView_splitCard']")
        # 첫 카드는 처음부터 선택돼 있어 클릭해도 URL(positionSn)이 안 바뀜 → 두 번째 카드를 먼저 눌러 둠
        if len(cards) > 1:
            cards[1].find_element(By.TAG_NAME, "button").click()
            time.sleep(REQUEST_INTERVAL + 1)
        for i, card in enumerate(cards[:MAX_POSTINGS], 1):
            ps = card.find_elements(By.CSS_SELECTOR, "[class*='splitView_cardCompany'] p")
            card.find_element(By.TAG_NAME, "button").click()
            time.sleep(REQUEST_INTERVAL + 1)  # 패널 본문 로딩 대기 (클릭마다 공고 1건 요청)
            sn = re.search(r"positionSn=(\d+)", driver.current_url)
            panel = driver.find_element(By.CSS_SELECTOR, "[class*='splitView_detailPanel']")
            texts = [p.text for p in card.find_elements(By.CSS_SELECTOR, "p")]
            # 패널 뒤쪽 '○○를 소개합니다!' 기업정보는 모든 공고 공통이라 자르고, 본문이 이미지라 글이 거의 없으면 결측
            body = re.split(r"\n[^\n]*[을를] 소개합니다!", panel.text)[0]
            body = body if len(body) >= 150 else np.nan
            rows.append({
                "공고ID": sn.group(1) if sn else np.nan,
                "기업명": ps[0].text if ps else np.nan,
                "요약": ps[1].text if len(ps) > 1 else np.nan,  # '경력 · 생산관리 · 창원2공장'
                "제목": texts[2] if len(texts) > 2 else np.nan,
                "태그": card.find_element(By.CSS_SELECTOR, "[class*='splitView_cardTags']").text.replace("\n", " "),
                "지역": card.find_element(By.CSS_SELECTOR, "[class*='splitView_cardLocation']").text,
                "마감": card.find_element(By.CSS_SELECTOR, "[class*='splitView_cardClosing']").text.replace("\n", " "),
                "본문": body,
                "출처URL": f"{JOBDA_LIST}?positionSn={sn.group(1)}" if sn else np.nan,
            })
            print(f"  잡다 {i}/{min(len(cards), MAX_POSTINGS)}")
    finally:
        driver.quit()
    return pd.DataFrame(rows)


# ---------- 전처리 ----------
def preprocess(df):
    df = df.copy()
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].apply(lambda s: s.map(mask_contacts))
    # 본문은 줄바꿈을 살리고 연속 공백·빈 줄만 정리, 나머지 열은 한 줄로
    df["본문"] = df["본문"].str.replace(r"[ \t]+", " ", regex=True).str.replace(r"\n\s*\n+", "\n", regex=True).str.strip()
    other = [c for c in obj if c != "본문"]
    df[other] = df[other].apply(lambda s: s.str.replace(r"\s+", " ", regex=True).str.strip())
    df = df.replace("", np.nan)
    df["본문_결측"] = df["본문"].isna().map({True: "Y", False: "N"})
    df[obj] = df[obj].fillna("정보없음")
    return df.drop_duplicates("공고ID").reset_index(drop=True)


SITES = {"incruit": collect_incruit, "jobda": collect_jobda}


if __name__ == "__main__":
    assert mask_contacts("문의 hr@abc.co.kr / 02-123-4567, 010 1234 5678") == "문의 [이메일] / [전화번호], [전화번호]"
    for site in sys.argv[1:] or SITES:  # python collect_private_jobs.py jobda → 잡다만 다시 수집
        collect = SITES[site]
        print(f"== {site}")
        raw = collect()
        raw.to_csv(RAW_DIR / f"private_{site}.csv", index=False, encoding="utf-8-sig")
        df = preprocess(raw)
        df.to_csv(OUT_DIR / f"private_{site}.csv", index=False, encoding="utf-8-sig")
        assert df["공고ID"].is_unique and not df.astype(str).apply(lambda s: s.str.contains(EMAIL.pattern)).any().any()
        print(f"   원본 {raw.shape} → 전처리 {df.shape} | 본문 있음 {(df['본문_결측'] == 'N').sum()}건")
