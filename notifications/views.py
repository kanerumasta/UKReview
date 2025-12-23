from django.shortcuts import render
from .services import notify_user
from django.http import JsonResponse

def test(request):
    user = request.user
    notify_user(user = user, title='hahah',description='kuyawa nimo ue')
    return JsonResponse({"ok": True})