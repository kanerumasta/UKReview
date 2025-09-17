from django.shortcuts import render

from enactments.models import Enactment, Provision, Batch
from django.http import JsonResponse
import pandas as pd
import os
from datetime import datetime

from jobs.models import ProvisionJob

# Create your views here.
def index(request):
    context = {
        'active_page': 'dropzone',
    }

    return render(request, 'dropzone/index.html',context=context)



def upload_file(request):
    if request.method == "POST" and request.FILES.get("file"):
        file = request.FILES["file"]
        try:
            # Read the Excel file into a DataFrame
            batch_name = os.path.splitext(file.name)[0]
            df = pd.read_excel(file, engine="openpyxl")

            if  Batch.objects.filter(name=batch_name).exists():
                return JsonResponse({"error": "Batch with this name already exists."}, status=400)
            

            batch = Batch.objects.create(name=batch_name)
            

            # Iterate through the rows and save to the database
            for _, row in df.iterrows():
                # Clean and reformat the date
                raw_date = str(row["Date"]).strip().replace("\u201c", "").replace("\u201d", "")
                formatted_date = datetime.strptime(raw_date, "%d/%m/%Y").strftime("%Y-%m-%d")
                
                # Get or create the Enactment
                enactment, _ = Enactment.objects.get_or_create(
                    title=row["Enactment citation"],
                    batch=batch,
                )


                provision, _ = Provision.objects.get_or_create(
                    enactment=enactment,
                    title=row["Provision"],
                    batch=batch,
                )

                # Create a ProvisionJob for each provision
                ProvisionJob.objects.create(
                    provision=provision, 
                    filename=row["Filename"],
                    date=formatted_date,
                )

            return JsonResponse({"message": "File uploaded and data saved successfully!"})
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    return render(request, "dropzone/index.html")