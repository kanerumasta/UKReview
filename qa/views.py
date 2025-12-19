from django.shortcuts import render, redirect, get_object_or_404
from jobs.models import ProvisionJob
from django.urls import reverse
from enactments.models import Batch
from django.core.paginator import Paginator
from datetime import datetime
from settings.models import QASettings
from django.core.exceptions import ImproperlyConfigured
from .models import QACluster,QAMissingDefectLog, QAJob, QASession
from django.contrib import messages
from .helpers import get_sampling_values, stratified_sampling
from django.db.models import Count, Q, Min
import json
from django.http import JsonResponse
from defects.models import DefectLog, DefectCategory, DefectOption
from django.db import transaction
# views.py
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.csrf import csrf_exempt
import json
from django.core.cache import cache
from django.utils import timezone
from collections import OrderedDict


from django.db.models import Count, Q, FloatField, ExpressionWrapper, F
CACHE_TTL = 60 * 60  # 1 hour

def index(request):
    all_clusters = QACluster.objects.all().annotate(
        selected_qa_jobs_count=Count('qa_jobs', filter=Q(qa_jobs__is_selected=True)),
        total_qa_jobs_count=Count('qa_jobs'),
        completed_qa_jobs_count=Count('qa_jobs', filter=Q(qa_jobs__status='completed'))
    ).annotate(
        # Calculate completion percentage
        progress_percentage=ExpressionWrapper(
            F('completed_qa_jobs_count') * 100.0 / F('sample_size'),
            output_field=FloatField()
        )
    )
    
    # For clusters: exclude completed and certain manager statuses
    clusters = all_clusters.exclude(qa_status='completed').exclude(
        manager_status__in=['recompute', 'rework']
    )
    
    completed_clusters = all_clusters.filter(qa_status="completed").exclude(manager_status='recompute')
    recomputed_clusters = all_clusters.filter(manager_status='recompute')

    context = {
        "clusters": clusters,
        "completed_clusters": completed_clusters,
        "recomputed_clusters": recomputed_clusters,
        "active_page": "qa",
        "title": "QA Dashboard",
        "is_initial_title": True,
    }
    return render(request, 'qa/index.html', context=context)



def qa_loading(request):
    batches = Batch.objects.all().order_by('-id')
    qa_settings = QASettings.objects.first()

    if qa_settings is None:
        raise ImproperlyConfigured("QASettings must be created before accessing the QA dashboard.")

    # --- Determine selected batch ---
    selected_batch_id = request.GET.get("batch")
    if selected_batch_id:
        selected_batch = Batch.objects.filter(id=selected_batch_id).first()
    else:
        # Default: latest available batch
        selected_batch = batches.last()

    # If still none (no batches at all)
    if selected_batch is None:
        return render(request, "qa/qa_loading.html", {
            "page_obj": None,
            "cluster_name": None,
            "sampling_data": None,
            "batches": [],
            "selected_batch_id": None
        })

    # --- Jobs filtered based on selected batch ---
    jobs_for_sampling = ProvisionJob.objects.filter(
        status="completed",
        provision__batch=selected_batch.id,
        in_qa = False
    ).order_by('-created_at')

    # --- Cluster name logic ---
    last_cluster = QACluster.objects.last()
    next_cluster_number = last_cluster.id + 1 if last_cluster else 1

    cluster_name = f"LNKIL_{datetime.now().strftime('%Y%m%d')}_{next_cluster_number:03d}_Counter1"

    # --- Sampling logic ---
    lot_size = jobs_for_sampling.count()

    sampling_data = get_sampling_values(lot_size, qa_settings.sampling_type)
   


    # --- Pagination ---
    paginator = Paginator(jobs_for_sampling, 10)
    page = request.GET.get("page", 1)
    page_obj = paginator.get_page(page)

    context = {
        "page_obj": page_obj,
        "cluster_name": cluster_name,
        "sampling_data": sampling_data,
        "batches": batches,
        "selected_batch_id": selected_batch.id,
        "title":"QA Loading",
        "is_initial_title":True
    }
   

    return render(request, "qa/qa_loading.html", context)

def load_to_qa(request, batch_id):
    if request.method != "POST":
        return redirect("qa-loading")

    qa_settings = QASettings.objects.first()

    jobs_for_sampling = ProvisionJob.objects.filter(
        status="completed",
        provision__batch=batch_id,
        in_qa=False
    )

    lot_size = jobs_for_sampling.count()

    sampling_data = get_sampling_values(lot_size, qa_settings.sampling_type)

    sample_size = sampling_data['sample_size']
    sampling_type = sampling_data['type']
    

    if not jobs_for_sampling.exists():
        messages.error(request, "No completed jobs found for this batch.")
        return redirect("qa-loading")

    try:
        # Create the cluster
        cluster = QACluster.objects.create(
            created_by=request.user,
            sample_size = sample_size,
            sampling_type = sampling_type
        )

        sampled_jobs = stratified_sampling(jobs_for_sampling, sample_size)

        sampled_ids = set(j.id for j in sampled_jobs)

        for job in jobs_for_sampling:
            qa_job = QAJob.objects.create(
                qa_cluster = cluster,
                job = job,
                is_selected =  job.id in sampled_ids
            )
            job.in_qa = True
            job.save()
            

        messages.success(request, f"{jobs_for_sampling.count()} jobs successfully submitted to QA.")
        return redirect("qa-detail", cluster_id = cluster.id)
    except Exception as e:
        print(e)
        messages.error(request, "Error creating a cluster.")

    return redirect("qa-loading")

def provision_jobs_page(request, cluster_id):
    cluster =  get_object_or_404(QACluster, id = cluster_id)
    context =  {
        "cluster_id":cluster_id,
        "active_page":"qa", 
        "cluster":cluster,
        "title":cluster.name,
        "back_title":"QA",
        "back_url": reverse('qa-index')

    }

    return render(request,"qa/provision_jobs.html",context =context)

def defect_logs_page(request, job_id):
    categories = DefectCategory.objects.prefetch_related('options').all()
    qa_job = get_object_or_404(QAJob, id = job_id)
    missing_defects = QAMissingDefectLog.objects.filter(qa_job = qa_job)


    context = {
        "qa_job":qa_job,
        "categories":categories,
        "missing_defects":missing_defects,
        "title":"QA Job Review: Defect Logs",
        "back_title":qa_job.qa_cluster.name,
        "back_url":reverse('qa-detail', args=[qa_job.qa_cluster.id]),
        "back_title2":"QA",
        "back_url2":reverse('qa-index'),
        "active_page":'qa'
    } 
        
    #Allocated the provision to the current QA User if none
    if not qa_job.qa_user:
        qa_job.qa_user = request.user
        if qa_job.status != QAJob.COMPLETED:
            qa_job.status = "ongoing"
        qa_job.save()

    #Create a session if None
    last_undended_session = QASession.objects.filter(qa_job = qa_job, ended_at__isnull=True).first()
    if not last_undended_session:
        QASession.objects.create(qa_job=qa_job)

        

    return render(request, 'qa/defect_logs.html', context=context)

def qa_start(request, qa_job_id):
    if request.method == "POST":
        with transaction.atomic():
            qa_job = QAJob.objects.select_for_update().get(id = qa_job_id)
            if qa_job.qa_user is not None and qa_job.qa_user != request.user:
                messages.error(request, "Job is already assigned to other user.")
                return redirect('qa-detail', cluster_id = qa_job.qa_cluster.id)
            
            if qa_job.status  in [QAJob.NEW, QAJob.PAUSED, QAJob.ONHOLD]:
                if not qa_job.start_date:
                    qa_job.start_date = datetime.now()
                qa_job.status = QAJob.ONGOING
                qa_job.qa_user = request.user
                unended_session = QASession.objects.filter(qa_job = qa_job, ended_at__isnull = True ).first()

                #Create a new session if no pending session
                if unended_session is None:
                    QASession.objects.create(qa_job = qa_job)

                qa_job.save()
            
            if qa_job.qa_cluster.qa_status != 'ongoing' and qa_job.qa_cluster.qa_status != 'completed':
                qa_job.qa_cluster.qa_status = 'ongoing'
                qa_job.qa_cluster.save()

            return redirect('qa-defect-logs', job_id = qa_job_id)

def qa_resume(request, qa_job_id):
    qa_job = get_object_or_404(QAJob, id = qa_job_id)
    if request.method == "POST":
        qa_job.status = "ongoing"

        if qa_job.start_date is None:
            qa_job.start_date = datetime.now()
            
        
        #Handle session
        last_unended_session = QASession.objects.filter(qa_job = qa_job, ended_at__isnull=True)
        if not last_unended_session.exists():
            QASession.objects.create(qa_job=qa_job)
        qa_job.save()
    return redirect('qa-defect-logs',job_id = qa_job_id)

def qa_pause(request, qa_job_id):
    qa_job = get_object_or_404(QAJob, id = qa_job_id)
    if request.method == "POST":
        qa_job.status = "paused"
        
        #handle session
        last_unended_session = QASession.objects.filter(qa_job = qa_job, ended_at__isnull=True).first()

        if last_unended_session is not None:
            last_unended_session.ended_at = datetime.now()
            last_unended_session.save()
        qa_job.save()

        fallback_url = reverse('qa-defect-logs', args=[qa_job_id])

        # Redirect to the same page
        return redirect(request.META.get('HTTP_REFERER', fallback_url))


def qa_submit(request, qa_job_id):
    qa_job = get_object_or_404(QAJob, pk=qa_job_id)
    
    # Check if user has permission to submit this QA job
    if qa_job.qa_user != request.user:
        messages.error(request, "You don't have permission to submit this QA job.")
        return redirect("qa-detail", cluster_id=qa_job.qa_cluster.id)

    if request.method == "POST":
        answers_json = request.POST.get("answers_json", "{}")
        
        try:
            answers = json.loads(answers_json)
        except json.JSONDecodeError:
            messages.error(request, "Invalid data format. Please try again.")
            return redirect("qa-defect-logs", job_id=qa_job.id)
        
        # Get all defects for this job
        defects = qa_job.job.defect_logs.all()

        # Initialize list for defect IDs with errors
        error_defect_ids = []
        
        # Check if there are any defects to validate
        if defects.exists():
            validation_errors = []
            all_defects_answered = True
            
            # Validate each defect
            for defect in defects:
                defect_id = str(defect.id)
                
                # Check if defect is in answers
                if defect_id not in answers:
                    validation_errors.append(f"Please review all defect logs.")
                    all_defects_answered = False
                    error_defect_ids.append(defect.id)
                    continue
                
                answer_data = answers[defect_id]
                
                # Check if answer exists and is valid
                if 'answer' not in answer_data or not answer_data['answer']:
                    validation_errors.append(f"{defect.id}: Please select Yes or No.")
                    all_defects_answered = False
                    error_defect_ids.append(defect.id)
                    continue
                
                answer = answer_data['answer'].lower()
                if answer not in ['yes', 'no']:
                    validation_errors.append(f"{defect.id}: Invalid answer. Must be 'Yes' or 'No'.")
                    all_defects_answered = False
                    error_defect_ids.append(defect.id)
                    continue
                
                # Check if remarks are provided for "no" answers
                if answer == 'no':
                    remarks = answer_data.get('remarks', '').strip()
                    if not remarks:
                        validation_errors.append(f"{defect.id}: Remarks are required for incorrect defects.")
                        all_defects_answered = False
                        error_defect_ids.append(defect.id)
            
            # If validation errors exist, show them and return to form
            if validation_errors:
                # Store error defect IDs in session
                request.session['qa_validation_errors'] = error_defect_ids
                request.session.modified = True
                
                for error in validation_errors:
                    messages.error(request, error)
                
                return redirect("qa-defect-logs", job_id=qa_job.id)
            
            # If not all defects are answered
            if not all_defects_answered:
                # Store error defect IDs in session
                request.session['qa_validation_errors'] = error_defect_ids
                request.session.modified = True
                
                messages.error(request, "Please answer all defects before submitting.")
                return redirect("qa-defect-logs", job_id=qa_job.id)
        
        # Clear any previous validation errors from session
        if 'qa_validation_errors' in request.session:
            del request.session['qa_validation_errors']
        
        # If validation passes, save the answers
        try:
            all_correct = True
            for defect_id_str, values in answers.items():
                try:
                    defect = DefectLog.objects.get(pk=defect_id_str, provision_job=qa_job.job)
                    
                    answer = values.get("answer", "").lower()
                    remarks = values.get("remarks", "").strip()
                    
                    # Validate answer before saving
                    if answer not in ['yes', 'no']:
                        continue  # Skip invalid entries

                    #Fail job if not all answers are 'YES'

                    if answer.lower() != 'yes':
                        all_correct = False
                    
                    defect.qa_correct = answer
                    defect.qa_remarks = remarks # Clear remarks for 'yes'
                    defect.save()
                    
                except (DefectLog.DoesNotExist, ValueError):
                    continue  # Skip invalid defect IDs
            
            qa_job.outcome = 'pass' if all_correct else 'fail'

            
            # Update QA job status and end session
            qa_job.status = 'completed'
            qa_job.end_date = datetime.now()
                
            # End any active session
            last_session = QASession.objects.filter(qa_job=qa_job, ended_at__isnull=True).first()
            if last_session:
                last_session.ended_at = datetime.now()
                last_session.save()

            #Error count of the job

            missing_defects_count = QAMissingDefectLog.objects.filter(qa_job = qa_job).count()
            error_defects_count = sum(1 for v in answers.values() if v.get('answer') == 'no')

            qa_job.job_error_count = missing_defects_count + error_defects_count
            
            qa_job.save()

            
            messages.success(request, "QA results submitted successfully!")
            
            # === GET NEXT QA JOB ===
            cluster = qa_job.qa_cluster
            qa_jobs = cluster.qa_jobs.filter(is_selected=True)
            
            next_qa_job = qa_jobs.filter(
                qa_user__isnull=True
            ).exclude(
                status='completed'
            ).exclude(
                id=qa_job.id
            ).first()
            if next_qa_job:
                # Assign the next job to current user
                next_qa_job.qa_user = request.user
                next_qa_job.status = 'ongoing'
                next_qa_job.save()
                
                QASession.objects.create(qa_job=next_qa_job)
                # messages.info(request, f"Moving to next QA job: {next_qa_job.job.provision.title}")
                return redirect("qa-defect-logs", job_id=next_qa_job.id)
            
            else:
                # Check if all jobs in cluster are complete
                cluster.qa_status = 'completed'
                
                # Check if all selected QA jobs are COMPLETED
                all_complete = not qa_jobs.exclude(status='completed').exists()

                if all_complete:
                    
                    # Determine if cluster passed or failed

                    all_pass = not qa_jobs.exclude(outcome='pass').exists()
                    cluster.final_status = 'pass' if all_pass else 'fail'
                    cluster.completed_at = datetime.now()
                
                cluster.save()
                
                messages.success(request, "All QA jobs in this cluster are complete!")
                return redirect("qa-detail", cluster_id=cluster.id)
                
        except Exception as e:
            messages.error(request, f"Error saving QA results: {str(e)}")
            return redirect("qa-defect-logs", job_id=qa_job.id)
    
    # If not POST request, redirect to defect logs
    return redirect("qa-defect-logs", job_id=qa_job.id)

def qa_add_missing(request, qa_id):
    if request.method != "POST":
        return redirect("qa-page", qa_id=qa_id)
    
    defect_id = request.POST.get("defect_option")
    defect_option = get_object_or_404(DefectOption, id = defect_id)

    remarks = request.POST.get("remarks", "")

    qa_job = get_object_or_404(QAJob, id=qa_id)
    remarks = request.POST.get("remarks")

    # Validate
    if not defect_id or not remarks:
        messages.error(request, "All fields are required.")
        return redirect("qa-defect-logs", job_id=qa_job.id)

    QAMissingDefectLog.objects.create(
        qa_job = qa_job,
        category=defect_option.category.name,
        check_type=defect_option.check_type,
        remarks=remarks
    )

    messages.success(request, "Missing defect log added.")
    return redirect("qa-defect-logs", job_id=qa_job.id)

def qa_poll_data(request):
    all_clusters = QACluster.objects.all()

    active = (
    all_clusters
    .annotate(
        jobs_count=Count('qa_jobs'),   # total jobs
        selected=Count('qa_jobs', filter=Q(qa_jobs__is_selected=True))
    )
    .exclude(qa_status="completed")
    .values('id', 'name', 'created_at', 'jobs_count', 'selected')
)

    completed = (
    all_clusters
    .filter(qa_status="completed")
    .annotate(
        jobs_count=Count('qa_jobs'),
        selected=Count('qa_jobs', filter=Q(qa_jobs__is_selected=True))
    )
    .values('id', 'name', 'created_at', 'jobs_count', 'selected')
)
    

    print(list(active))


    return JsonResponse({
        "clusters": list(active),
        "completed_clusters": list(completed)
    })

def qa_jobs_poll(request, cluster_id):
    cluster = get_object_or_404(QACluster, id=cluster_id)

    jobs = cluster.qa_jobs.filter(
        Q(is_selected=True)
    ).order_by('-status')

        
    #Handle auto pause
    ongoing_user_qa_jobs = jobs.filter( qa_user = request.user, status=QAJob.ONGOING)
    
    if ongoing_user_qa_jobs.exists():
        for job in ongoing_user_qa_jobs:
            job.status = QAJob.PAUSED
            last_session = QASession.objects.filter(qa_job = job, ended_at__isnull=True).first()
            if last_session:
                last_session.ended_at = datetime.now()
                last_session.save()
            job.save()

    data = []

    for j in jobs:
        data.append({
            "id": j.id,
            "filename": j.job.filename or "-",
            "provision": j.job.provision.title,
            "enactment": j.job.provision.enactment.title,
            "date": j.job.date.strftime("%m/%d/%Y") if j.job.date else "",
            "batch": j.job.provision.enactment.batch.name,
            "user": j.qa_user.get_fullname().strip() or j.qa_user.username if j.qa_user else "unassigned",
            "submitted": j.job.end_date.strftime('%b-%d-%Y') if j.job.end_date else "",
            "start_action_url": reverse("qa-start", args=[j.id]),
            "resume_action_url":reverse("qa-resume", args=[j.id]),
            "pause_action_url":reverse("qa-pause", args=[j.id]),
            "status": j.status,
            "can_resume": (
            j.qa_user == request.user 
            and j.status in [QAJob.PAUSED, QAJob.ONGOING]
        ),
            "can_pause":(
                j.qa_user == request.user and j.status in [QAJob.ONGOING]
            ),
            "is_mine":j.qa_user == request.user
        })

    return JsonResponse({"jobs": data})

@require_POST
@csrf_exempt
def clear_qa_errors(request):

    """Clear QA validation errors from session"""
    try:
        if 'qa_validation_errors' in request.session:
            del request.session['qa_validation_errors']
            request.session.modified = True
        return JsonResponse({'status': 'success'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})

def qqa_report(request, cluster_id):
    cluster  = get_object_or_404(QACluster, id = cluster_id)
    tab = request.GET.get('tab', 'project')


    context = {
        'title':'QQA Report',
        'back_title':'QA Reports',
        'back_url':reverse('qa-reports-index'),
        'cluster':cluster,
        'active_tab':'project'
    }

    if tab == 'project':
        return render(request,'qa/qqa_report.html', context=context)
    


    elif tab == 'error-log':
        cache_key = f"qqa:error_logs:cluster:{cluster.id}"

        error_logs = cache.get(cache_key)
        if error_logs is None:
            error_logs =  DefectLog.objects.filter(
                    provision_job__qa_job__qa_cluster=cluster,
                    provision_job__qa_job__is_selected = True
                ).select_related(
                    "provision_job",
                    "provision_job__qa_job",
                    "provision_job__qa_job__qa_cluster"
                )
            error_logs = list(error_logs)
            cache.set(cache_key, error_logs, CACHE_TTL)

        # Add can_dispute attribute
        for log in error_logs:
            log.can_dispute = (log.qa_correct == "no" and log.dispute_reason is None)

         # Group defect logs by provision_job
        grouped_logs = OrderedDict()
        for log in error_logs:
            job = log.provision_job
            if job not in grouped_logs:
                grouped_logs[job] = []
            grouped_logs[job].append(log)


        context['grouped_logs'] = grouped_logs
        context['active_tab'] = 'error-log'
        return render(request,'qa/error_log.html', context=context)
    


    elif tab == 'defect-log':
        cache_key = f"qqa:defect_logs:cluster:{cluster.id}"

        defect_logs = cache.get(cache_key)
        if defect_logs is None:
            defect_logs =  DefectLog.objects.filter(
                    provision_job__qa_job__qa_cluster=cluster
                ).select_related(
                    "provision_job",
                    "provision_job__qa_job",
                    "provision_job__qa_job__qa_cluster"
                )
            defect_logs = list(defect_logs)
            print('DEFECT LG', defect_logs)
            cache.set(cache_key, defect_logs, CACHE_TTL)


        # Add can_dispute attribute

         # Group defect logs by provision_job
        grouped_logs = OrderedDict()
        for log in defect_logs:
            job = log.provision_job
            if job not in grouped_logs:
                grouped_logs[job] = []
            grouped_logs[job].append(log)

        context['active_tab'] = 'defect-log'
        context['grouped_logs'] = grouped_logs
        return render(request,'qa/defect_logs_tab.html', context=context)
    

    elif tab == 'query-log':
        context['active_tab'] = 'query-log'
        return render(request,'qa/query_log.html', context=context)
    


    elif tab == 'enactments':
        cache_key  = f"qqa:enactments:cluster:{cluster_id}"
        provision_jobs = cache.get(cache_key)
        
        if provision_jobs is None:
            provision_jobs = (
                    ProvisionJob.objects
                    .filter(qa_job__qa_cluster=cluster)
                    .annotate(lowest_severity_level=Min("defect_logs__severity_level"))
                    
                )

            provision_jobs = list(provision_jobs)

            cache.set(cache_key, provision_jobs, CACHE_TTL)

        
        grouped_logs = OrderedDict()
        for job in provision_jobs:
            enactment = job.provision.enactment
            if enactment not in grouped_logs:
                grouped_logs[enactment] = []
            grouped_logs[enactment].append(job)

        context['grouped_logs'] = grouped_logs
        context['active_tab'] = 'enactments'
        context['batch'] = provision_jobs[0].provision.batch.name
        return render(request,'qa/enactments.html', context=context)


    return render(request,'qa/qqa_report.html', context=context)

def add_dispute(request):

    defect_id = request.POST.get('defect_log_id')
    if defect_id:
        defect = get_object_or_404(DefectLog, id = defect_id)
    if request.method == 'POST' and defect is not None:
        dispute_reason = request.POST.get('dispute_reason')
        if dispute_reason:
            defect.dispute_reason = dispute_reason
            defect.disputed_by = request.user
            defect.dispute_date = timezone.now()
            

            defect.save()

            # CLEAR THE CACHE for this cluster's error logs
            cluster_id = defect.provision_job.qa_job.qa_cluster.id
            cache_key = f"qqa:error_logs:cluster:{cluster_id}"
            cache.delete(cache_key)

    return redirect(request.META.get('HTTP_REFERER', 'qa-index'))


@require_POST
@csrf_exempt
def recompute(request):
    if request.method == 'POST':
        cluster_id = request.POST.get('cluster_id')

        if cluster_id:
            cluster = get_object_or_404(QACluster, id = cluster_id)

            cluster.manager_status = 'recompute'
            cluster.final_status = 'ongoing'
            cluster.qa_status = 'ongoing'
            cluster.increment_counter()
            cluster.save()

            sampled_jobs = cluster.qa_jobs.filter(is_selected=True)

            for job in sampled_jobs:
                job.is_selected = False
                job.outcome = None
                job.start_date = None
                job.end_date = None
                job.job_error_count = None
                job.in_qa = False
                job.status = 'new'
                job.qa_user = None
                job.save()

            #Do sampling

            jobs_for_sampling = []

            for qa_job in cluster.qa_jobs.all():
                jobs_for_sampling.append(qa_job.job)

            sampled_jobs = stratified_sampling(jobs_for_sampling, cluster.sample_size)

            sampled_ids = set(j.id for j in sampled_jobs)

            for job in jobs_for_sampling:
                print('JOB', job.id)

                
                job.qa_job.is_selected =  job.id in sampled_ids
                
                job.in_qa = True
                job.save()
                job.qa_job.save()
                

            #clear cache

            cache_key1 = f"qqa:error_logs:cluster:{cluster_id}"
            cache_key2 = f"qqa:defect_logs:cluster:{cluster_id}"
            cache.delete(cache_key1)
            cache.delete(cache_key2)

    return redirect( 'qa-reports-index')
































