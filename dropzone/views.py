from django.shortcuts import render

from enactments.models import Enactment, Provision, Batch
from django.http import JsonResponse
import pandas as pd
import os
from datetime import datetime
from django.shortcuts import redirect
from jobs.models import ProvisionJob
from django.contrib import messages
from django.core.paginator import Paginator



# Dropzone view
def index(request):
    try:
        jobs_list = ProvisionJob.objects.select_related("provision", "user").all()
        paginator = Paginator(jobs_list, 10)  # show 10 rows per page

        page_number = request.GET.get("page")
        jobs = paginator.get_page(page_number)

        # ✅ always count from the base queryset, not paginated jobs
        total_uploaded_rows = jobs_list.count()

    except ProvisionJob.DoesNotExist:
        jobs = []
        total_uploaded_rows = 0

    context = {
        "active_page": "dropzone",
        "jobs": jobs,
        "total_uploaded_rows": total_uploaded_rows,  # 👈 add here
    }
    return render(request, "dropzone/index.html", context=context)


def upload_file(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        try:
            batch_name = os.path.splitext(file.name)[0]
            df = pd.read_excel(file, engine="openpyxl")

      

            if Batch.objects.filter(name=batch_name).exists():
                messages.error(request, "Batch with this name already exists.")
                return redirect('/dropzone/')



            batch = Batch.objects.create(name=batch_name)

            for idx, row in df.iterrows():
                # Clean up date
                raw_date = str(row["Date"]).strip().replace("\u201c", "").replace("\u201d", "")
                formatted_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")

                # Access index (1-based if you prefer)
                row_number = idx + 1  

                enactment, _ = Enactment.objects.get_or_create(
                    title=row["Enactment citation"],
                    batch=batch,
                )

                provision, _ = Provision.objects.get_or_create(
                    enactment=enactment,
                    title=row["Provision"],
                    batch=batch,
                )

                ProvisionJob.objects.create(
                    provision=provision,
                    filename=row["Filename"],
                    date=formatted_date,
                )

                print(f"Processing row {row_number}")

            messages.success(request, "File uploaded and data saved successfully!")
            # return redirect("/jobs/")  # absolute path to jobs page
            return redirect('/dropzone/')


        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return render(request, "dropzone/index.html")

    return render(request, "dropzone/index.html")