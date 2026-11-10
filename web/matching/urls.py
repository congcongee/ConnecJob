from django.urls import path

from . import views

app_name = "matching"
urlpatterns = [
    path("", views.index, name="index"),
    path("result/<int:pk>/", views.result, name="result"),
    path("result/<int:pk>/letter/<str:doc_id>/", views.letter, name="letter"),
    path("letter/<int:pk>/", views.letter_detail, name="letter_detail"),
    path("history/", views.history, name="history"),
]
