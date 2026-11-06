"""하이잡 공고 직무명 ↔ 구인표준직무기술서 직종 연결 (TF-IDF 글자 n-gram 유사도).

입력 : processed/cover_letter_questions.csv (공고별 직무·직무분류), processed/job_desc_standard.csv, processed/job_ncs.csv
출력 : processed/posting_job.csv (utf-8-sig) - 공고·직무 한 줄당 가장 비슷한 직종 1개 (연결 못 하면 '정보없음')

1) 직무명 정리 : [태그]·(괄호) 제거, 신입·인턴·지역·전형 같은 직무와 무관한 말 제거, 영문 약어 → 한글 (IT → 정보기술)
   정리 후 남는 말이 없으면 연결하지 않음 ('일반전형 - 충북지역 - 3개월')
2) 직종 텍스트 : 직종명(3번 가중) + 표준직무내용 + 연결된 NCS 세분류명 (job_ncs.csv)
3) 하이잡 직무분류별로 허용한 NCS 대분류의 직종 안에서만 고름 (IT 공고가 간호사로 가는 것 방지)
shortcut: 글자 유사도 + 손으로 만든 영문 약어·분류 대응표, 정확도가 필요하면 임베딩 모델로 교체
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
MIN_SCORE = 0.1

EN = {"it": "정보기술 전산", "hr": "인사", "sw": "소프트웨어", "hw": "하드웨어", "ai": "인공지능", "r&d": "연구개발",
      "rnd": "연구개발", "qa": "품질", "qc": "품질", "md": "상품기획", "finance": "재무", "marketing": "마케팅",
      "marketer": "마케팅", "sales": "영업", "data": "데이터", "developer": "개발자", "engineer": "엔지니어",
      "design": "디자인", "designer": "디자이너", "backend": "백엔드 서버 개발", "frontend": "웹 프론트엔드 개발",
      "server": "서버", "security": "보안", "pm": "프로젝트 관리", "po": "서비스 기획", "ux": "디자인", "ui": "디자인",
      "legal": "법무", "accounting": "회계", "strategy": "전략 기획", "manager": "관리"}
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남",
           "경북", "경남", "제주", "충청", "전라", "경상", "수도권", "영남", "호남", "전국"]
GENERIC = {"일반", "신입", "경력", "주니어", "시니어", "사원", "인턴", "채용형", "체험형", "청년", "프로", "정규직", "계약직",
           "무기계약직", "채용", "모집", "분야", "직무", "공통", "본사", "제한경쟁", "사회형평", "보훈", "장애", "고졸",
           "대졸", "전문학사", "학사", "석사", "박사", "일근", "교대", *REGIONS}
GENERIC_END = re.compile(r".*(전형|지역|공장|사업장|지사|프로)|(영남|호남|수도|충청|강원)권|\d.*")  # '6급', '3개월' 은 숫자로 시작
# 하이잡 직무분류 → 허용 NCS 대분류 (없으면 전체 허용)
ALLOWED = {
    "금융·보험": ["금융·보험", "경영·회계·사무"],
    "기획·전략/경영": ["경영·회계·사무", "사업관리"],
    "건축·건설": ["건설", "환경·에너지·안전"],
    "물류·무역·유통/자재": ["경영·회계·사무", "운전·운송", "영업판매"],
    "영업·판매": ["영업판매", "경영·회계·사무"],
    "엔지니어링·설계/연구개발": ["기계", "전기·전자", "화학·바이오", "재료", "정보통신", "건설", "환경·에너지·안전",
                         "교육·자연·사회과학"],
    "제조·생산": ["기계", "전기·전자", "화학·바이오", "재료", "식품가공", "섬유·의복", "인쇄·목재·가구·공예", "환경·에너지·안전"],
    "회계·세무·재무": ["경영·회계·사무", "금융·보험"],
    "인사·HR": ["경영·회계·사무", "교육·자연·사회과학"],
    "디자인": ["문화·예술·디자인·방송", "섬유·의복", "건설"],
    "개발·데이터/IT·인터넷": ["정보통신", "전기·전자"],
    "마케팅·광고·홍보/MD": ["경영·회계·사무", "영업판매", "문화·예술·디자인·방송"],
    "법무·사무·총무": ["경영·회계·사무", "법률·경찰·소방·교도·국방"],
    "고객서비스·리테일/서비스": ["영업판매", "이용·숙박·여행·오락·스포츠", "음식서비스", "경영·회계·사무"],
    "의료·바이오": ["보건·의료", "화학·바이오"],
    "시설 관리·운영": ["건설", "전기·전자", "기계", "환경·에너지·안전", "경비·청소"],
    "교육": ["교육·자연·사회과학", "사회복지·종교"],
    "미디어·문화·스포츠": ["문화·예술·디자인·방송", "이용·숙박·여행·오락·스포츠"],
    "운전·운송·배송": ["운전·운송"],
}


def clean(name):
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", str(name))
    s = re.sub(r"[A-Za-z&]+", lambda m: " " + EN.get(m.group().lower(), m.group()) + " ", s)
    tokens = re.split(r"[\s_/·,\-]+", s)
    return " ".join(t for t in tokens if t and t not in GENERIC and not GENERIC_END.fullmatch(t))


def occupations(jd, jn):
    """직종별 텍스트와 대표 NCS 대분류"""
    occ = jd.groupby("직종")["표준직무내용"].apply(" ".join).to_frame("내용")
    occ["세분류"] = jn[jn["NCS세분류명"] != "정보없음"].groupby("직종")["NCS세분류명"].apply(lambda s: " ".join(s.unique()))
    occ = occ.fillna("")
    # 직종마다 연결된 대분류 전부 (원본이 섞여 있어 최빈값 하나로 정하면 '데이터 설계 및 프로그래머'가 '기계'가 됨)
    occ["대분류"] = jn.groupby("직종")["NCS대분류명"].agg(set).reindex(occ.index).map(lambda s: s if isinstance(s, set) else set())
    occ["텍스트"] = (occ.index.to_series() + " ") * 3 + occ["내용"] + " " + occ["세분류"]
    return occ


def link(texts, cats, occ):
    """→ (직종 이름 배열, 점수 배열), 연결 못 하면 '정보없음'·0"""
    # 가중치는 직종 텍스트로만 학습 (공고까지 넣으면 '영업·개발'처럼 공고에 흔한 말의 가중치가 낮아져 점수가 떨어짐)
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True).fit(occ["텍스트"])
    sim = linear_kernel(vec.transform(texts), vec.transform(occ["텍스트"]))
    masks = {cat: ~occ["대분류"].map(lambda s: bool(s & set(cats_ok))).to_numpy() for cat, cats_ok in ALLOWED.items()}
    for i, cat in enumerate(cats):
        if cat in masks:
            sim[i, masks[cat]] = 0
    sim[(texts.str.strip() == "").to_numpy()] = 0
    best, score = sim.argmax(1), sim.max(1)
    names = np.where(score >= MIN_SCORE, occ.index.to_numpy()[best], "정보없음")
    return names, np.where(score >= MIN_SCORE, score.round(3), 0)


def _selftest():
    assert clean("[그룹인재] 경영_HR_주니어프로") == "경영 인사"
    assert clean("채권관리 - 영남권") == "채권관리"
    assert clean("일반전형 - 충북지역 - 3개월") == ""
    assert clean("신입_SW 개발(일근)") == "소프트웨어 개발"
    occ = pd.DataFrame({"텍스트": ["웹 개발자 웹 개발자 프로그래밍", "일반 간호사 간호 환자"], "대분류": [{"정보통신"}, {"보건·의료"}]},
                       index=["웹 개발자", "일반 간호사"])
    names, _ = link(pd.Series(["웹 개발", "일반 간호", ""]), ["개발·데이터/IT·인터넷"] * 3, occ)
    assert names.tolist() == ["웹 개발자", "정보없음", "정보없음"]  # IT 공고는 간호사로 가지 않음, 빈 직무명은 연결 없음


if __name__ == "__main__":
    _selftest()
    c = pd.read_csv(OUT_DIR / "cover_letter_questions.csv")
    posts = c.drop_duplicates(["posting_id", "직무"])[["posting_id", "기업명", "기업규모", "직무", "직무분류"]].reset_index(drop=True)
    occ = occupations(pd.read_csv(OUT_DIR / "job_desc_standard.csv"), pd.read_csv(OUT_DIR / "job_ncs.csv"))

    text = posts["직무"].map(clean)
    text = text.where(text == "", text + " " + text + " " + posts["직무분류"].str.replace(r"[·/]", " ", regex=True))
    posts["직종"], posts["유사도"] = link(text, posts["직무분류"].tolist(), occ)
    posts.to_csv(OUT_DIR / "posting_job.csv", index=False, encoding="utf-8-sig")

    hit = posts["직종"] != "정보없음"
    print(f"공고·직무 {len(posts)}줄 중 {hit.sum()}줄 연결 ({hit.mean():.0%}), 직종 {posts.loc[hit, '직종'].nunique()}개 사용 → posting_job.csv")
    print(posts.groupby("기업규모")["직종"].apply(lambda s: f"{(s != '정보없음').mean():.0%}").to_dict())
