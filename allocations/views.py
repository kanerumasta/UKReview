from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import get_user_model
from jobs.models import ProvisionJob
from django.core.paginator import Paginator
from accounts.decorators import manager_required



User = get_user_model()

@manager_required
def allocations_index(request):

    jobs = ProvisionJob.objects.filter(user__isnull=False).select_related(
        "user", "provision", "enactment_assignment__enactment"
    ).order_by("-id")

    # Filters
    user_id = request.GET.get("user")
    status = request.GET.get("status", "pending")  # default to pending

    if user_id:
        jobs = jobs.filter(user_id=user_id)
    if status:
        jobs = jobs.filter(status=status)

    # Pagination
    paginator = Paginator(jobs, 10)  # 10 per page
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Handle reassignment
    if request.method == "POST" and "reassign_to" in request.POST:
        job_ids = request.POST.getlist("jobs")
        reassign_to_id = request.POST.get("reassign_to")

        if not job_ids:
            messages.error(request, "No jobs selected for reassignment.")
            return redirect("allocations_index")

        if not reassign_to_id:
            messages.error(request, "Please select a user to reassign to.")
            return redirect("allocations_index")

        new_user = get_object_or_404(User, id=reassign_to_id)
        updated = ProvisionJob.objects.filter(id__in=job_ids).update(user=new_user)
        messages.success(request, f"{updated} job(s) reassigned to {new_user.username}.")
        return redirect("allocations_index")

    users = User.objects.all()
    return render(request, "allocations/index.html", {
        "jobs": jobs,
        "users": users,
        "selected_user": user_id,
        "selected_status": status,
        "status_choices": ProvisionJob.STATUS_CHOICES,
        "page_obj": page_obj,
        "active_page": "allocations",
    })
