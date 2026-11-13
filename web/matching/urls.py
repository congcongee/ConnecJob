from django.urls import path
from . import views

app_name = "matching"
urlpatterns = [
  path("",                    views.home,       name="home"),       # 홈
  path("jobs/",               views.jobs,       name="jobs"),       # 공고 둘러보기
  path("jobs/<str:doc_id>/",  views.job_detail, name="job_detail"), # 공고 상세
  path("guide/",              views.guide,      name="guide"),      # 직무 알아보기
  path("match/",              views.index,      name="index"),      # 맞춤 추천 (경험 입력)
  path("match/delete/<int:no>/", views.exp_delete, name="exp_delete"),
  path("result/<int:pk>/",    views.result,     name="result"),
  path("result/<int:pk>/letter/<str:doc_id>/", views.letter, name="letter"),
  path("letter/<int:pk>/",    views.letter_detail, name="letter_detail"),
  path("history/",            views.history,    name="history"),
]
