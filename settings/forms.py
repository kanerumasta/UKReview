from django import forms
from django.forms import inlineformset_factory
from defects.models import DefectCategory, DefectOption

class DefectCategoryForm(forms.ModelForm):
    class Meta:
        model = DefectCategory
        fields = ["name"]

DefectOptionFormSet = inlineformset_factory(
    DefectCategory,
    DefectOption,
    fields=("check_type", "severity_level"),
    extra=1,
    can_delete=True
)
