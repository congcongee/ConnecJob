from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator

SIZES = ["대기업집단", "공공기관", "중견(근사)", "외국계", "중소·기타"]
TYPES = (
  ("프로젝트", "프로젝트"),
  ("경력", "경력"),
  ("자격증/교육", "자격증/교육"),
  ("대외활동", "대외활동"),
)

def min_length_10_validator(value):
  if len(value.strip()) < 10: # 너무 짧으면 공고 검색·자소서 모두 근거가 없음
    raise forms.ValidationError("무엇을 했는지 10자 이상 적어 주세요.")

# 경험 1개 입력 (여러 개는 [경험 추가]를 누를 때마다 세션 목록에 담음)
class ExperienceForm(forms.Form):
  유형 = forms.ChoiceField(label="유형", choices=TYPES)
  제목 = forms.CharField(label="제목", max_length=100)
  기간 = forms.CharField(label="기간", max_length=50, required=False, help_text="예: 2025.03-2025.06")
  역할 = forms.CharField(label="역할", max_length=100, required=False)
  기술스택 = forms.CharField(label="기술스택", max_length=300, required=False,
                         help_text="쉼표로 구분 (예: Python, Django, MySQL)")
  내용 = forms.CharField(label="내용", max_length=2000,
                       widget=forms.Textarea(attrs={"rows": 4}),
                       validators=[min_length_10_validator])
  성과 = forms.CharField(label="성과", max_length=300, required=False)

# 추천 조건
class OptionForm(forms.Form):
  newbie_only = forms.BooleanField(label="신입 지원 가능 공고만", required=False, initial=True)
  sizes = forms.MultipleChoiceField(label="기업 규모 (선택 안 하면 전체)",
                                    choices=[(s, s) for s in SIZES],
                                    required=False,
                                    widget=forms.CheckboxSelectMultiple)

# 자소서 초안·첨삭
class LetterForm(forms.Form):
  question  = forms.CharField(label="문항", widget=forms.Textarea(attrs={"rows": 2}))
  limit     = forms.IntegerField(label="글자수 제한", initial=800,
                                 validators=[MinValueValidator(100), MaxValueValidator(3000)])
  user_text = forms.CharField(label="내가 쓴 자소서 (첨삭할 때만)", required=False,
                              widget=forms.Textarea(attrs={"rows": 8}))
