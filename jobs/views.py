from django.shortcuts import render

def jobs_index(request):
    context = {
        'active_page': 'allocations',
    }
    return render(request, 'jobs/index.html', context=context)