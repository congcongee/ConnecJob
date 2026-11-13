from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
  path("login/",  views.login_view,  name="login"),
  path("logout/", views.logout_view, name="logout"), # POST 로만 로그아웃
  path("signup/", views.signup,      name="signup"),
]
