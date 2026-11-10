from django.db import models


class Search(models.Model):
    """경험 입력 1번 = 추천·로드맵 결과 1건 (다시 볼 때 AI 를 또 부르지 않게 결과를 통째로 저장)"""
    experiences = models.JSONField()  # [{exp_id, 유형, 제목, 기간, 역할, 기술스택, 내용, 성과}]
    newbie_only = models.BooleanField(default=True)
    sizes = models.JSONField(default=list)  # 기업규모 필터, 빈 리스트 = 전체
    results = models.JSONField()  # recommend() 결과
    roadmap = models.JSONField()  # roadmap() 결과 + '학습계획' (study_plan)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.experiences[0]['제목']} 외 {len(self.experiences) - 1}개" if len(self.experiences) > 1 \
            else self.experiences[0]["제목"]


class Letter(models.Model):
    KIND = [("draft", "초안 생성"), ("review", "첨삭")]
    search = models.ForeignKey(Search, on_delete=models.CASCADE, related_name="letters")
    doc_id = models.CharField(max_length=100)
    company = models.CharField(max_length=200)
    title = models.CharField(max_length=300)
    kind = models.CharField(max_length=10, choices=KIND)
    question = models.TextField()
    limit = models.PositiveIntegerField()
    user_text = models.TextField(blank=True)  # 첨삭할 때 사용자가 쓴 자소서
    result = models.JSONField()  # write_draft() / review_letter() 결과
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
