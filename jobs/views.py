from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
import time

from django.views.decorators.csrf import csrf_exempt

from .models import EnactmentAssignment, ProvisionJob, ProvisionJobSession
from enactments.models import Enactment
from defects.models import DefectLog

from django.utils import timezone
from django.db.models import Q, Exists, OuterRef
from django.contrib import messages


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
        jobs = ProvisionJob.objects.filter(provision__enactment=assignment.enactment, status__in=['pending', 'active','onhold'], user=request.user)
        for job in jobs:
            if job.status == 'active':
                job.status = 'onhold'
                sessions = ProvisionJobSession.objects.filter(provision_job = job,ended_at=None)
                for session in sessions:
                    session.ended_at = timezone.now()
                    session.save()
                job.save()
    context = {
        'active_page': 'allocations',
        'jobs': jobs,
    }
 
    return render(request, 'jobs/index.html', context=context)





def allocate_enactment(request):
    if request.method == "POST":
        # Find the first enactment that still has pending provision jobs
        pending_jobs = ProvisionJob.objects.filter(
            provision__enactment=OuterRef('pk'),
            status='pending'
        )

        enactment = Enactment.objects.annotate(
            has_pending_jobs=Exists(pending_jobs)
        ).filter(has_pending_jobs=True).first()

        if not enactment:
            return JsonResponse({"error": "No enactments with pending jobs available."}, status=400)

        # Create a new EnactmentAssignment
        assignment = EnactmentAssignment.objects.create(
            enactment=enactment,
            user=request.user,
        )

        # Assign only up to 10 unassigned, pending jobs
        job_ids = ProvisionJob.objects.filter(
            provision__enactment=enactment,
            status='pending',
            user__isnull=True,
            enactment_assignment__isnull=True
        ).values_list('id', flat=True)[:100]

        ProvisionJob.objects.filter(id__in=job_ids).update(
            user=request.user,
            enactment_assignment=assignment
        )

        return redirect("jobs")

    return JsonResponse({"error": "Invalid request method."}, status=400)

@csrf_exempt
def start_job(request, job_id):
    print('here')
    if request.method == "POST":
        try:
          
            # if ProvisionJob.objects.filter(status='active').exclude(id=job_id).exists(): 
            #     messages.error(request, f"Please complete your active job.")
            #     return redirect("jobs")
            job = ProvisionJob.objects.get(id=job_id)
            if job.status == 'pending':
                job.start_date = timezone.now()
                
            if job.status != 'active':
                session = ProvisionJobSession.objects.create(provision_job=job)
            job.status = "active"
            job.save()
        except ProvisionJob.DoesNotExist:
            messages.error(request,"Job does not exist")
            return redirect("jobs")
        return redirect('job_detail', job_id=job.id)
        
@csrf_exempt
def hold(request, job_id):
    print('HEREEE')
    if request.method == "POST":
        print(request.POST)
        job = get_object_or_404(ProvisionJob, id = job_id)
        last_session = job.sessions.filter(ended_at=None).first()
        if last_session:
            last_session.ended_at = timezone.now()
            
            last_session.save()
        job.status = "onhold"
        job.save()
   
        return redirect('jobs')
    return JsonResponse({"error": "Invalid request method."}, status=405)
    

@csrf_exempt
def submit_job(request, job_id):
    if request.method == "POST":
        submit_action = request.POST.get('submit_action','go_back')
        print(request.POST)

        job = get_object_or_404(ProvisionJob, id = job_id)

        last_session = job.sessions.filter(ended_at=None).first()
        assignment = job.enactment_assignment

        now = timezone.now()
        
        if last_session:
            last_session.ended_at = now
            job.status = "completed"
            job.end_date = now
            last_session.save()
            job.save()
            last_session.save()
            
        else:
            pass
        #set assignment complete of empty
        if not ProvisionJob.objects.filter(enactment_assignment=assignment, status__in=['pending','active','onhold']).exists():
            job.enactment_assignment.status = 'completed'
            job.enactment_assignment.save()

        print('Action', submit_action)

        if submit_action == 'start_another':
            next_job = ProvisionJob.objects.filter(
                user=request.user,
                status__in=['pending', 'active', 'onhold']
            ).exclude(id=job.id).first()
            if next_job:
                messages.success(request, "Job successfully submitted.")
                return redirect('job_detail', job_id=next_job.id)
            else:
                return redirect('jobs')
        elif submit_action == 'go_back':
            messages.success(request, "Job successfully submitted.")
            return redirect('jobs')
        return redirect('jobs')

        
def job_detail(request, job_id):
    # Fetch the job and related defect logs
    job = get_object_or_404(ProvisionJob, id=job_id, user=request.user)
    if not ProvisionJobSession.objects.filter(provision_job=job, ended_at=None).exists():
        new_session = ProvisionJobSession.objects.create(provision_job = job)
    job.status = 'active'
    job.save()
    

    defect_logs = DefectLog.objects.filter(provision_job=job)

    context = {
        "job": job,
        "defect_logs": defect_logs,
        "defect_options": DEFECT_OPTIONS,
        "active_page":"allocations"
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

@csrf_exempt
def edit_defect_log(request, job_id):
    if request.method == "POST":
        defect_id = request.POST.get("defect_id")
       
        defect = get_object_or_404(DefectLog, id=defect_id)

        # Update the defect log
        defect.category = request.POST.get("category")
        defect.check_type = request.POST.get("check_type")
        defect.severity_level = request.POST.get("severity_level")
        defect.issue_description = request.POST.get("issue_description")
        defect.expected_outcome = request.POST.get("expected_outcome", "")
        defect.actual_outcome = request.POST.get("actual_outcome", "")
        defect.comments = request.POST.get("comments", "")
        if "screenshot" in request.FILES:
            defect.screenshot = request.FILES["screenshot"]
        defect.save()

        return redirect("job_detail", job_id=job_id)

    return JsonResponse({"error": "Invalid request method."}, status=405)

@csrf_exempt
def delete_defect_log(request, defect_id):
    if request.method == "POST":
        defect = get_object_or_404(DefectLog, id=defect_id)
        defect.delete()
        return redirect("job_detail", job_id=defect.provision_job.id)

    return JsonResponse({"error": "Invalid request method."}, status=405)



    