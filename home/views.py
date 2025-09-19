from django.shortcuts import render
from jobs.models import EnactmentAssignment

def home(request):
	print(request.user.is_authenticated)
	return render(request,"home/index.html",{'active_page':'dashboard'})


def get_enactment_assignments(request):
    assignments = EnactmentAssignment.objects.all()
    context = {
        "assignments": assignments
    }
