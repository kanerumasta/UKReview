from django.shortcuts import render, redirect
from django.http import JsonResponse

from .models import EnactmentAssignment, ProvisionJob, ProvisionJobSession
from enactments.models import Enactment

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
        
        ProvisionJob.objects.filter(provision__enactment=enactment, status="pending")


        return redirect("jobs")
    
    #redirect to jobs page after allocation
    return JsonResponse({"error": "Invalid request method."}, status=400)

    
def start_job(request, job_id):
    if request.method == "POST":
        try:
            job = ProvisionJob.objects.get(id=job_id, user=request.user, status="pending")
            job.status = "active"
            job.save()
            session = ProvisionJobSession.objects.create(provision_job=job)
            return redirect('job_detail', job_id=job.id)
        except ProvisionJob.DoesNotExist:
            return JsonResponse({"error": "Job not found or already started."}, status=404)

def job_detail(request, job_id):
    try:
        job = ProvisionJob.objects.get(id=job_id, user=request.user)
        sessions = job.sessions.all()
        context = {
            'job': job,
            'sessions': sessions,
        }
        return render(request, 'jobs/detail.html', context=context)
    except ProvisionJob.DoesNotExist:
        return JsonResponse({"error": "Job not found."}, status=404)