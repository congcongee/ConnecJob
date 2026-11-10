import logging

import openai
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from cover_letter import get_questions, review_letter, write_draft
from recommend import get_db, recommend
from roadmap import roadmap, study_plan

from .forms import ExperienceFormSet, LetterForm, OptionForm
from .models import Letter, Search

log = logging.getLogger(__name__)
_db = None


def postings_db():
    global _db  # Chroma 연결은 한 번만 (요청마다 만들면 느림)
    _db = _db or get_db("postings")
    return _db


AI_ERROR = "AI 호출 중 오류가 났습니다. 잠시 뒤 다시 시도해 주세요."


def index(request):
    """경험 입력 → 추천 + 부족 역량·로드맵 → 결과 저장 후 결과 화면으로"""
    formset = ExperienceFormSet(request.POST or None, prefix="exp")
    option = OptionForm(request.POST or None)
    if request.method == "POST" and formset.is_valid() and option.is_valid():
        exps = [{"exp_id": f"E{i:02d}", **f.cleaned_data} for i, f in enumerate(
            (f for f in formset if f.cleaned_data), 1)]
        opt = option.cleaned_data
        try:
            recs = recommend(exps, postings_db(), k=10, use_llm=True,
                             sizes=opt["sizes"] or None, newbie_only=opt["newbie_only"])
            plan = roadmap(exps, recs)
            plan["학습계획"] = study_plan(exps, plan)
        except openai.OpenAIError:
            log.exception("추천 AI 호출 실패")
            messages.error(request, AI_ERROR)
        else:
            s = Search.objects.create(experiences=exps, newbie_only=opt["newbie_only"], sizes=opt["sizes"],
                                      results=recs, roadmap=plan)
            return redirect("matching:result", pk=s.pk)
    return render(request, "matching/index.html", {"formset": formset, "option": option,
                                                   "recent": Search.objects.all()[:5]})


def result(request, pk):
    s = get_object_or_404(Search, pk=pk)
    return render(request, "matching/result.html", {"s": s})


def find_rec(s, doc_id):
    for r in s.results:
        if r["doc_id"] == doc_id:
            return r
    return None


def letter(request, pk, doc_id):
    """추천 공고 1건 → 자소서 초안 생성 또는 사용자 자소서 첨삭"""
    s = get_object_or_404(Search, pk=pk)
    rec = find_rec(s, doc_id)
    if rec is None:  # 추천 결과에 없는 공고 id 를 주소창에 넣은 경우
        messages.error(request, "추천 결과에 없는 공고입니다.")
        return redirect("matching:result", pk=pk)
    questions = get_questions(rec["기업명"])
    first = questions[0]
    form = LetterForm(request.POST or None, initial={"question": first["문항"], "limit": first["글자수"]})
    if request.method == "POST" and form.is_valid():
        kind = "review" if request.POST.get("kind") == "review" else "draft"
        d = form.cleaned_data
        try:
            if kind == "review":
                out = review_letter(s.experiences, rec, d["question"], d["user_text"], d["limit"], postings_db())
            else:
                out = write_draft(s.experiences, rec, d["question"], d["limit"], postings_db())
        except openai.OpenAIError:
            log.exception("자소서 AI 호출 실패")
            messages.error(request, AI_ERROR)
        except ValueError as e:  # write_draft : 입력에 없는 경험 ID 를 근거로 씀 (지어낸 근거)
            messages.error(request, f"초안이 입력하지 않은 경험을 근거로 써서 버렸습니다. 다시 시도해 주세요. ({e})")
        else:
            l = Letter.objects.create(search=s, doc_id=doc_id, company=rec["기업명"], title=rec["title"], kind=kind,
                                      question=d["question"], limit=d["limit"], user_text=d["user_text"], result=out)
            return redirect("matching:letter_detail", pk=l.pk)
    return render(request, "matching/letter.html", {"s": s, "rec": rec, "form": form, "questions": questions})


def letter_detail(request, pk):
    return render(request, "matching/letter_detail.html", {"l": get_object_or_404(Letter, pk=pk)})


def history(request):
    return render(request, "matching/history.html", {"searches": Search.objects.prefetch_related("letters")})
