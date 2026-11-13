"""검색 방식·임베딩 모델 비교 (07_LLM ch9.01 임베딩 모델 성능 비교 + ch9_14 TF-IDF 방식).
같은 평가셋(경험 20개 · 공고 110개 · 정답 eval_answers.csv)에서 '유사도만'으로 상위 10개를 뽑아 재현율@10 비교.
재순위·필터는 빼고 검색 단계만 비교 (recommend.py evaluate 의 '유사도만' 과 같은 기준).
  python compare_retrieval.py   → 표 출력 + data/eval_retrieval.csv
"""
import time

import numpy as np
import pandas as pd
from langchain_openai import OpenAIEmbeddings
from langchain_upstage import UpstageEmbeddings
from recommend import DATA_DIR, embed_text, experience_text

K = 10


def cosine_similarity(a, b):
    a = a / np.maximum(np.linalg.norm(a, axis=1, keepdims=True), 1e-12)
    b = b / np.maximum(np.linalg.norm(b, axis=1, keepdims=True), 1e-12)
    return a @ b.T


def char_ngrams(text, n_range=(2, 3)):
    """단어마다 앞뒤 공백을 붙여 글자 n-gram (sklearn TfidfVectorizer analyzer='char_wb' 와 같은 방식)"""
    out = []
    for w in text.lower().split():
        w = f" {w} "
        out += [w[i:i + n] for n in range(n_range[0], n_range[1] + 1) for i in range(len(w) - n + 1)]
    return out


class TfidfVectorizer:
    """shortcut: 'llm' conda 환경에 scikit-learn 이 없어 ch9_14 TfidfVectorizer(char_wb, sublinear_tf) 를 numpy 로 같은 식으로 구현
    (smooth idf = ln((1+N)/(1+df)) + 1, tf = 1 + ln(count), 행 L2 정규화), sklearn 이 있는 환경이면 그걸로 바꿔도 됨"""
    def fit(self, texts):
        grams = [set(char_ngrams(t)) for t in texts]
        self.vocab = {g: i for i, g in enumerate(sorted(set().union(*grams)))}
        df = np.zeros(len(self.vocab))
        for gs in grams:
            df[[self.vocab[g] for g in gs]] += 1
        self.idf = np.log((1 + len(texts)) / (1 + df)) + 1
        return self

    def transform(self, texts):
        m = np.zeros((len(texts), len(self.vocab)))
        for r, t in enumerate(texts):
            for g, c in pd.Series(char_ngrams(t)).value_counts().items():
                if g in self.vocab:
                    m[r, self.vocab[g]] = 1 + np.log(c)
        return m * self.idf


def load_eval():
    e = pd.read_csv(DATA_DIR / "eval_exps.csv", dtype=str).fillna("")
    j = pd.read_csv(DATA_DIR / "eval_jobs.csv", dtype=str).fillna("")
    a = pd.read_csv(DATA_DIR / "eval_answers.csv", dtype=str)
    docs = (j["채용제목"] + "\n" + j["모집직종"] + "\n" + j["직무내용"]).map(embed_text).tolist()
    queries = [experience_text([r]) for r in e.to_dict("records")]
    answers = dict(zip(a["exp_id"], a["relevant_job_ids"].str.split(";")))
    return e["exp_id"].tolist(), queries, j["job_id"].tolist(), docs, answers


def recall_at_k(sim, exp_ids, job_ids, answers, k=K):
    """sim[경험, 공고] → 경험별 재현율@k (정답이 k 개보다 많으면 k 로 나눔, recommend.evaluate 와 같음)"""
    out = []
    for i, exp in enumerate(exp_ids):
        top = {job_ids[t] for t in np.argsort(-sim[i])[:k]}
        want = set(answers[exp])
        out.append(len(want & top) / min(len(want), k))
    return np.array(out)


def tfidf_sim(queries, docs):
    """키워드 방식 기준선 : 글자 2~3-gram TF-IDF 코사인 (한국어는 조사·띄어쓰기 때문에 단어보다 글자 단위가 나음)"""
    vec = TfidfVectorizer().fit(docs + queries)
    return cosine_similarity(vec.transform(queries), vec.transform(docs))


def embed_sim(query_model, queries, docs, doc_model=None):
    doc_vec = np.array((doc_model or query_model).embed_documents(docs))
    q_vec = np.array(query_model.embed_documents(queries))
    return cosine_similarity(q_vec, doc_vec)


def _selftest():
    sim = np.array([[0.9, 0.1, 0.5], [0.1, 0.2, 0.9]])
    # E1 : 정답 {a,b}, 상위 1개 {a} → 1/min(2,1) = 1.0 / E2 : 정답 {b}, 상위 1개 {c} → 0
    assert list(recall_at_k(sim, ["E1", "E2"], ["a", "b", "c"], {"E1": ["a", "b"], "E2": ["b"]}, k=1)) == [1.0, 0.0]
    v = TfidfVectorizer().fit(["파이썬 개발", "자바 개발"])
    s = cosine_similarity(v.transform(["파이썬"]), v.transform(["파이썬 개발", "자바 개발"]))
    assert s[0, 0] > s[0, 1] and abs(cosine_similarity(s, s)[0, 0] - 1) < 1e-9


if __name__ == "__main__":
    _selftest()
    exp_ids, queries, job_ids, docs, answers = load_eval()
    methods = {
        "TF-IDF (키워드)": lambda: tfidf_sim(queries, docs),
        "Upstage embedding": lambda: embed_sim(UpstageEmbeddings(model="embedding-query"), queries, docs,
                                               UpstageEmbeddings(model="embedding-passage")),
        "OpenAI 3-small": lambda: embed_sim(OpenAIEmbeddings(model="text-embedding-3-small"), queries, docs),
        "OpenAI 3-large (채택)": lambda: embed_sim(OpenAIEmbeddings(model="text-embedding-3-large"), queries, docs),
    }
    rows, per_exp = [], {"exp_id": exp_ids}
    for name, run in methods.items():
        start = time.time()
        try:
            r = recall_at_k(run(), exp_ids, job_ids, answers)
        except Exception as err:  # 키가 없거나 호출 실패한 모델은 건너뛰고 나머지는 비교
            print(f"{name} 건너뜀 : {err}")
            continue
        per_exp[name] = r.round(2)
        rows.append({"방식": name, "재현율@10": round(r.mean(), 3), "재현율 0인 경험": int((r == 0).sum()),
                     "시간(초)": round(time.time() - start, 1)})
    res = pd.DataFrame(rows)
    print(res.to_string(index=False))
    print(pd.DataFrame(per_exp).to_string(index=False))
    res.to_csv(DATA_DIR / "eval_retrieval.csv", index=False, encoding="utf-8-sig")
