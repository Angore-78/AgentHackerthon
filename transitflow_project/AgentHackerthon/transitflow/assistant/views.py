import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from .chatbot import TransitChatbot

@login_required
@require_POST
def chatbot_message_api(request):
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
    except Exception:
        user_message = request.POST.get('message', '').strip()

    response_data = TransitChatbot.process_query(request.user, user_message)
    return JsonResponse(response_data)
