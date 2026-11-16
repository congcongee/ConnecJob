import json
from django.conf import settings
from django.db import models

# 채용공고 1건 (data/processed/postings.csv 통합 공고 표 → python manage.py load_postings)
# 공고 둘러보기·상세·직무 알아보기는 이 표에서 읽고, 맞춤 추천은 벡터DB(직무묶음이 있는 공고)에서 찾음
class Posting(models.Model): # 테이블명 : matching_posting
  doc_id   = models.CharField(max_length=100, unique=True)
  source   = models.CharField(max_length=50, verbose_name="출처")
  title    = models.CharField(max_length=500, verbose_name="제목")
  company  = models.CharField(max_length=300, verbose_name="기업명")
  category = models.CharField(max_length=100, verbose_name="NCS 대분류")
  size     = models.CharField(max_length=20, verbose_name="기업규모")
  region   = models.CharField(max_length=50, verbose_name="시도")
  career   = models.CharField(max_length=10, verbose_name="경력")          # 신입 / 경력 / 관계없음 / 정보없음
  deadline = models.DateField(null=True, blank=True, verbose_name="마감일") # 비어 있으면 상시
  url      = models.CharField(max_length=1000)                             # '정보없음' 도 있어서 URLField 대신
  tech_tags  = models.TextField(blank=True, verbose_name="기술태그")      # 'Django;AWS'
  cert_tags  = models.TextField(blank=True, verbose_name="자격증태그")
  job_groups = models.CharField(max_length=300, blank=True, db_index=True, verbose_name="직무묶음") # '웹·백엔드 개발;…', 범위 밖이면 ''
  # db_index : 직무묶음 있는 공고(수백 건)만 색인으로 바로 찾음 (job_groups__gt="")
  content  = models.TextField(verbose_name="본문")

  def as_dict(self):
    """화면·추천 코드가 쓰던 공고 dict 모양 (벡터DB 메타와 같은 한글 키)"""
    return {"doc_id": self.doc_id, "source": self.source, "title": self.title, "기업명": self.company,
            "기업규모": self.size, "시도": self.region, "경력": self.career,
            "마감일": self.deadline.isoformat() if self.deadline else "", "url": self.url,
            "기술태그": self.tech_tags, "직무묶음": self.job_groups, "본문": self.content}

  def __str__(self):
    return f"{self.company} {self.title}"

  class Meta:
    indexes = [models.Index(fields=["deadline"])] # 열린 공고·마감 순 조회가 가장 잦음


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
