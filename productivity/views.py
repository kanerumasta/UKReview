from django.shortcuts import render

def index(request):
    context = {
        'active_page': 'productivity',
    }
    return render(request, 'productivity/index.html',context=context)