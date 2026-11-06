"""하이잡(haijob.co.kr) 채용공고별 자기소개서 문항 수집.

robots.txt 전체 허용, 이용약관에 자동수집 금지 조항 없음 (2026.10.28 확인).
목록(/list) 을 기업유형 필터로 훑어 공고 ID를 모으고, 공고 페이지(/posting/<id>)에
내장된 postingTasks JSON(직무별 문항·글자수)을 읽는다.
원본은 data/raw/cover_letter_questions.csv, 전처리 결과(공백 정리·중복 제거·문항유형 분류)는
data/processed/cover_letter_questions.csv (utf-8-sig) 로 저장.
"""
import json
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent.parent / "data"
BASE = "https://www.haijob.co.kr"
HEADERS = {"User-Agent": "ConnecJob-student-project/1.0 (personal study)"}
SLEEP = 1.0  # 서버 부담 완화

# 하이잡 기업유형 코드: 목록 필터 값 → 저장할 기업규모
COMPANY_TYPES = {"1": "대기업", "2": "외국계", "3": "공공기관", "5": "중소/중견"}
# 수집 대상: (기업유형, 직무코드 필터, 최대 공고 수). 직무코드 6=개발·데이터/IT, 5=마케팅 (TASKS 순번)
TARGETS = [
    ("1", [], 600), ("2", [], 600), ("3", [], 150),       # 전 직무
    ("1", ["6"], 600), ("3", ["6"], 300), ("5", ["6"], 500),  # IT·데이터 추가
    ("1", ["5"], 300), ("5", ["5"], 300),                  # (데이터)마케팅 추가
]
MIN_END = datetime(2026, 1, 1)  # 이 날짜 이후 마감 공고만

# 하이잡 코드 → 이름 (공고 페이지의 detailsInfo 와 동일)
TASKS = ["기획·전략/경영", "법무·사무·총무", "인사·HR", "회계·세무·재무", "마케팅·광고·홍보/MD",
         "개발·데이터/IT·인터넷", "디자인", "물류·무역·유통/자재", "운전·운송·배송", "영업·판매",
         "고객서비스·리테일/서비스", "엔지니어링·설계/연구개발", "제조·생산", "교육", "건축·건설",
         "의료·바이오", "미디어·문화·스포츠", "금융·보험", "공공기관/공공복지", "전문/특수직",
         "시설 관리·운영", "기타"]
HIRES = ["신입", "경력", "인턴", "계약"]


def get(path, params=None):
    r = requests.get(BASE + path, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(SLEEP)
    return r.text


def list_postings(ctype, tasks, limit):
    """기업유형(+직무) 필터의 공고 목록 → [(posting_id, 마감일)]"""
    q = json.dumps({"company": [ctype], "task": tasks, "hire": [], "region": []})
    out, page = [], 1
    while len(out) < limit:
        soup = BeautifulSoup(get("/list", {"q": q, "pageNo": page}), "html.parser")
        # end 가 빈 공고(상시채용)는 마감일 필터를 못 해서 제외
        items = [(a["href"].split("/")[-1], a["start"], a["end"]) for a in soup.select('[href^="/posting/"][end]') if a["end"]]
        if not items:
            break
        for pid, _, end in items:
            end_dt = datetime.fromtimestamp(int(end) / 1000)
            if end_dt >= MIN_END:
                out.append((pid, end_dt))
        if all(datetime.fromtimestamp(int(e) / 1000) < MIN_END for _, _, e in items):
            break  # 목록이 최신순이라 이후 페이지는 전부 오래된 공고
        page += 1
    return out[:limit]


def js_arg(script, prefix):
    """<script> 안 'const x = f('값')' 의 값 (공고 제목·직무 JSON 은 HTML 태그가 아니라 자바스크립트 변수로만 있음)"""
    return script.split(prefix, 1)[1].split("')", 1)[0] if prefix in script else None


def parse_posting(html):
    """공고 페이지 → (기업명, 공고제목, [직무 dict])"""
    soup = BeautifulSoup(html, "html.parser")
    company = soup.select_one("div.companyName")
    script = "\n".join(s.string or "" for s in soup.select("script"))
    title = js_arg(script, "const postingTitle = decodeURIComponent('")
    tasks = js_arg(script, "const postingTasks = parseEncodedStringifiedJSON('")
    if not (company and tasks):
        return None
    return (company.text.strip(),
            urllib.parse.unquote(title) if title else "",
            json.loads(urllib.parse.unquote(tasks)))


def classify(text, types):
    """판별키워드가 가장 많이 걸리는 문항유형 (shortcut: 키워드 일치율 약 75%, 정확도가 필요하면 LLM 분류로 교체)"""
    scores = {t: sum(k in text for k in kws) for t, kws in types.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "기타"


def code_name(names, code):
    i = int(code) - 1 if str(code).isdigit() else -1
    return names[i] if 0 <= i < len(names) else "정보없음"


def to_rows(pid, end_dt, size, parsed):
    """공고 하나 → 원본 행 (문항 텍스트는 손대지 않음)"""
    company, title, tasks = parsed
    return [{
        "posting_id": pid, "기업명": company, "기업규모": size, "공고제목": title,
        "직무": task.get("title", ""), "직무분류": code_name(TASKS, task.get("taskType")),
        "채용형태": code_name(HIRES, task.get("hireType")), "마감일": end_dt.date().isoformat(),
        "문항": item.get("name", ""), "글자수": item.get("limit"), "출처URL": f"{BASE}/posting/{pid}",
    } for task in tasks for item in task.get("applicationItems", [])]


def keep_removed(new, old):
    """이번 수집에 없는 이전 공고(하이잡에서 내려간 공고)의 원본 행을 남김"""
    return pd.concat([new, old[~old["posting_id"].isin(new["posting_id"])]], ignore_index=True)


def preprocess(raw, types):
    df = raw.copy()
    # 1) 공백 정리, 빈 문항 제거
    for c in ["직무", "문항"]:
        df[c] = df[c].fillna("").str.replace(r"\s+", " ", regex=True).str.strip()
    df = df[df["문항"] != ""]
    # 2) 같은 공고·직무에 채용형태만 다른 중복 문항 제거
    df = df.drop_duplicates(["posting_id", "직무", "문항"])
    # 3) 문항유형 분류 (문항 앞에 배치)
    df.insert(df.columns.get_loc("문항"), "문항유형", df["문항"].map(lambda q: classify(q, types)))
    df.insert(0, "q_id", [f"Q{i:05d}" for i in range(1, len(df) + 1)])
    return df.reset_index(drop=True)


def _selftest(types):
    html = ('<div class="companyName"> 테스트(주) </div><script>'
            "const postingTitle = decodeURIComponent('%EC%8B%A0%EC%9E%85');"
            "const postingTasks = parseEncodedStringifiedJSON('"
            + urllib.parse.quote(json.dumps([{"title": "백엔드", "taskType": "6", "hireType": "1",
                                              "applicationItems": [{"name": "지원한 이유와  입사 후 목표", "limit": 700}]}]))
            + "');</script>")
    rows = to_rows("1", datetime(2026, 1, 1), "대기업", parse_posting(html))
    assert rows == [{"posting_id": "1", "기업명": "테스트(주)", "기업규모": "대기업", "공고제목": "신입",
                     "직무": "백엔드", "직무분류": "개발·데이터/IT·인터넷", "채용형태": "신입", "마감일": "2026-01-01",
                     "문항": "지원한 이유와  입사 후 목표", "글자수": 700, "출처URL": f"{BASE}/posting/1"}], rows
    df = preprocess(pd.DataFrame(rows * 2), types)  # 중복 1건 제거 + 공백 정리
    assert df[["q_id", "문항유형", "문항"]].values.tolist() == [["Q00001", "지원동기·포부", "지원한 이유와 입사 후 목표"]]
    old = pd.DataFrame([{**rows[0], "posting_id": "2"}, {**rows[0], "문항": "옛 문항"}])
    assert keep_removed(pd.DataFrame(rows), old)["posting_id"].tolist() == ["1", "2"]  # 내려간 공고 2만 추가, 공고 1은 새 수집본


if __name__ == "__main__":
    t = pd.read_csv(DATA_DIR / "cover_letter_types.csv")
    types = dict(zip(t["문항유형"], t["판별키워드"].str.split("|")))
    _selftest(types)

    rows, failed = [], []
    seen = set()
    for ctype, tasks, limit in TARGETS:
        size = COMPANY_TYPES[ctype]
        postings = [p for p in list_postings(ctype, tasks, limit) if p[0] not in seen]
        print(f"[{size} / 직무 {','.join(code_name(TASKS, t) for t in tasks) or '전체'}] 새 공고 {len(postings)}건")
        for pid, end_dt in postings:
            seen.add(pid)
            try:
                parsed = parse_posting(get(f"/posting/{pid}"))
            except requests.RequestException as e:
                failed.append(pid)
                print(f"  {pid} 실패: {e}")
                continue
            if parsed:
                rows += to_rows(pid, end_dt, size, parsed)

    raw = pd.DataFrame(rows)
    raw_path = DATA_DIR / "raw" / "cover_letter_questions.csv"
    if raw_path.exists():
        n = raw["posting_id"].nunique()
        raw = keep_removed(raw, pd.read_csv(raw_path, dtype={"posting_id": str}))
        print(f"하이잡에서 내려간 이전 공고 {raw['posting_id'].nunique() - n}건 유지")
    (DATA_DIR / "raw").mkdir(exist_ok=True)
    (DATA_DIR / "processed").mkdir(exist_ok=True)
    raw.to_csv(raw_path, index=False, encoding="utf-8-sig")
    df = preprocess(raw, types)
    df.to_csv(DATA_DIR / "processed" / "cover_letter_questions.csv", index=False, encoding="utf-8-sig")
    print(f"원본 {raw.shape} → 전처리 {df.shape} | 공고 {df['posting_id'].nunique()}건, 기업 {df['기업명'].nunique()}곳, 실패 {len(failed)}건")
