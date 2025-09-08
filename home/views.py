from django.shortcuts import render

def home(request):
	print(request.user.is_authenticated)
	return render(request,"home/index.html")