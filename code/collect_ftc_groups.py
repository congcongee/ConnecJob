"""공정거래위원회 기업집단포털 Open API 수집 + 전처리 (대기업집단 계열사 여부 판별용).

- 지정된 대규모기업집단 조회         (appnGroupSttusList)   → 집단명·코드·동일인·대표회사·계열회사 수·집단 구분
- 대규모기업집단 소속회사 재무현황   (financeCompSttusList) → 소속회사명·법인/사업자등록번호·자산·매출 등

API 키는 data/.env 의 DATA_GO_KR_KEY (공공데이터포털 인증키, 일반 인증키 Decoding 값) 를 os.getenv 로 읽는다.
원본은 data/raw/ftc_groups.csv, ftc_companies.csv
전처리 결과는 data/processed/ftc_companies.csv (utf-8-sig) : 소속회사 한 줄에 집단 정보(구분·공기업 여부)를 붙임

전처리 기준 (collect_alio.py 와 같은 방식)
- 429/5xx 는 재시도, resultCode 확인
- 영문 필드명 → 한글 열이름, 금액은 숫자형, 날짜 YYYYMMDD → 날짜형
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"
load_dotenv(DATA_DIR / ".env")
SERVICE_KEY = os.getenv("DATA_GO_KR_KEY")

GROUP_URL = "https://apis.data.go.kr/1130000/appnGroupSttusList/appnGroupSttusListApi"
COMPANY_URL = "https://apis.data.go.kr/1130000/financeCompSttusList/financeCompSttusListApi"
PRESENT_YM = "202605"  # 기업집단 지정년월 (공정위는 매년 5월 1일 지정), 결과가 0건이면 이전 해 '202505' 로
NUM_OF_ROWS = 100
REQUEST_INTERVAL = 0.3


def tag_text(soup, tag):
    el = soup.select_one(tag)
    return el.text.strip() if el else None


def request_get_with_retry(url, params, max_retries=5, base_delay=2.0, timeout=30):
    """429(요청 제한)/5xx 는 base_delay * 2^시도횟수 만큼 대기 후 재시도, 그 외 4xx 는 즉시 예외"""
    for attempt in range(max_retries):
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(float(resp.headers.get("Retry-After", base_delay * 2 ** attempt)))
            continue
        if resp.status_code >= 400:  # raise_for_status 는 URL(인증키 포함)을 메시지에 찍어서 본문 오류만 남김
            raise RuntimeError(f"HTTP {resp.status_code}: {tag_text(BeautifulSoup(resp.text, 'xml'), 'returnAuthMsg')}")
        return resp
    raise RuntimeError(f"재시도 {max_retries}회 초과 (마지막 상태코드 {resp.status_code})")


def fetch_page(url, page_no, key_field):
    """XML 응답 → (행 목록, 전체 건수). key_field 태그의 부모 요소를 한 행으로 본다 (01_python ch14 2.3 방식)"""
    params = {"ServiceKey": SERVICE_KEY, "pageNo": page_no, "numOfRows": NUM_OF_ROWS, "presentnYear": PRESENT_YM}
    soup = BeautifulSoup(request_get_with_retry(url, params).text, "xml")
    code = tag_text(soup, "resultCode")
    if code not in ("00", "0", "200"):
        raise RuntimeError(f"API 오류: {code} / {tag_text(soup, 'resultMsg')} / {tag_text(soup, 'returnAuthMsg')}")
    rows = [{c.name: c.text for c in k.parent.find_all(recursive=False)} for k in soup.select(key_field)]
    return rows, int(tag_text(soup, "totalCount") or 0)


def collect_all(url, key_field):
    rows, page = [], 1
    while True:
        batch, total = fetch_page(url, page, key_field)
        rows += batch
        print(f"  {page}페이지 {len(rows):,}/{total:,}")
        if not batch or len(rows) >= total:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return pd.DataFrame(rows)


GROUP_RENAME = {
    "unityGrupNm": "기업집단명", "unityGrupCode": "기업집단코드", "smerNm": "동일인", "repreCmpny": "대표회사",
    "sumCmpnyCo": "계열회사수", "invstmntLmtt": "집단구분", "entrprsCl": "공기업구분",
}
COMPANY_RENAME = {
    "unityGrupNm": "기업집단명", "entrprsNm": "회사명", "jurirno": "법인등록번호", "bizrno": "사업자등록번호",
    "rprsntvNm": "대표자명", "beforeBsnsStacntDe": "직전사업결산일자", "stacntDudt": "결산기일",
    "assetsTotamt": "자산총액", "caplAmount": "자본금", "caplTotamt": "자본총액", "debtTotamt": "부채총액",
    "selngAmount": "매출액", "thstrmNtpfAmount": "당기순이익", "entrprsOthbcDe": "기업공개일자",
}
AMOUNT_COLS = ["자산총액", "자본금", "자본총액", "부채총액", "매출액", "당기순이익"]


def preprocess(groups, companies):
    g = groups.rename(columns=GROUP_RENAME)[list(GROUP_RENAME.values())]
    c = companies.rename(columns=COMPANY_RENAME)
    obj = c.select_dtypes("object").columns
    c[obj] = c[obj].apply(lambda s: s.str.strip()).replace("", np.nan)
    c[AMOUNT_COLS] = c[AMOUNT_COLS].apply(lambda s: pd.to_numeric(s.str.replace(",", ""), errors="coerce"))
    c["기업공개일자"] = pd.to_datetime(c["기업공개일자"], format="%Y%m%d", errors="coerce")

    df = c.merge(g[["기업집단명", "기업집단코드", "집단구분", "공기업구분"]], on="기업집단명", how="left")
    df["상장여부"] = df["기업공개일자"].notna().map({True: "Y", False: "N"})
    str_cols = df.select_dtypes("object").columns
    df[str_cols] = df[str_cols].fillna("정보없음")
    return df.drop_duplicates(subset=["기업집단명", "회사명"]).reset_index(drop=True)


if __name__ == "__main__":
    if not SERVICE_KEY:
        raise SystemExit("[중단] data/.env 에 DATA_GO_KR_KEY 가 없습니다.")

    print("== 지정된 대규모기업집단")
    try:
        groups = collect_all(GROUP_URL, "unityGrupCode")
        groups.to_csv(RAW_DIR / "ftc_groups.csv", index=False, encoding="utf-8-sig")
    except RuntimeError as e:  # 활용신청 직후엔 서비스별로 키 반영이 늦을 수 있음 → 소속회사만 먼저 저장
        print(f"  [건너뜀] {e} → 집단구분·공기업구분 없이 저장, 키 반영 후 다시 실행")
        groups = pd.DataFrame(columns=list(GROUP_RENAME))
    print("== 소속회사 재무현황")
    companies = collect_all(COMPANY_URL, "entrprsNm")
    companies.to_csv(RAW_DIR / "ftc_companies.csv", index=False, encoding="utf-8-sig")

    df = preprocess(groups, companies)
    assert df["회사명"].ne("정보없음").all() and df["기업집단명"].ne("정보없음").all()
    if len(groups):
        assert df["기업집단코드"].ne("정보없음").mean() > 0.95, "집단명으로 집단 정보가 안 붙은 소속회사가 많음"
    df.to_csv(OUT_DIR / "ftc_companies.csv", index=False, encoding="utf-8-sig")
    print(f"집단 {len(groups)}개, 소속회사 원본 {companies.shape} → 전처리 {df.shape}")
    print(df["집단구분"].value_counts().to_dict())
