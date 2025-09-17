from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import login
from django.shortcuts import render, redirect

from django.contrib.auth.decorators import login_not_required


@login_not_required
def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')  # Change to your homepage
    else:
        form = AuthenticationForm()

    return render(request, 'accounts/login.html', {'form': form})