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
from dateutil.parser import parse as parse_date

###UK REVIEW
# Dropzone view
@manager_required
def index(request):

    try:
        jobs_list = ProvisionJob.objects.select_related("provision", "user").all().order_by('-last_edited')

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


#Version that only uses the first sheet of the excel

# @manager_required
# def upload_file(request):
#     if request.method == "POST" and request.FILES.get("file"):
#         file = request.FILES["file"]
#         try:
#             batch_name = os.path.splitext(file.name)[0]
#             df = pd.read_excel(file, engine="openpyxl")

#             # ✅ required column names
#             required_columns = ["Enactment citation", "Provision", "Date"]
#             file_columns = df.columns.tolist()

#             # Check if all required columns are present
#             missing = [col for col in required_columns if col not in file_columns]
#             if missing:
#                 messages.error(
#                     request,
#                     f"Invalid file format. Missing columns: {', '.join(missing)}. "
#                 )
#                 return redirect('dropzone_index')

#             # ✅ Prevent duplicate batch
#             if Batch.objects.filter(name=batch_name).exists():
#                 messages.error(request, "Batch with this name already exists.")
#                 return redirect('dropzone_index')

#             # ✅ Create batch
#             batch = Batch.objects.create(name=batch_name)

#             # ✅ Process rows
#             for idx, row in df.iterrows():

#                 raw_date = str(row["Date"]).strip().replace("\u201c", "").replace("\u201d", "")
                
#                 try:
#                     # parse_date will automatically detect the format
#                     formatted_date = parse_date(raw_date, dayfirst=True).strftime("%Y-%m-%d")
#                 except (ValueError, TypeError):
#                     batch.delete()
#                     messages.error(request, f"Invalid date format in row {idx+1}: {raw_date}")
#                     return redirect('dropzone_index')
#                 enactment, _ = Enactment.objects.get_or_create(
#                     title=row.get("Enactment citation"),
#                     batch=batch,
#                 )

#                 provision, _ = Provision.objects.get_or_create(
#                     enactment=enactment,
#                     title=row["Provision"],
#                     batch=batch,
#                 )

#                 ProvisionJob.objects.create(
#                     provision=provision,
#                     filename=row.get("Filename"),
#                     provision_identification = row.get("provision_id"),
#                     enactment_identification = row.get("enactment_id"),
#                     enactment_type = row.get("enactment_type"),
#                     have_am_or_not=row.get("have_am_or_not"),
#                     date=formatted_date,
#                 )

#                 print(f"Processing row {idx+1}")

#             messages.success(request, "File uploaded and data saved successfully!")
#             return redirect('dropzone_index')

#         except Exception as e:
#             messages.error(request, f"Error: {str(e)}")
#             return render(request, "dropzone/index.html")

#     return render(request, "dropzone/index.html")

####



#Users all identical columns sheets 
@manager_required
def upload_file(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        try:
            batch_name = os.path.splitext(file.name)[0]

            # ⬅️ Load ALL sheets
            sheets = pd.read_excel(file, sheet_name=None, engine="openpyxl")

            # ⬅️ Identify first sheet (default)
            default_sheet = next(iter(sheets.values()))
            required_columns = ["Enactment citation", "Provision", "Date"]

            # Validate default sheet columns
            default_columns = default_sheet.columns.tolist()
            missing = [c for c in required_columns if c not in default_columns]
            if missing:
                messages.error(
                    request,
                    f"Invalid file format. Missing columns in default sheet: {', '.join(missing)}."
                )
                return redirect("dropzone_index")

            # ⬅️ Combine sheets that MATCH default sheet columns
            combined = []
            for sheet_name, df in sheets.items():
                if list(df.columns) == default_columns:
                    combined.append(df)
                else:
                    print(f"Skipping sheet '{sheet_name}' — columns do not match default")

            if not combined:
                messages.error(request, "No sheets have matching columns to the default sheet.")
                return redirect("dropzone_index")

            df_all = pd.concat(combined, ignore_index=True)

            # Prevent duplicate batch
            if Batch.objects.filter(name=batch_name).exists():
                messages.error(request, "Batch with this name already exists.")
                return redirect("dropzone_index")

            # Create batch
            batch = Batch.objects.create(name=batch_name)

            # Process rows
            for idx, row in df_all.iterrows():

                raw_date = str(row["Date"]).strip().replace("\u201c", "").replace("\u201d", "")

                try:
                    formatted_date = parse_date(raw_date, dayfirst=True).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    batch.delete()
                    messages.error(request, f"Invalid date format in row {idx+1}: {raw_date}")
                    return redirect("dropzone_index")

                enactment, _ = Enactment.objects.get_or_create(
                    title=row.get("Enactment citation"),
                    batch=batch,
                )

                provision, _ = Provision.objects.get_or_create(
                    enactment=enactment,
                    title=row["Provision"],
                    batch=batch,
                )

                ProvisionJob.objects.create(
                    provision=provision,
                    filename=row.get("Filename"),
                    provision_identification=clean_excel_id(row.get("provision_id")),
                    enactment_identification=clean_excel_id(row.get("enactment_id")),
                    enactment_type=row.get("enactment_type"),
                    have_am_or_not=row.get("have_am_or_not"),
                    date=formatted_date,
                )

                print(f"Processing row {idx+1}")

            messages.success(request, "File uploaded and data saved successfully!")
            return redirect("dropzone_index")

        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return render(request, "dropzone/index.html")

    return render(request, "dropzone/index.html")


def clean_excel_id(value):
    if value is None or pd.isna(value):
        return None
    # Convert floats like 95472.0 → "95472"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
