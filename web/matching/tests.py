"""화면 흐름 테스트 (AI·벡터DB 호출은 가짜로 바꿈) : python manage.py test matching"""
from unittest import mock

import httpx
import openai
from django.test import TestCase
from django.urls import reverse

from .models import Letter, Search

REC = {"doc_id": "d1", "title": "백엔드 개발자", "기업명": "테스트회사", "기업규모": "중소·기타", "시도": "서울",
       "경력": "신입", "마감일": "", "url": "정보없음", "기술태그": "Django", "직무묶음": "백엔드 개발",
       "점수": 0.6, "유사도": 0.5, "겹치는기술": "Django", "부족기술": "AWS", "경력요구": False, "이유": "백엔드 직무"}
PLAN = {"직무묶음": ["백엔드 개발"], "대상공고수": 10, "부족기술": [{"기술": "AWS", "요구비율": 0.3, "공고수": 3,
                                                          "추천공고부족": 1}], "추천자격증": []}
EXP_POST = {"exp-TOTAL_FORMS": "1", "exp-INITIAL_FORMS": "0", "exp-MIN_NUM_FORMS": "0", "exp-MAX_NUM_FORMS": "5",
            "exp-0-유형": "프로젝트", "exp-0-제목": "예약 웹", "exp-0-기술스택": "Python, Django",
            "exp-0-내용": "Django 로 예약 API 와 관리자 화면을 만듦", "newbie_only": "on"}


def api_error():
    return openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com"))


@mock.patch("matching.views.postings_db", return_value=None)
class FlowTest(TestCase):
    @mock.patch("matching.views.study_plan", return_value=[])
    @mock.patch("matching.views.roadmap", return_value=dict(PLAN))
    @mock.patch("matching.views.recommend", return_value=[REC])
    def test_index_saves_and_redirects(self, rec, *_):
        res = self.client.post(reverse("matching:index"), EXP_POST)
        s = Search.objects.get()
        self.assertRedirects(res, reverse("matching:result", args=[s.pk]))
        exps = rec.call_args.args[0]
        self.assertEqual(exps[0]["exp_id"], "E01")
        self.assertEqual(exps[0]["기술스택"], "Python;Django")  # 쉼표 → ';'
        self.assertTrue(rec.call_args.kwargs["newbie_only"])
        self.assertContains(self.client.get(res.url), "백엔드 개발자")

    def test_empty_input_shows_error(self, _):
        data = {k: v for k, v in EXP_POST.items() if not k.startswith("exp-0-")}
        res = self.client.post(reverse("matching:index"), data)
        self.assertContains(res, "경험을 하나 이상 입력해 주세요.")
        self.assertFalse(Search.objects.exists())

    @mock.patch("matching.views.recommend", side_effect=api_error())
    def test_ai_error_shows_message(self, *_):
        res = self.client.post(reverse("matching:index"), EXP_POST)
        self.assertContains(res, "AI 호출 중 오류")
        self.assertFalse(Search.objects.exists())

    def make_search(self):
        return Search.objects.create(experiences=[{"exp_id": "E01", "유형": "프로젝트", "제목": "예약 웹",
                                                   "기술스택": "Django", "내용": "예약 API"}],
                                     results=[REC], roadmap=PLAN)

    @mock.patch("matching.views.write_draft", return_value={"초안": "초안입니다 [E01]", "보완할점": "수치", "고친표현": [],
                                                            "확인필요": [], "글자수": 6, "제한": 800, "사용경험": ["E01"]})
    def test_draft(self, draft, _):
        s = self.make_search()
        res = self.client.post(reverse("matching:letter", args=[s.pk, "d1"]),
                               {"question": "지원 동기", "limit": "800", "kind": "draft"})
        l = Letter.objects.get()
        self.assertRedirects(res, reverse("matching:letter_detail", args=[l.pk]))
        self.assertContains(self.client.get(res.url), "초안입니다")

    def test_review_needs_text(self, _):
        s = self.make_search()
        res = self.client.post(reverse("matching:letter", args=[s.pk, "d1"]),
                               {"question": "지원 동기", "limit": "800", "kind": "review", "user_text": "짧음"})
        self.assertContains(res, "50자 이상")
        self.assertFalse(Letter.objects.exists())

    def test_unknown_posting_redirects(self, _):
        s = self.make_search()
        res = self.client.get(reverse("matching:letter", args=[s.pk, "없는공고"]))
        self.assertRedirects(res, reverse("matching:result", args=[s.pk]))
