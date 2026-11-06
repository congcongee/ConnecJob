"""청년 일자리 올인원 지원 서비스(ALIO) 공공기관 채용공시 API 수집 + 전처리.

API 키는 data/.env 의 ALIO_KEY 를 os.getenv 로 읽는다 (코드에 하드코딩 금지).
원본은 data/raw/alio_recruit.csv, 전처리 결과는 data/processed/alio_recruit.csv (utf-8-sig) 로 저장.

전처리 기준 (01_python ch11·ch13 방식)
- 429/5xx 는 재시도, resultCode 확인
- 영문 필드명 → 한글 열이름 (rename)
- 공고 시작/종료일 YYYYMMDD → 날짜형 (to_datetime)
- 줄바꿈(\\r\\n)·앞뒤 공백 정리, 빈 문자열 → 결측치
- 문자 결측치는 '정보없음' 으로 대체하고 대체 여부를 *_결측 플래그로 표시
- 상세조회에서만 채워지는 목록(files, steps)과 매일 바뀌는 D-day 는 제외
- 채용공시일련번호 기준 중복 제거
"""
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"
load_dotenv(DATA_DIR / ".env")
SERVICE_KEY = os.getenv("ALIO_KEY")

LIST_URL = "https://opendata.alio.go.kr/new/v1/recruit/list.do"
ONGOING_YN = "Y"   # 진행 중인 공고만. 마감 공고까지 받으려면 None (전체 약 11만 건)
NUM_OF_ROWS = 100
REQUEST_INTERVAL = 0.3


def request_post_with_retry(url, params, max_retries=5, base_delay=2.0, timeout=30):
    """429(요청 제한)/5xx 는 base_delay * 2^시도횟수 만큼 대기 후 재시도, 그 외 4xx 는 즉시 예외"""
    for attempt in range(max_retries):
        resp = requests.post(url, params=params, timeout=timeout)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(float(resp.headers.get("Retry-After", base_delay * 2 ** attempt)))
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"재시도 {max_retries}회 초과 (마지막 상태코드 {resp.status_code})")


def fetch_recruit_list(page_no):
    params = {"serviceKey": SERVICE_KEY, "pageNo": page_no, "numOfRows": NUM_OF_ROWS, "resultType": "json"}
    if ONGOING_YN:
        params["ongoingYn"] = ONGOING_YN
    js = request_post_with_retry(LIST_URL, params).json()
    if js.get("resultCode") != 200:
        raise RuntimeError(f"API 오류: {js.get('resultCode')} / {js.get('resultMsg')}")
    return js.get("result") or [], int(js.get("totalCount") or 0)


def collect_all():
    rows, page = [], 1
    while True:
        batch, total = fetch_recruit_list(page)
        rows += batch
        print(f"  {page}페이지 {len(rows):,}/{total:,}")
        if not batch or len(rows) >= total:
            break
        page += 1
        time.sleep(REQUEST_INTERVAL)
    return pd.DataFrame(rows)


RENAME = {
    "recrutPblntSn": "채용공시일련번호", "instNm": "기관명", "pblntInstCd": "공시기관코드",
    "pbadmsStdInstCd": "행정표준기관코드", "recrutPbancTtl": "채용공고제목", "srcUrl": "출처URL",
    "pbancBgngYmd": "공고시작일", "pbancEndYmd": "공고종료일", "ongoingYn": "진행여부",
    "recrutSe": "채용구분코드", "recrutSeNm": "채용구분", "hireTypeLst": "고용유형코드",
    "hireTypeNmLst": "고용유형", "workRgnLst": "근무지역코드", "workRgnNmLst": "근무지역",
    "acbgCondLst": "학력조건코드", "acbgCondNmLst": "학력조건", "ncsCdLst": "NCS코드",
    "ncsCdNmLst": "NCS분류", "recrutNope": "채용인원", "replmprYn": "대체인력여부",
    "aplyQlfcCn": "지원자격", "prefCondCn": "우대조건", "prefCn": "우대내용",
    "disqlfcRsn": "결격사유", "scrnprcdrMthdExpln": "전형절차",
}
DROP_COLS = ["files", "steps", "decimalDay", "nonatchRsn"]  # 상세조회 전용 빈 목록, 매일 바뀌는 D-day, 첨부 미첨부사유
FLAG_COLS = ["지원자격", "우대조건", "우대내용", "결격사유", "전형절차", "NCS분류"]


def preprocess(raw):
    df = raw.drop(columns=DROP_COLS, errors="ignore").rename(columns=RENAME)

    # 텍스트 정리: \r\n → \n, 앞뒤 공백 제거, 빈 문자열 → 결측치
    obj = df.select_dtypes("object").columns
    df[obj] = df[obj].apply(lambda s: s.str.replace("\r\n", "\n").str.strip()).replace("", np.nan)

    # 날짜 변환 : 문자열 YYYYMMDD -> 날짜형
    for c in ["공고시작일", "공고종료일"]:
        df[c] = pd.to_datetime(df[c].astype(str), format="%Y%m%d", errors="coerce")
    df["공고기간(일)"] = (df["공고종료일"] - df["공고시작일"]).dt.days

    # 결측치 : 임의 대체분은 *_결측 플래그로 표시한 뒤 '정보없음' 으로 대체
    for c in FLAG_COLS:
        df[f"{c}_결측"] = df[c].isna()
    df[obj.intersection(df.columns)] = df[obj.intersection(df.columns)].fillna("정보없음")

    df = df[[c for c in RENAME.values() if c in df.columns] + [c for c in df.columns if c not in RENAME.values()]]
    df = df.drop_duplicates(subset="채용공시일련번호")
    return df.sort_values("공고시작일", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    if not SERVICE_KEY:
        raise SystemExit("[중단] .env 에 ALIO_KEY 가 없습니다.")
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)

    raw = collect_all()
    raw.to_csv(RAW_DIR / "alio_recruit.csv", index=False, encoding="utf-8-sig")

    df = preprocess(raw)
    assert df["채용공시일련번호"].is_unique
    assert df["공고시작일"].notna().all(), "공고시작일 날짜 변환 실패 행 있음"
    df.to_csv(OUT_DIR / "alio_recruit.csv", index=False, encoding="utf-8-sig")

    print(f"원본 {raw.shape} → 전처리 {df.shape}")
    print("결측 대체 건수:", {c: int(df[f'{c}_결측'].sum()) for c in FLAG_COLS})
    print("남은 결측치:", int(df.isna().sum().sum()))
