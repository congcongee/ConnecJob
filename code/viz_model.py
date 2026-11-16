"""모델 부분 발표용 그림 (data/eda/08~10).
  08_embedding_map.png   : 벡터DB 공고 528건 임베딩을 PCA 2차원으로 → 직무묶음별로 모이는지
  09_similarity_dist.png : 평가셋 경험-공고 유사도, 정답 쌍 vs 오답 쌍 분포 → 최소 점수 컷을 안 쓴 근거
  10_recall_by_exp.png   : 경험 20개별 재현율@10, TF-IDF vs text-embedding-3-large
실행 : python viz_model.py (OpenAI 임베딩 약 130건 호출, 공고 528건은 벡터DB 에 저장된 값 사용)
"""
import chromadb
import matplotlib.pyplot as plt
import numpy as np
from langchain_openai import OpenAIEmbeddings

from compare_retrieval import cosine_similarity, load_eval, recall_at_k, tfidf_sim
from recommend import DATA_DIR

plt.rc("font", family="Malgun Gothic")
plt.rc("axes", unicode_minus=False)
OUT = DATA_DIR / "eda"
BLUE, DEEP, MID, LIGHT, YELLOW, GRAY = "#1F06AC", "#0A2463", "#0F42C0", "#5882E8", "#E3EF4F", "#9C98AE"


def pca2(x):
    """평균을 빼고 SVD 로 첫 두 주성분 좌표 (sklearn PCA 와 같은 계산)"""
    x = x - x.mean(axis=0)
    u, s, _ = np.linalg.svd(x, full_matrices=False)
    return u[:, :2] * s[:2], s[:2] ** 2 / (s ** 2).sum()


def embedding_map():
    g = chromadb.PersistentClient(path=str(DATA_DIR / "chroma")).get_collection("postings").get(include=["embeddings", "metadatas"])
    xy, ratio = pca2(np.array(g["embeddings"]))
    first = np.array([m["직무묶음"].split(";")[0] for m in g["metadatas"]])
    groups, counts = np.unique(first, return_counts=True)
    top = [groups[i] for i in np.argsort(-counts)[:6]]
    colors = dict(zip(top, [BLUE, "#E07A1F", MID, "#2A9D8F", "#C0392B", "#8E44AD"]))
    fig, ax = plt.subplots(figsize=(9, 6.2))
    rest = ~np.isin(first, top)
    ax.scatter(xy[rest, 0], xy[rest, 1], s=14, c="#CFCBBE", label="그 외 직무")
    for gname in top:
        m = first == gname
        ax.scatter(xy[m, 0], xy[m, 1], s=18, c=colors[gname], label=f"{gname} ({m.sum()})", alpha=0.85)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_xlabel(f"주성분 1 ({ratio[0]:.0%})"); ax.set_ylabel(f"주성분 2 ({ratio[1]:.0%})")
    ax.set_title(f"공고 {len(first)}건 임베딩(3,072차원) → 2차원 PCA, 색 = 첫 번째 직무묶음")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1), frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "08_embedding_map.png", dpi=150, bbox_inches="tight")


def similarity_and_recall():
    exp_ids, queries, job_ids, docs, answers = load_eval()
    emb = OpenAIEmbeddings(model="text-embedding-3-large")
    sim = cosine_similarity(np.array(emb.embed_documents(queries)), np.array(emb.embed_documents(docs)))
    hit = np.array([[j in set(answers[e]) for j in job_ids] for e in exp_ids])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    bins = np.linspace(sim.min(), sim.max(), 40)
    ax.hist(sim[~hit], bins=bins, color=GRAY, alpha=0.7, density=True, label=f"정답 아닌 쌍 ({(~hit).sum():,})")
    ax.hist(sim[hit], bins=bins, color=BLUE, alpha=0.75, density=True, label=f"정답 쌍 ({hit.sum()})")
    ax.axvline(np.median(sim[hit]), color=BLUE, ls="--")
    ax.axvline(np.median(sim[~hit]), color="#45425A", ls="--")
    ax.set_xlabel("경험-공고 코사인 유사도"); ax.set_yticks([])
    ax.set_title("평가셋 유사도 분포 — 정답 쌍이 더 높지만 0.22~0.40 구간이 겹침 (점선 = 중앙값)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "09_similarity_dist.png", dpi=150, bbox_inches="tight")
    overlap = (sim[~hit] > np.median(sim[hit])).mean()

    r_emb = recall_at_k(sim, exp_ids, job_ids, answers)
    r_tf = recall_at_k(tfidf_sim(queries, docs), exp_ids, job_ids, answers)
    order = np.argsort(r_emb)
    fig, ax = plt.subplots(figsize=(8, 6))
    y = np.arange(len(exp_ids))
    for i, k in enumerate(order):
        ax.plot([r_tf[k], r_emb[k]], [i, i], color="#CFCBBE", lw=3, zorder=1)
    ax.scatter(r_tf[order], y, color=GRAY, s=60, label=f"TF-IDF (평균 {r_tf.mean():.2f})", zorder=2)
    ax.scatter(r_emb[order], y, color=BLUE, s=60, label=f"3-large (평균 {r_emb.mean():.2f})", zorder=3)
    ax.set_yticks(y, [exp_ids[k] for k in order]); ax.set_xlim(-0.05, 1.05)
    ax.set_xlabel("재현율@10"); ax.set_title("경험별 재현율 — 임베딩이 키워드보다 낮은 경험이 거의 없음")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout(); fig.savefig(OUT / "10_recall_by_exp.png", dpi=150, bbox_inches="tight")
    print(f"정답 쌍 중앙값 {np.median(sim[hit]):.3f} / 오답 {np.median(sim[~hit]):.3f}, 오답 중 정답 중앙값보다 높은 비율 {overlap:.1%}")
    print(f"임베딩 > TF-IDF {int((r_emb > r_tf).sum())}개, 같음 {int((r_emb == r_tf).sum())}개, 낮음 {int((r_emb < r_tf).sum())}개")


if __name__ == "__main__":
    assert np.allclose(np.abs(pca2(np.array([[1., 0], [-1, 0], [0, 0]]))[0][:, 0]), [1, 1, 0])
    embedding_map()
    similarity_and_recall()
