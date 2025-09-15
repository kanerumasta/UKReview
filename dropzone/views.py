from django.shortcuts import render

# Create your views here.
def index(request):
    context = {
        'active_page': 'dropzone',
    }

    return render(request, 'dropzone/index.html',context=context)