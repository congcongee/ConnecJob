from django import forms

SIZES = ["대기업집단", "공공기관", "중견(근사)", "외국계", "중소·기타"]


class ExperienceForm(forms.Form):
    유형 = forms.ChoiceField(choices=[(x, x) for x in ["프로젝트", "경력", "자격증/교육", "대외활동"]])
    제목 = forms.CharField(max_length=100)
    기간 = forms.CharField(max_length=50, required=False, help_text="예: 2025.03-2025.06")
    역할 = forms.CharField(max_length=100, required=False)
    기술스택 = forms.CharField(max_length=300, required=False, help_text="쉼표로 구분 (예: Python, Django, MySQL)")
    내용 = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), max_length=2000)
    성과 = forms.CharField(max_length=300, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-select" if isinstance(f.widget, forms.Select) else "form-control"

    def clean_내용(self):
        text = self.cleaned_data["내용"].strip()
        if len(text) < 10:  # 너무 짧으면 검색·자소서 모두 근거가 없음
            raise forms.ValidationError("무엇을 했는지 10자 이상 적어 주세요.")
        return text

    def clean_기술스택(self):
        # recommend.experience_text 는 ';' 구분을 기대함
        return ";".join(t.strip() for t in self.cleaned_data["기술스택"].replace(";", ",").split(",") if t.strip())


class BaseExperienceFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        if not any(f.cleaned_data for f in self.forms):
            raise forms.ValidationError("경험을 하나 이상 입력해 주세요.")


ExperienceFormSet = forms.formset_factory(ExperienceForm, formset=BaseExperienceFormSet, extra=1, max_num=5)


class OptionForm(forms.Form):
    newbie_only = forms.BooleanField(label="신입 지원 가능 공고만", required=False, initial=True)
    sizes = forms.MultipleChoiceField(label="기업 규모 (선택 안 하면 전체)", choices=[(s, s) for s in SIZES],
                                      required=False, widget=forms.CheckboxSelectMultiple)


class LetterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields.values():
            f.widget.attrs["class"] = "form-control"

    question = forms.CharField(label="문항", widget=forms.Textarea(attrs={"rows": 2}))
    limit = forms.IntegerField(label="글자수 제한", min_value=100, max_value=3000, initial=800)
    user_text = forms.CharField(label="내가 쓴 자소서 (첨삭할 때만)", required=False,
                                widget=forms.Textarea(attrs={"rows": 8}))

    def clean(self):
        data = super().clean()
        if self.data.get("kind") == "review" and len(data.get("user_text", "").strip()) < 50:
            self.add_error("user_text", "첨삭하려면 자소서를 50자 이상 붙여 넣어 주세요.")
        return data
