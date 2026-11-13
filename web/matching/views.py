import json
import re
from datetime import date, timedelta

import openai
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.html import escape

from cover_letter import get_questions, review_letter, write_draft
from recommend import get_db, recommend
from roadmap import VAGUE_TAGS, roadmap, study_plan

from .forms import ExperienceForm, LetterForm, OptionForm, SIZES
from .jobinfo import EXAMPLES, JOB_INFO, QUESTIONS
from .models import Letter, Search

# 직무 알아보기 '많이 요구하는 기술'에서 뺄 태그 : 너무 넓은 말(웹, 인공지능 …) + 문서 도구
SKIP_TAGS = set(VAGUE_TAGS) | {"정보없음", "Word", "PowerPoint", "MS Office", "한글"}

AI_ERROR = "AI 호출 중 오류가 났습니다. 잠시 뒤 다시 시도해 주세요."
GUEST_KEY = "search_ids" # 비회원이 이 브라우저에서 만든 결과 id 목록 (세션)
EXP_KEY = "exps"         # 추천받기 전에 담아 둔 경험 목록 (세션)
HOME_EXP_KEY = "home_exp" # 홈에서 적은 경험 글 (맞춤 추천 '내용' 칸에 한 번 채움)

# ---------------------------------------------------------------- 공고 데이터
_db = None
_postings = None

def postings_db():
  global _db # Chroma 연결은 한 번만 (요청마다 만들면 느림)
  if _db is None:
    _db = get_db("postings")
  return _db

def postings():
  """벡터DB 에 넣은 공고 전체 (메타 + 본문). 서버가 켜진 동안 한 번만 읽음 (AI 호출 없음)"""
  global _postings
  if _postings is None:
    g = postings_db().get(include=["metadatas", "documents"])
    _postings = []
    for m, d in zip(g["metadatas"], g["documents"]):
      p = dict(m)
      p["본문"] = d
      _postings.append(p)
  return _postings

# ---------------------------------------------------------------- 화면에 보여 줄 값 계산
def split_tags(text):
  """'Django;REST API' → ['Django', 'REST API']"""
  return [t for t in str(text or "").split(";") if t and t != "nan"]

def to_date(text):
  try:
    return date.fromisoformat(str(text or "")[:10])
  except ValueError: # '', 'nan', '정보없음', '상시' 등
    return None

def dday_text(text, today=None):
  """마감일 → 'D-8' / 'D-Day' / '마감' / ''"""
  d = to_date(text)
  if d is None:
    return ""
  n = (d - (today or date.today())).days
  if n == 0:
    return "D-Day"
  if n > 0:
    return f"D-{n}"
  return "마감"

def deadline_text(text):
  """마감일 → '~11/18(수)', 날짜가 없으면 '상시'"""
  d = to_date(text)
  if d is None:
    return "상시"
  return f"~{d.month}/{d.day}({'월화수목금토일'[d.weekday()]})"

def add_display(p):
  """공고·추천 1건에 화면용 값을 더한 복사본"""
  p = dict(p)
  p["tag_list"] = split_tags(p.get("기술태그"))
  p["group_list"] = split_tags(p.get("직무묶음"))
  p["dday"] = dday_text(p.get("마감일"))
  p["deadline_txt"] = deadline_text(p.get("마감일"))
  p["career"] = "경력 무관" if p.get("경력") in ("정보없음", "관계없음", None) else p["경력"]
  p["place"] = "" if p.get("시도") == "정보없음" else p.get("시도", "")
  # 추천 결과에만 있는 값 : 겹치는 기술 / 부족한 기술 / 기술 일치 '2/3'
  p["have"] = split_tags(p.get("겹치는기술"))
  p["lack"] = split_tags(p.get("부족기술"))
  total = len(p["have"]) + len(p["lack"])
  p["ratio"] = f"{len(p['have'])}/{total}" if total else "-"
  return p

def is_open(p, today):
  d = to_date(p.get("마감일"))
  return d is None or d.isoformat() >= today

def open_postings():
  today = date.today().isoformat()
  return [p for p in postings() if is_open(p, today)]

def deadline_key(p):
  d = to_date(p.get("마감일"))
  return d.isoformat() if d else "9999" # 상시·정보없음은 뒤로

def deadline_soon(items, today, n=6):
  """홈 마감 임박 : 경력 필수 공고는 빼고 3일 이내, 모자라면 7일 이내 (신입·주니어 대상이라서)"""
  for days in (3, 7):
    last = (today + timedelta(days=days)).isoformat()
    picked = [p for p in items if p.get("경력") != "경력" and today.isoformat() <= deadline_key(p) <= last]
    if len(picked) >= n:
      break
  return sorted(picked, key=deadline_key)[:n]

def group_counts(items):
  """직무별 공고 수 {'웹·백엔드 개발': 122, ...}"""
  counts = dict()
  for p in items:
    for g in split_tags(p.get("직무묶음")):
      if g in counts:
        counts[g] += 1
      else:
        counts[g] = 1
  return counts

# ---------------------------------------------------------------- 결과 주인 (회원 / 비회원)
def owned(request):
  """지금 사람이 볼 수 있는 결과 : 회원 = 내 계정 것, 비회원 = 이 브라우저(세션)에서 만든 것"""
  if request.user.is_authenticated:
    return Search.objects.filter(user=request.user)
  return Search.objects.filter(user=None, id__in=request.session.get(GUEST_KEY, []))

def get_search(request, pk):
  return get_object_or_404(owned(request), id=pk) # 남의 결과면 404

def claim_guest_searches(request, user):
  """비회원으로 만든 결과를 로그인·가입한 계정으로 옮김 (accounts.views 에서 부름)"""
  for s in Search.objects.filter(user=None, id__in=request.session.get(GUEST_KEY, [])):
    s.user = user
    s.save()
  request.session[GUEST_KEY] = []

# ---------------------------------------------------------------- 둘러보기 (AI 호출 없음)
def home(request):
  items = open_postings()
  counts = group_counts(items)
  groups = []
  for g, n in sorted(counts.items(), key=lambda x: -x[1]):
    groups.append({"name": g, "count": n, "desc": JOB_INFO.get(g, {}).get("한줄", "")})
  soon = deadline_soon(items, date.today())
  examples = []
  for e in EXAMPLES: # 요구 역량 막대 : 채운 칸 True, 빈 칸 False
    e = dict(e)
    e["bar"] = [True] * e["hit"] + [False] * (e["req"] - e["hit"])
    examples.append(e)
  context = {
    "examples": examples,
    "total": len(items),
    "groups": groups,
    "soon": [add_display(p) for p in soon],
    "recent": owned(request)[:3],
  }
  return render(request, "matching/home.html", context)

PER_PAGE = 20

def jobs(request):
  """공고 둘러보기 : 검색어·직무·기업규모·신입 필터, 마감 빠른 순, 20개씩"""
  q = request.GET.get("q", "").strip()
  group = request.GET.get("group", "")
  size = request.GET.get("size", "")
  newbie = request.GET.get("newbie") == "1"
  all_items = open_postings()
  items = all_items
  if q:
    items = [p for p in items if q.lower() in f"{p['title']} {p['기업명']} {p['기술태그']}".lower()]
  if group:
    items = [p for p in items if group in split_tags(p.get("직무묶음"))]
  if size:
    items = [p for p in items if p.get("기업규모") == size]
  if newbie:
    items = [p for p in items if p.get("경력") != "경력"]
  items = sorted(items, key=deadline_key)

  # 페이지 나누기 : 리스트 자르기 [시작:끝]
  page = request.GET.get("page", "1")
  page = int(page) if page.isdigit() else 1
  last = (len(items) + PER_PAGE - 1) // PER_PAGE or 1
  page = min(max(page, 1), last)
  rows = items[(page - 1) * PER_PAGE : page * PER_PAGE]

  context = {
    "rows": [add_display(p) for p in rows],
    "count": len(items),
    "page": page, "last": last,
    "q": q, "group": group, "size": size, "newbie": newbie,
    "groups": sorted(group_counts(all_items)),
    "sizes": SIZES,
    "group_desc": JOB_INFO.get(group, {}).get("한줄", ""),
  }
  return render(request, "matching/jobs.html", context)

def job_detail(request, doc_id):
  found = [p for p in postings() if p["doc_id"] == doc_id]
  if not found: # 없는 공고 번호
    messages.error(request, "찾는 공고가 없습니다.")
    return redirect("matching:jobs")
  p = add_display(found[0])
  infos = [{"name": g, "desc": JOB_INFO[g]["한줄"]} for g in p["group_list"] if g in JOB_INFO]
  return render(request, "matching/job_detail.html",
                {"p": p, "open": is_open(p, date.today().isoformat()), "infos": infos})

def guide(request):
  """직무 알아보기 : 직무별 설명 + 공고에서 많이 요구하는 기술 + 체크해서 맞는 직무 찾기"""
  items = open_postings()
  counts = group_counts(items)
  cards = []
  for g, info in JOB_INFO.items():
    skills = dict() # 이 직무 공고의 기술태그 세기
    for p in items:
      if g in split_tags(p.get("직무묶음")):
        for t in split_tags(p.get("기술태그")):
          if t not in SKIP_TAGS:
            skills[t] = skills.get(t, 0) + 1
    top = sorted(skills.items(), key=lambda x: -x[1])[:6]
    cards.append({"name": g, "count": counts.get(g, 0), "info": info, "top": [t for t, n in top]})
  cards = sorted(cards, key=lambda c: -c["count"])

  # 체크한 문장 → 직무 점수
  likes = request.GET.getlist("like")
  scores = dict()
  reasons = dict()
  for key, text, groups in QUESTIONS:
    if key in likes:
      for g in groups:
        scores[g] = scores.get(g, 0) + 1
        reasons.setdefault(g, []).append(text)
  picks = []
  for g, n in sorted(scores.items(), key=lambda x: -x[1])[:3]:
    picks.append({"name": g, "score": n, "reasons": reasons[g], "desc": JOB_INFO[g]["한줄"],
                  "count": counts.get(g, 0), "no": [c["name"] for c in cards].index(g) + 1})
  context = {"cards": cards, "questions": QUESTIONS, "likes": likes, "picks": picks,
             "asked": "like" in request.GET or "check" in request.GET}
  return render(request, "matching/guide.html", context)

# ---------------------------------------------------------------- 맞춤 추천 (AI 호출)
def index(request):
  """경험 담기(여러 번) → [공고 추천 받기] → 추천 + 부족 역량·로드맵 저장 후 결과 화면으로"""
  exps = request.session.get(EXP_KEY, [])
  # 홈에서 적은 글은 POST → 세션 → 다시 GET (글이 주소창·방문 기록·서버 로그에 남지 않게)
  if request.method == "POST" and "exp" in request.POST:
    text = request.POST["exp"].strip()
    if not text:
      messages.error(request, "경험을 한 줄 이상 적어 주세요.")
      return redirect("matching:home")
    request.session[HOME_EXP_KEY] = text[:500]
    return redirect("matching:index")
  form = ExperienceForm(initial={"내용": request.session.pop(HOME_EXP_KEY, "")}) # 홈에서 적은 글을 내용 칸에
  option = OptionForm()
  if request.method == "POST":
    if "add" in request.POST: # [경험 추가] 버튼
      form = ExperienceForm(request.POST)
      if len(exps) >= 5:
        messages.error(request, "경험은 5개까지 담을 수 있어요.")
      elif form.is_valid():
        exp = form.cleaned_data
        # 'Python, Django' → 'Python;Django' (recommend 가 ';' 구분을 씀)
        exp["기술스택"] = ";".join([t.strip() for t in exp["기술스택"].replace(";", ",").split(",") if t.strip()])
        exps.append(exp)
        request.session[EXP_KEY] = exps
        messages.success(request, f"'{exp['제목']}' 경험을 담았어요.")
        return redirect("matching:index")
    else: # [공고 추천 받기] 버튼
      option = OptionForm(request.POST)
      if not exps:
        messages.error(request, "경험을 하나 이상 입력해 주세요.")
      elif option.is_valid():
        exps = [dict(e, exp_id=f"E{i:02d}") for i, e in enumerate(exps, 1)]
        opt = option.cleaned_data
        try:
          recs = recommend(exps, postings_db(), k=10, use_llm=True,
                           sizes=opt["sizes"] or None, newbie_only=opt["newbie_only"])
          plan = roadmap(exps, recs)
          plan["학습계획"] = study_plan(exps, plan)
        except openai.OpenAIError as e:
          print("추천 AI 호출 실패 :", e)
          messages.error(request, AI_ERROR)
        else:
          s = Search(experiences=json.dumps(exps, ensure_ascii=False),
                     newbie_only=opt["newbie_only"],
                     sizes=json.dumps(opt["sizes"], ensure_ascii=False),
                     results=json.dumps(recs, ensure_ascii=False),
                     roadmap=json.dumps(plan, ensure_ascii=False))
          if request.user.is_authenticated:
            s.user = request.user
          s.save()
          if not request.user.is_authenticated:
            request.session[GUEST_KEY] = request.session.get(GUEST_KEY, []) + [s.id]
          return redirect("matching:result", pk=s.id)
  context = {"form": form, "option": option, "exps": exps, "recent": owned(request)[:5]}
  return render(request, "matching/index.html", context)

def exp_delete(request, no:int):
  """담아 둔 경험 1개 빼기 (no : 1부터)"""
  exps = request.session.get(EXP_KEY, [])
  if 1 <= no <= len(exps):
    exp = exps.pop(no - 1)
    request.session[EXP_KEY] = exps
    messages.success(request, f"'{exp['제목']}' 경험을 뺐어요.")
  else:
    messages.error(request, f"{no}번 경험이 없습니다.")
  return redirect("matching:index")

def result(request, pk):
  s = get_search(request, pk)
  plan = s.get_roadmap()
  for d in plan.get("부족기술", []) + plan.get("추천자격증", []):
    d["pct"] = f"{d.get('요구비율', 0):.0%}"
  context = {
    "s": s,
    "exps": s.get_experiences(),
    "sizes": s.get_sizes(),
    "results": [add_display(r) for r in s.get_results()],
    "plan": plan,
    "letters": s.letter_set.all(),
  }
  return render(request, "matching/result.html", context)

def letter(request, pk, doc_id):
  """추천 공고 1건 → 자소서 초안 생성 또는 사용자 자소서 첨삭"""
  s = get_search(request, pk)
  found = [r for r in s.get_results() if r["doc_id"] == doc_id]
  if not found: # 추천 결과에 없는 공고 id 를 주소창에 넣은 경우
    messages.error(request, "추천 결과에 없는 공고입니다.")
    return redirect("matching:result", pk=pk)
  rec = found[0]
  questions = get_questions(rec["기업명"])
  if request.method == "POST":
    form = LetterForm(request.POST)
    kind = "review" if request.POST.get("kind") == "review" else "draft"
    if form.is_valid():
      d = form.cleaned_data
      if kind == "review" and len(d["user_text"].strip()) < 50:
        messages.error(request, "첨삭하려면 자소서를 50자 이상 붙여 넣어 주세요.")
      else:
        try:
          if kind == "review":
            out = review_letter(s.get_experiences(), rec, d["question"], d["user_text"], d["limit"], postings_db())
          else:
            out = write_draft(s.get_experiences(), rec, d["question"], d["limit"], postings_db())
        except openai.OpenAIError as e:
          print("자소서 AI 호출 실패 :", e)
          messages.error(request, AI_ERROR)
        except ValueError as e: # write_draft : 입력에 없는 경험 ID 를 근거로 씀 (지어낸 근거)
          messages.error(request, f"초안이 입력하지 않은 경험을 근거로 써서 버렸습니다. 다시 시도해 주세요. ({e})")
        else:
          l = Letter(search=s, doc_id=doc_id, company=rec["기업명"], title=rec["title"], kind=kind,
                     question=d["question"], limit=d["limit"], user_text=d["user_text"],
                     result=json.dumps(out, ensure_ascii=False))
          l.save()
          return redirect("matching:letter_detail", pk=l.id)
  else:
    form = LetterForm(initial={"question": questions[0]["문항"], "limit": questions[0]["글자수"]})
  return render(request, "matching/letter.html",
                {"s": s, "rec": add_display(rec), "form": form, "questions": questions})

def letter_detail(request, pk):
  l = get_object_or_404(Letter, id=pk, search__in=owned(request))
  r = l.get_result()
  # 초안의 [E01]·[공고] 표시를 강조 (글은 escape 해서 태그가 실행되지 않게)
  draft_html = re.sub(r"\[(E\d+|공고)\]", r'<span class="src">[\1]</span>', escape(r.get("초안", "")))
  return render(request, "matching/letter_detail.html", {"l": l, "r": r, "draft_html": draft_html})

def history(request):
  return render(request, "matching/history.html", {"searches": owned(request)})
