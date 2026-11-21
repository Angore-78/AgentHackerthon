import json
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from payments.models import PaymentTransaction
from .chatbot import TransitChatbot

@login_required
@require_POST
def chatbot_message_api(request):
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
    except Exception:
        user_message = request.POST.get('message', '').strip()

    response_data = TransitChatbot.process_query(request.user, user_message, request=request)
    return JsonResponse(response_data)

@login_required
def check_payment_status_api(request, reference):
    """
    Polling endpoint for Voice AI Agent to announce payment confirmation in real-time.
    """
    try:
        tx = PaymentTransaction.objects.select_related('shipment').get(reference=reference)
        if request.user.is_client and tx.client_id != request.user.id:
            return JsonResponse({'status': 'unauthorized'}, status=403)
        return JsonResponse({
            'reference': tx.reference,
            'status': tx.status,
            'is_paid': tx.shipment.is_paid,
            'mpesa_receipt': tx.mpesa_receipt or '',
            'amount': float(tx.amount),
            'tracking_number': tx.shipment.tracking_number,
        })
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({'status': 'not_found'}, status=404)
