"""서울 열린데이터광장 '서울시 일자리포털 채용정보' Open API(recMntList) 수집 + 전처리.

사람인·원티드·잡코리아 API 대신 쓰는 민간기업 채용공고 출처 (고용24 등록 공고, 전국 약 4만 건).
파일 데이터(raw/서울시 일자리포털 채용정보.csv)와 같은 38개 항목이 같은 순서로 오므로
열이름은 그 파일을 따르고 전처리는 preprocess_files.preprocess_seoul_jobs 를 그대로 쓴다.

인증키는 data/.env 의 SEOUL_KEY (data.seoul.go.kr 회원가입 → 인증키 신청, 개인 즉시 발급).
키가 없으면 샘플키로 5건만 받아 동작만 확인한다.
원본은 data/raw/seoul_jobs_api.csv, 전처리 결과는 data/processed/seoul_jobs_api.csv (utf-8-sig)
- 기존 seoul_jobs.csv(파일 데이터 88건)는 건드리지 않는다.
"""
import os
import time
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

from preprocess_files import preprocess_seoul_jobs

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
OUT_DIR = DATA_DIR / "processed"
load_dotenv(DATA_DIR / ".env")
KEY = os.getenv("SEOUL_KEY") or "sample"

URL = "http://openapi.seoul.go.kr:8088/{key}/json/recMntList/{start}/{end}/"
PAGE = 5 if KEY == "sample" else 1000  # 샘플키 최대 5건, 인증키 1회 최대 1000건
REQUEST_INTERVAL = 0.3

# API 필드 → 파일 데이터 열이름 (명세서 출력값 순서 = 파일 열 순서)
RENAME = {
    "COMPANY": "기업명", "TITLE": "채용제목", "CAREER": "경력", "REG_DT": "등록일자", "CLOSE_DT": "마감일자",
    "REGION": "근무지역", "STRTNM_CD": "근무지도로명주소코드", "MIN_EDUBG": "최소학력", "MAX_EDUBG": "최대학력",
    "IND_TP_CD_NM": "업종", "CORP_ADDR": "회사주소", "JOBS_NM": "모집직종", "JOB_CONT": "직무내용",
    "EMP_TP_NM": "고용형태", "COLLECT_PSNCNT": "모집인원", "SAL_TP_NM": "임금조건", "MAJOR": "전공",
    "CERTIFICATE": "자격면허", "MLTSVC_EXC_HOPE": "병역특례채용희망", "COMP_ABL": "컴퓨터활용능력",
    "PF_COND": "우대조건", "SEL_MTHD": "전형방법", "RCPT_MTHD": "접수방법", "SUBMIT_DOC": "제출서류준비물",
    "WORK_REGION": "근무예정지", "WORKDAY_WORKHR_CONT": "근무시간/형태", "FOUR_INS": "연금4대보험",
    "RETIREPAY": "퇴직금", "ETC_WELFARE": "기타복리후생", "JOBS_CD": "직종코드", "MIN_EDUBG_ICD": "최소학력코드",
    "MAX_EDUBG_ICD": "최대학력코드", "REGION_CD": "근무지역코드", "EMP_TP_CD": "고용형태코드",
    "ENTER_TP_CD": "근무형태코드", "SAL_TP_CD": "임금형태코드", "EMP_CHARGER_DPT": "채용부서", "CONTACT_TELNO": "전화번호",
}


def fetch(start, end, max_retries=5):
    """→ (행 목록, 전체 건수). ERROR-500/600 은 서버 일시 오류라 재시도, 그 외 오류코드는 즉시 예외"""
    for attempt in range(max_retries):
        r = requests.get(URL.format(key=KEY, start=start, end=end), timeout=30)
        r.raise_for_status()
        js = r.json()
        body = js.get("recMntList", js)
        code = body["RESULT"]["CODE"]
        if code in ("ERROR-500", "ERROR-600"):
            time.sleep(2.0 * 2 ** attempt)
            continue
        if code == "INFO-200":  # 해당 데이터 없음
            return [], 0
        if code != "INFO-000":
            raise RuntimeError(f"API 오류: {code} / {body['RESULT']['MESSAGE']}")
        return body["row"], int(body["list_total_count"])
    raise RuntimeError(f"재시도 {max_retries}회 초과 ({code})")


def collect_all():
    rows, start = [], 1
    while True:
        batch, total = fetch(start, start + PAGE - 1)
        rows += batch
        print(f"  {len(rows):,}/{total:,}")
        if not batch or len(rows) >= total or KEY == "sample":
            break
        start += PAGE
        time.sleep(REQUEST_INTERVAL)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    if KEY == "sample":
        print("[안내] .env 에 SEOUL_KEY 가 없어 샘플키로 5건만 받습니다.")
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)

    raw = collect_all().rename(columns=RENAME)[list(RENAME.values())]
    raw.to_csv(RAW_DIR / "seoul_jobs_api.csv", index=False, encoding="utf-8-sig")

    df = preprocess_seoul_jobs(raw.astype(str).replace("nan", ""))
    assert df["등록일자"].notna().all(), "등록일자 날짜 변환 실패 행 있음"
    assert df["최소임금"].notna().mean() >= 0.9, "임금 파싱 실패 행이 많음"
    df.to_csv(OUT_DIR / "seoul_jobs_api.csv", index=False, encoding="utf-8-sig")
    print(f"원본 {raw.shape} → 전처리 {df.shape} → seoul_jobs_api.csv | 남은 결측치 {df.isna().sum()[lambda s: s > 0].to_dict()}")
