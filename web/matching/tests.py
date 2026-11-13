"""화면 흐름 테스트 (AI·벡터DB 호출은 가짜로 바꿈) : python manage.py test matching"""
import json
from datetime import date, timedelta
from unittest import mock

import httpx
import openai
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from . import views
from .models import Letter, Search

REC = {"doc_id": "d1", "title": "백엔드 개발자", "기업명": "테스트회사", "기업규모": "중소·기타", "시도": "서울",
       "경력": "신입", "마감일": "", "url": "정보없음", "기술태그": "Django", "직무묶음": "웹·백엔드 개발",
       "점수": 0.6, "유사도": 0.5, "겹치는기술": "Django", "부족기술": "AWS", "경력요구": False, "이유": "백엔드 직무"}
PLAN = {"직무묶음": ["웹·백엔드 개발"], "대상공고수": 10,
        "부족기술": [{"기술": "AWS", "요구비율": 0.3, "공고수": 3, "추천공고부족": 1}], "추천자격증": []}
EXP = {"유형": "프로젝트", "제목": "예약 웹", "기술스택": "Python, Django",
       "내용": "Django 로 예약 API 와 관리자 화면을 만듦", "add": ""}
POST = {"doc_id": "p1", "title": "주니어 백엔드 개발자", "기업명": "(주)테스트랩", "기업규모": "중소·기타", "시도": "서울",
        "경력": "신입", "마감일": "2099-12-31", "url": "정보없음", "기술태그": "Django;AWS", "직무묶음": "웹·백엔드 개발",
        "source": "인크루트", "본문": "Django API 개발"}
OLD = dict(POST, doc_id="p2", title="지난 데이터 분석가", 마감일="2020-01-01", 직무묶음="데이터 분석·사이언스")

def api_error():
  return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))


class BrowseTest(TestCase):
  """경험을 안 적어도 홈·공고 목록·상세·직무 알아보기를 볼 수 있음 (공고는 벡터DB 대신 가짜 목록)"""
  def setUp(self):
    views._postings = [POST, OLD]

  def tearDown(self):
    views._postings = None

  def test_home(self):
    soon = (date.today() + timedelta(days=1)).isoformat()
    views._postings = [POST, OLD, dict(POST, doc_id="p3", title="곧 마감 QA 인턴", 마감일=soon, 시도="정보없음"),
                       dict(POST, doc_id="p4", title="곧 마감 경력직", 마감일=soon, 경력="경력")]
    res = self.client.get(reverse("matching:home"))
    self.assertContains(res, "곧 마감 QA 인턴")         # 마감 임박
    self.assertContains(res, "근무지 미기재")           # 근무지 빈칸
    self.assertNotContains(res, "곧 마감 경력직")       # 경력 필수 제외
    self.assertNotContains(res, "지난 데이터 분석가")    # 마감 지난 공고 제외
    self.assertContains(res, "웹 서비스의 서버와 데이터베이스를 만드는 일")  # 직무 한 줄 설명

  def test_deadline_soon(self):
    today = date(2026, 11, 10)
    def p(i, d, career="신입"):
      return dict(POST, doc_id=f"s{i}", 마감일=d, 경력=career)
    items = [p(1, "2026-11-10"), p(2, "2026-11-12"), p(3, "2026-11-11", "경력"), p(4, "2026-11-09"),
             p(5, "2026-11-16"), p(6, ""), p(7, "2026-11-20")]
    got = [x["doc_id"] for x in views.deadline_soon(items, today)]
    # 6건이 안 차서 7일까지 넓힘 : 경력 필수·지난 공고·상시·7일 넘는 공고는 빠지고 마감 순
    self.assertEqual(got, ["s1", "s2", "s5"])
    got = [x["doc_id"] for x in views.deadline_soon(items, today, n=2)]
    self.assertEqual(got, ["s1", "s2"]) # 3일 안에서 다 차면 넓히지 않음

  def test_jobs_filters(self):
    self.assertContains(self.client.get(reverse("matching:jobs"), {"q": "django"}), "주니어 백엔드 개발자")
    self.assertNotContains(self.client.get(reverse("matching:jobs"), {"q": "spring"}), "주니어 백엔드 개발자")
    self.assertNotContains(self.client.get(reverse("matching:jobs"), {"size": "공공기관"}), "주니어 백엔드 개발자")
    self.assertContains(self.client.get(reverse("matching:jobs"), {"page": "abc"}), "주니어 백엔드 개발자")

  def test_detail(self):
    self.assertContains(self.client.get(reverse("matching:job_detail", args=["p1"])), "Django API 개발")
    res = self.client.get(reverse("matching:job_detail", args=["없음"]))
    self.assertRedirects(res, reverse("matching:jobs"))

  def test_guide(self):
    res = self.client.get(reverse("matching:guide"))
    self.assertContains(res, "LLM·생성형AI 개발")
    res = self.client.get(reverse("matching:guide"), {"check": "1", "like": ["llm", "model"]})
    self.assertEqual(res.context["picks"][0]["name"] in ("LLM·생성형AI 개발", "AI·ML 개발"), True)
    self.assertContains(res, "이런 직무가 어울려요")


@mock.patch("matching.views.postings_db", return_value=None)
class FlowTest(TestCase):
  def setUp(self):
    views._postings = [POST]

  def tearDown(self):
    views._postings = None

  def test_home_text_prefills_form(self, _):
    # 홈 글은 POST → 세션 → GET (주소에 글이 안 붙음), 한 번 채우면 세션에서 지움
    res = self.client.post(reverse("matching:index"), {"exp": "  공공데이터 대시보드 제작  "})
    self.assertRedirects(res, reverse("matching:index"), fetch_redirect_response=False)
    self.assertNotIn("exp=", res.url)
    self.assertContains(self.client.get(reverse("matching:index")), "공공데이터 대시보드 제작")
    self.assertNotContains(self.client.get(reverse("matching:index")), "공공데이터 대시보드 제작")

  def test_home_blank_text_goes_back(self, _):
    res = self.client.post(reverse("matching:index"), {"exp": "   \n "})
    self.assertRedirects(res, reverse("matching:home"), fetch_redirect_response=False)
    self.assertFalse(Search.objects.exists())

  @mock.patch("matching.views.study_plan", return_value=[])
  @mock.patch("matching.views.roadmap", return_value=dict(PLAN))
  @mock.patch("matching.views.recommend", return_value=[REC])
  def test_add_then_run(self, rec, *_):
    self.assertRedirects(self.client.post(reverse("matching:index"), EXP), reverse("matching:index"))
    res = self.client.post(reverse("matching:index"), {"newbie_only": "on", "run": ""})
    s = Search.objects.get()
    self.assertRedirects(res, reverse("matching:result", args=[s.id]))
    self.assertIsNone(s.user)  # 비회원 결과
    exps = rec.call_args.args[0]
    self.assertEqual(exps[0]["exp_id"], "E01")
    self.assertEqual(exps[0]["기술스택"], "Python;Django")  # 쉼표 → ';'
    self.assertTrue(rec.call_args.kwargs["newbie_only"])
    self.assertContains(self.client.get(res.url), "백엔드 개발자")

  def test_short_content_error(self, _):
    res = self.client.post(reverse("matching:index"), dict(EXP, 내용="짧음"))
    self.assertContains(res, "10자 이상")
    self.client.post(reverse("matching:index"), EXP)
    self.client.get(reverse("matching:exp_delete", args=[1]))  # 담은 경험 빼기
    self.assertEqual(self.client.session["exps"], [])

  def test_run_without_exps(self, _):
    res = self.client.post(reverse("matching:index"), {"run": ""}, follow=True)
    self.assertContains(res, "경험을 하나 이상 입력해 주세요.")
    self.assertFalse(Search.objects.exists())

  @mock.patch("matching.views.study_plan", side_effect=api_error())
  @mock.patch("matching.views.roadmap", return_value=dict(PLAN))
  @mock.patch("matching.views.recommend", side_effect=[api_error(), [REC]])
  def test_llm_error_falls_back_to_score(self, rec, *_):
    """LLM 재판정·학습 계획이 실패해도 점수순 추천과 요구 비율표로 결과를 저장하고 안내"""
    self.client.post(reverse("matching:index"), EXP)
    res = self.client.post(reverse("matching:index"), {"run": ""}, follow=True)
    self.assertEqual([c.kwargs["use_llm"] for c in rec.call_args_list], [True, False])
    s = Search.objects.get()
    self.assertEqual(s.get_roadmap()["학습계획"], [])
    self.assertContains(res, "점수순 추천")
    self.assertContains(res, "백엔드 개발자")

  @mock.patch("matching.views.recommend", side_effect=api_error())
  def test_ai_error_shows_message(self, *_):
    self.client.post(reverse("matching:index"), EXP)
    res = self.client.post(reverse("matching:index"), {"run": ""})
    self.assertContains(res, "AI 호출 중 오류")
    self.assertFalse(Search.objects.exists())

  def make_search(self, mine=True):
    s = Search(experiences=json.dumps([{"exp_id": "E01", "유형": "프로젝트", "제목": "예약 웹",
                                        "기술스택": "Django", "내용": "예약 API"}]),
               results=json.dumps([REC]), roadmap=json.dumps(PLAN))
    s.save()
    if mine:  # 이 브라우저(비회원 세션)에서 만든 결과로 표시
      session = self.client.session
      session["search_ids"] = session.get("search_ids", []) + [s.id]
      session.save()
    return s

  def test_other_people_results_hidden(self, _):
    other = self.make_search(mine=False)
    self.assertEqual(self.client.get(reverse("matching:result", args=[other.id])).status_code, 404)
    self.assertNotContains(self.client.get(reverse("matching:history")), "예약 웹")
    l = Letter(search=other, doc_id="d1", company="c", title="t", kind="draft", question="q", limit=800, result="{}")
    l.save()
    self.assertEqual(self.client.get(reverse("matching:letter_detail", args=[l.id])).status_code, 404)

  def test_login_claims_guest_results(self, _):
    s = self.make_search()
    User.objects.create_user("tester", password="pw-12345678")
    res = self.client.post(reverse("accounts:login"), {"username": "tester", "password": "pw-12345678"})
    self.assertEqual(res.status_code, 302)
    s.refresh_from_db()
    self.assertEqual(s.user.username, "tester")
    self.assertContains(self.client.get(reverse("matching:history")), "예약 웹")
    self.assertContains(self.client.get(reverse("matching:result", args=[s.id])), "tester")

  def test_login_blocks_other_site(self, _):
    User.objects.create_user("tester", password="pw-12345678")
    res = self.client.post(reverse("accounts:login"), {"username": "tester", "password": "pw-12345678",
                                                       "next": "https://evil.example"})
    self.assertRedirects(res, "/")

  def test_signup_and_logout(self, _):
    res = self.client.post(reverse("accounts:signup"), {"username": "newbie", "password1": "pw-12345678",
                                                        "password2": "pw-12345678"})
    self.assertRedirects(res, "/")
    self.assertContains(self.client.get("/"), "newbie")
    self.client.post(reverse("accounts:logout"))
    self.assertContains(self.client.get("/"), "회원가입")

  @mock.patch("matching.views.write_draft", return_value={"초안": "초안입니다 [E01] <b>x</b>", "보완할점": "수치",
                                                          "고친표현": [], "확인필요": [], "글자수": 6, "제한": 800,
                                                          "사용경험": ["E01"]})
  def test_draft(self, draft, _):
    s = self.make_search()
    res = self.client.post(reverse("matching:letter", args=[s.id, "d1"]),
                           {"question": "지원 동기", "limit": "800", "kind": "draft"})
    l = Letter.objects.get()
    self.assertRedirects(res, reverse("matching:letter_detail", args=[l.id]))
    page = self.client.get(res.url)
    self.assertContains(page, '<span class="src">[E01]</span>')
    self.assertContains(page, "&lt;b&gt;x&lt;/b&gt;")  # AI 글 속 태그는 escape

  def test_review_needs_text(self, _):
    s = self.make_search()
    res = self.client.post(reverse("matching:letter", args=[s.id, "d1"]),
                           {"question": "지원 동기", "limit": "800", "kind": "review", "user_text": "짧음"})
    self.assertContains(res, "50자 이상")
    self.assertFalse(Letter.objects.exists())

  def test_unknown_posting_redirects(self, _):
    s = self.make_search()
    res = self.client.get(reverse("matching:letter", args=[s.id, "없는공고"]))
    self.assertRedirects(res, reverse("matching:result", args=[s.id]))


class DisplayTest(TestCase):
  def test_display_values(self):
    today = date(2026, 11, 10)
    self.assertEqual(views.dday_text("2026-11-18", today), "D-8")
    self.assertEqual(views.dday_text("2026-11-10 00:00:00", today), "D-Day")
    self.assertEqual(views.dday_text("nan", today), "")
    self.assertEqual(views.deadline_text("2026-11-18"), "~11/18(수)")
    self.assertEqual(views.deadline_text("정보없음"), "상시")
    self.assertEqual(views.add_display({"겹치는기술": "REST API", "부족기술": "Java;Spring"})["ratio"], "1/3")
