
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt

# Create your views here.
from defects.models import DefectCategory
from .forms import DefectCategoryForm, DefectOptionFormSet
from django.contrib import messages
from .models import JobSettings

def index(request):
    categories = DefectCategory.objects.all().order_by("name")
    settings = JobSettings.objects.first()
    context = {
        "categories":categories,
        "settings":settings,
        "active_page":"settings"
    }
    return render(request, "settings/index.html", context=context)

@csrf_exempt
def update_max_job_count(request):
    settings = JobSettings.objects.first()
    if request.method == 'POST':
        new_count = request.POST.get('new_count')
        try:
            new_count = int(new_count)  # convert string to int
        except (TypeError, ValueError):
            messages.error(request, 'Invalid number provided.')
            return redirect("settings_index")

        if settings:
            settings.max_job_count = new_count
            settings.save()
            messages.success(request, "New max job count successfully saved.")
            return redirect("settings_index")

    messages.error(request, 'Settings update failed. Please try again later.')
    return redirect("settings_index")



def defect_category_create(request):
    if request.method == "POST":
        form = DefectCategoryForm(request.POST)
        formset = DefectOptionFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            category = form.save()
            formset.instance = category
            formset.save()
            messages.success(request, "Defect category created successfully.")
            return redirect("settings_index")
    else:
        form = DefectCategoryForm()
        formset = DefectOptionFormSet()
    return render(request, "settings/defect_category_form.html", {"form": form, "formset": formset})

def defect_category_update(request, pk):
    category = get_object_or_404(DefectCategory, pk=pk)
    if request.method == "POST":
        form = DefectCategoryForm(request.POST, instance=category)
        formset = DefectOptionFormSet(request.POST, instance=category)
        if form.is_valid() and formset.is_valid():
            category = form.save()
            formset.instance = category  # <-- important
            formset.save()
            messages.success(request, "Defect category updated successfully.")
            return redirect("settings_index")
        else:
            print(formset.errors)
    else:
        form = DefectCategoryForm(instance=category)
        formset = DefectOptionFormSet(instance=category)
    return render(
        request, 
        "settings/defect_category_form.html", 
        {"form": form, "formset": formset, "category": category}
    )


def defect_category_delete(request, pk):
    category = get_object_or_404(DefectCategory, pk=pk)
    if request.method == "POST":
        category.delete()
        messages.success(request, "Defect category deleted successfully.")
        return redirect("settings_index")
    return render(request, "settings/defect_category_confirm_delete.html", {"category": category})

@csrf_exempt
def update_quota(request):
    settings = JobSettings.objects.first()
    if request.method == 'POST':
        new_quota = request.POST.get('new_quota')
        try:
            new_quota = int(new_quota)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid number provided.')
            return redirect("settings_index")

        if settings:
            settings.quota = new_quota
            settings.save()
            messages.success(request, "New quota successfully saved.")
            return redirect("settings_index")

    messages.error(request, 'Quota update failed. Please try again later.')
    return redirect("settings_index")


@csrf_exempt
def update_parttime_quota(request):
    settings = JobSettings.objects.first()
    if request.method == 'POST':
        new_parttime_quota = request.POST.get('new_parttime_quota')
        try:
            new_parttime_quota = int(new_parttime_quota)
        except (TypeError, ValueError):
            messages.error(request, 'Invalid number provided.')
            return redirect("settings_index")

        if settings:
            settings.parttime_quota = new_parttime_quota
            settings.save()
            messages.success(request, "New part-time quota successfully saved.")
            return redirect("settings_index")

    messages.error(request, 'Part-time quota update failed. Please try again later.')
    return redirect("settings_index")
