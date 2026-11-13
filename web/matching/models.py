import json
from django.conf import settings
from django.db import models

# 경험 입력 1번 = 추천·로드맵 결과 1건
# 결과는 다시 볼 때 AI 를 또 부르지 않게 json 글자로 통째로 저장 (꺼낼 때 json.loads)
class Search(models.Model): # 테이블명 : matching_search
  user = models.ForeignKey(settings.AUTH_USER_MODEL, # 회원 결과는 user, 비회원 결과는 비어 있음(세션으로만 봄)
                           null=True, blank=True,
                           on_delete=models.CASCADE)
  experiences = models.TextField(verbose_name="경험")        # [{exp_id, 유형, 제목, 기간, 역할, 기술스택, 내용, 성과}]
  newbie_only = models.BooleanField(default=True)
  sizes   = models.TextField(verbose_name="기업규모", default="[]") # 빈 리스트 = 전체
  results = models.TextField(verbose_name="추천 결과")      # recommend() 결과
  roadmap = models.TextField(verbose_name="로드맵")         # roadmap() 결과 + '학습계획'
  created = models.DateTimeField(auto_now_add=True)

  def get_experiences(self):
    return json.loads(self.experiences)
  def get_sizes(self):
    return json.loads(self.sizes)
  def get_results(self):
    return json.loads(self.results)
  def get_roadmap(self):
    return json.loads(self.roadmap)

  def __str__(self):
    exps = self.get_experiences()
    if len(exps) > 1:
      return f"{exps[0]['제목']} 외 {len(exps) - 1}개"
    return exps[0]["제목"]

  class Meta:
    ordering = ['-created'] # 최근 결과부터


class Letter(models.Model): # Search : Letter = 1 : N
  KIND = (("draft", "초안 생성"), ("review", "첨삭"))
  search   = models.ForeignKey(Search, on_delete=models.CASCADE) # 결과를 지우면 자소서도 같이 삭제
  doc_id   = models.CharField(max_length=100)
  company  = models.CharField(max_length=200)
  title    = models.CharField(max_length=300)
  kind     = models.CharField(max_length=10, choices=KIND)
  question = models.TextField()
  limit    = models.IntegerField()
  user_text = models.TextField(blank=True) # 첨삭할 때 사용자가 쓴 자소서
  result   = models.TextField()            # write_draft() / review_letter() 결과 json
  created  = models.DateTimeField(auto_now_add=True)

  def get_result(self):
    return json.loads(self.result)

  def __str__(self):
    return f"{self.company} {self.get_kind_display()}"

  class Meta:
    ordering = ['-created']
