from functools import wraps
from django.shortcuts import redirect

def manager_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # Adjust check depending on how you store "manager" (is it a role, group, or just username?)
        if not request.user.is_authenticated or request.user.username != "manager":
            return redirect("dashboard")
        return view_func(request, *args, **kwargs)
    return _wrapped_view
