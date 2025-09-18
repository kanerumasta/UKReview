from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse

from .models import EnactmentAssignment, ProvisionJob, ProvisionJobSession
from enactments.models import Enactment
from defects.models import DefectLog


# Define the defect options
DEFECT_OPTIONS = {
    "Completeness": [
        {"check_type": "Missing text: multiple characters", "severity_level": 1},
        {"check_type": "Missing text: one character", "severity_level": 3},
        {"check_type": "Extra text", "severity_level": 2},
        {"check_type": "Missing spacing", "severity_level": 3},
        {"check_type": "Extra spacing", "severity_level": 4},
    ],
    "Structure": [
        {"check_type": "Sub-para nesting incorrect", "severity_level": 4},
        {"check_type": "Affected units mark up incorrect", "severity_level": 1},
        {"check_type": "Form structure incorrect", "severity_level": 1},
    ],
    "Chunking": [
        {"check_type": "Provision mark up incorrect", "severity_level": 1},
        {"check_type": "Information panel provision number incorrect", "severity_level": 1},
        {"check_type": "Schedules not present", "severity_level": 1},
        {"check_type": "Schedule parts not broken out", "severity_level": 1},
    ],
    "Hierarchy": [
        {"check_type": "Headings not present", "severity_level": 1},
        {"check_type": "Headings levels incorrect", "severity_level": 3},
    ],
    "Duplication": [
        {"check_type": "Duplicated text", "severity_level": 2},
    ],
    "Local Styling": [
        {"check_type": "Italics incorrect", "severity_level": 4},
        {"check_type": "Bold incorrect", "severity_level": 4},
    ],
    "Complex Content": [
        {"check_type": "Table columns/rows missing or added", "severity_level": 1},
        {"check_type": "Merged cells incorrect", "severity_level": 2},
        {"check_type": "Formulae/Images incorrect", "severity_level": 1},
    ],
    "Version": [
        {"check_type": "Version unavailable", "severity_level": 1},
        {"check_type": "Provision with Identified Issue or Error Message", "severity_level": 1},
    ],
}


def jobs_index(request):
    assignment = EnactmentAssignment.objects.filter(user=request.user, status = 'active').first()
    jobs = []
    if assignment:
        jobs = ProvisionJob.objects.filter(provision__enactment=assignment.enactment, status__in=['pending', 'active','onhold'])
    context = {
        'active_page': 'allocations',
        'jobs': jobs,
    }
    return render(request, 'jobs/index.html', context=context)


def allocate_enactment(request):
    # Logic for allocating enactments goes here
    
    if request.method == "POST":
        enactment = Enactment.objects.filter(assignments__isnull=True).first()

        if not enactment:
            return JsonResponse({"error": "No unallocated enactments available."}, status=400)

        EnactmentAssignment.objects.create(
            enactment=enactment,
            user=request.user,
        )
        
        ProvisionJob.objects.filter(provision__enactment=enactment, status="pending").update(user = request.user)


        return redirect("jobs")
    
    #redirect to jobs page after allocation
    return JsonResponse({"error": "Invalid request method."}, status=400)

    
def start_job(request, job_id):
    if request.method == "POST":
        try:
            job = ProvisionJob.objects.get(id=job_id, status="pending")
            job.status = "active"
            job.save()
            session = ProvisionJobSession.objects.create(provision_job=job)
            return redirect('job_detail', job_id=job.id)
        except ProvisionJob.DoesNotExist:
            return JsonResponse({"error": "Job not found or already started."}, status=404)

def job_detail(request, job_id):
    # Fetch the job and related defect logs
    job = get_object_or_404(ProvisionJob, id=job_id, user=request.user)
    defect_logs = DefectLog.objects.filter(provision_job=job)

    # Pass the defect options to the template
    context = {
        "job": job,
        "defect_logs": defect_logs,
        "defect_options": DEFECT_OPTIONS,
        "active_page":"Allocations"
    }
    return render(request, "jobs/detail.html", context)


def add_defect_log(request, job_id):
    if request.method == "POST":
        print(request.POST)
        # Get the job associated with the defect log
        job = get_object_or_404(ProvisionJob, id=job_id, user=request.user)

        # Create a new defect log
        DefectLog.objects.create(
            provision_job=job,
            category=request.POST.get("category"),
            check_type=request.POST.get("check_type"),
            severity_level=request.POST.get("severity_level"),
            issue_description=request.POST.get("issue_description"),
            expected_outcome=request.POST.get("expected_outcome", ""),
            actual_outcome=request.POST.get("actual_outcome", ""),
            screenshot=request.FILES.get("screenshot"),
            link=request.POST.get("link", ""),
            error_count=request.POST.get("error_count", 0),
            comments=request.POST.get("comments", ""),
        )

        # Redirect back to the job detail page
        return redirect("job_detail", job_id=job_id)

    # If the request is not POST, return a 405 Method Not Allowed response
    return JsonResponse({"error": "Invalid request method."}, status=405)