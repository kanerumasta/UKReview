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
from accounts.decorators import manager_required


# Dropzone view
@manager_required
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
        "total_uploaded_rows": total_uploaded_rows,  
    }
    return render(request, "dropzone/index.html", context=context)


@manager_required
def upload_file(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        try:
            batch_name = os.path.splitext(file.name)[0]
            df = pd.read_excel(file, engine="openpyxl")

            # ✅ required column names
            required_columns = ["Filename", "Enactment citation", "Provision", "Date"]
            file_columns = df.columns.tolist()

            # Check if all required columns are present
            missing = [col for col in required_columns if col not in file_columns]
            if missing:
                messages.error(
                    request,
                    f"Invalid file format. Missing columns: {', '.join(missing)}. "
                )
                return redirect('/dropzone/')

            # ✅ Prevent duplicate batch
            if Batch.objects.filter(name=batch_name).exists():
                messages.error(request, "Batch with this name already exists.")
                return redirect('/dropzone/')

            # ✅ Create batch
            batch = Batch.objects.create(name=batch_name)

            # ✅ Process rows
            for idx, row in df.iterrows():
                raw_date = str(row["Date"]).strip().replace("\u201c", "").replace("\u201d", "")
                try:
                    formatted_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                except ValueError:
                    messages.error(request, f"Invalid date format in row {idx+1}: {raw_date}")
                    return redirect('/dropzone/')

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

                print(f"Processing row {idx+1}")

            messages.success(request, "File uploaded and data saved successfully!")
            return redirect('/dropzone/')

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return render(request, "dropzone/index.html")

    return render(request, "dropzone/index.html")
