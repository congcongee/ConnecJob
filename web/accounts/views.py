from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.shortcuts import render, redirect
from matching.views import claim_guest_searches

def next_url(request):
  """로그인·가입 뒤 돌아갈 주소 (우리 사이트 주소 '/...' 만 허용)"""
  nxt = request.POST.get("next") or request.GET.get("next") or "/"
  if not nxt.startswith("/") or nxt.startswith("//"): # 다른 사이트로 보내는 주소는 막음
    nxt = "/"
  return nxt

def signup(request):
  # GET : 가입 화면 / POST : 유효성 체크 → 성공하면 저장 후 바로 로그인
  if request.method == "POST":
    form = UserCreationForm(request.POST)
    if form.is_valid():
      user = form.save()
      claim_guest_searches(request, user) # 비회원으로 만든 결과를 내 계정으로
      login(request, user)
      messages.success(request, "가입을 마쳤어요. 이제 결과가 계정에 저장돼요.")
      return redirect(next_url(request))
  else:
    form = UserCreationForm()
  return render(request, "accounts/signup.html", {"form": form, "next": next_url(request)})

def login_view(request):
  if request.method == "POST":
    form = AuthenticationForm(request, data=request.POST)
    if form.is_valid():
      user = form.get_user()
      claim_guest_searches(request, user)
      login(request, user)
      messages.success(request, f"{user.username}님, 반가워요.")
      return redirect(next_url(request))
  else:
    form = AuthenticationForm(request)
  return render(request, "accounts/login.html", {"form": form, "next": next_url(request)})

def logout_view(request):
  if request.method == "POST":
    logout(request)
    messages.success(request, "로그아웃했어요.")
  return redirect("matching:home")
