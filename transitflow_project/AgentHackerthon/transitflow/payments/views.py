import json
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.utils import timezone

from core.decorators import role_required
from logistics.models import Shipment
from .models import PaymentTransaction, PayHeroConfig, PaymentStatus, PaymentMethod
from .services import PayHeroService

# -----------------------------------------------------------------------------
# PAYMENTS INDEX (ACCESSIBLE TO ALL ROLES ACCORDING TO PRIVILEGES)
# -----------------------------------------------------------------------------
@login_required
def payments_index(request):
    config = PayHeroConfig.get_config()

    if request.user.is_manager or request.user.is_superuser:
        transactions = PaymentTransaction.objects.all().select_related('shipment', 'client')
        unpaid_shipments = Shipment.objects.filter(is_paid=False).select_related('client')
    else:
        transactions = PaymentTransaction.objects.filter(client=request.user).select_related('shipment')
        unpaid_shipments = Shipment.objects.filter(client=request.user, is_paid=False)

    total_collected = sum(t.amount for t in transactions if t.status == PaymentStatus.SUCCESS)
    pending_amount = sum(s.delivery_fee for s in unpaid_shipments)

    context = {
        'transactions': transactions,
        'unpaid_shipments': unpaid_shipments,
        'total_collected': total_collected,
        'pending_amount': pending_amount,
        'config': config,
    }
    return render(request, 'payments/payments_index.html', context)


# -----------------------------------------------------------------------------
# INITIATE PAYMENT (LIPWA LINK OR STK PUSH)
# -----------------------------------------------------------------------------
@login_required
def initiate_payment(request, tracking_number):
    shipment = get_object_or_404(Shipment, tracking_number=tracking_number)

    # Permission check: Only client who owns shipment or manager can pay
    if request.user.is_client and shipment.client_id != request.user.id:
        messages.error(request, "Access restricted: You cannot initiate payments for other clients' shipments.")
        return redirect('client_dashboard')

    if request.method == 'POST':
        method = request.POST.get('payment_method', 'LIPWA_LINK')
        phone = request.POST.get('phone_number', request.user.phone_number or '0712345678')
        amount = Decimal(request.POST.get('amount', shipment.delivery_fee))

        if method == 'LIPWA_LINK':
            result = PayHeroService.generate_lipwa_link(
                shipment=shipment,
                client=shipment.client,
                phone_number=phone,
                amount=amount,
                request=request
            )
            transaction = result['transaction']
            lipwa_url = result['lipwa_url']

            # If user wants direct redirect to Lipwa Link
            if 'open_link' in request.POST:
                return redirect(lipwa_url)

            context = {
                'shipment': shipment,
                'transaction': transaction,
                'lipwa_url': lipwa_url,
                'is_generated': True
            }
            return render(request, 'payments/lipwa_checkout.html', context)

        elif method == 'STK_PUSH':
            result = PayHeroService.initiate_stk_push(
                shipment=shipment,
                client=shipment.client,
                phone_number=phone,
                amount=amount,
                request=request
            )
            transaction = result['transaction']

            if result['success']:
                messages.success(request, f"🚀 {result['message']}")
                return redirect('payment_detail', reference=transaction.reference)
            else:
                messages.error(request, f"Payment initiation failed: {result['message']}")
                return redirect('payment_detail', reference=transaction.reference)

    context = {
        'shipment': shipment,
        'default_phone': request.user.phone_number or '0712345678',
        'config': PayHeroConfig.get_config(),
    }
    return render(request, 'payments/initiate_payment.html', context)


# -----------------------------------------------------------------------------
# TRANSACTION DETAIL
# -----------------------------------------------------------------------------
@login_required
def payment_detail(request, reference):
    transaction = get_object_or_404(
        PaymentTransaction.objects.select_related('shipment', 'client'),
        reference=reference
    )
    if request.user.is_client and transaction.client_id != request.user.id:
        messages.error(request, "Access restricted.")
        return redirect('payments_index')

    context = {
        'transaction': transaction,
        'config': PayHeroConfig.get_config(),
    }
    return render(request, 'payments/payment_detail.html', context)


# -----------------------------------------------------------------------------
# PAYHERO WEBHOOK / CALLBACK HANDLER (ASYNC RECONCILIATION)
# -----------------------------------------------------------------------------
@csrf_exempt
def payhero_callback(request):
    """
    Webhook endpoint: POST /payments/callback/
    Receives JSON notification from PayHero when customer completes transaction.
    """
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST.dict()

    external_ref = data.get('external_reference') or data.get('reference') or data.get('BillRefNumber')
    status_field = str(data.get('status', '')).lower()
    mpesa_receipt = data.get('MpesaReceiptNumber') or data.get('receipt_number') or f"PH{uuid.uuid4().hex[:8].upper()}"

    if not external_ref:
        return JsonResponse({"status": "ignored", "message": "No external_reference found"}, status=400)

    try:
        transaction = PaymentTransaction.objects.get(reference=external_ref)
        if 'success' in status_field or data.get('Success') is True or data.get('ResultCode') == 0:
            transaction.mark_as_paid(mpesa_receipt=mpesa_receipt, callback_data=data)
            return JsonResponse({"status": "success", "message": "Transaction marked as paid"})
        else:
            transaction.status = PaymentStatus.FAILED
            transaction.callback_payload = str(data)
            transaction.save()
            return JsonResponse({"status": "failed", "message": "Transaction marked as failed"})
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({"status": "not_found", "message": "Reference not found"}, status=404)


# -----------------------------------------------------------------------------
# SANDBOX SIMULATOR (TEST RECONCILIATION WITHOUT LIVE MPESA)
# -----------------------------------------------------------------------------
@login_required
def simulate_payment_success(request, reference):
    """
    Allows test evaluators to simulate instant payment completion
    and trigger shipment paid status immediately.
    """
    transaction = get_object_or_404(PaymentTransaction, reference=reference)
    
    # Generate mock M-Pesa receipt code
    mock_mpesa = f"QKB{uuid.uuid4().hex[:7].upper()}"
    mock_callback = {
        "status": "Success",
        "external_reference": transaction.reference,
        "amount": float(transaction.amount),
        "MpesaReceiptNumber": mock_mpesa,
        "phone": transaction.phone_number,
        "channel_id": PayHeroConfig.get_config().channel_id,
        "timestamp": timezone.now().isoformat()
    }
    
    transaction.mark_as_paid(mpesa_receipt=mock_mpesa, callback_data=mock_callback)
    messages.success(request, f"🎉 Simulated Sandbox Payment Confirmed! M-Pesa Receipt: {mock_mpesa}. Shipment is now officially marked as PAID.")
    return redirect('payment_detail', reference=reference)


# -----------------------------------------------------------------------------
# UPDATE PAYHERO CONFIGURATION (MANAGER ONLY)
# -----------------------------------------------------------------------------
@login_required
@role_required(['MANAGER'])
def configure_payhero(request):
    config = PayHeroConfig.get_config()
    if request.method == 'POST':
        config.api_username = request.POST.get('api_username', config.api_username)
        config.api_password = request.POST.get('api_password', config.api_password)
        config.channel_id = request.POST.get('channel_id', config.channel_id)
        config.lipwa_link_slug = request.POST.get('lipwa_link_slug', config.lipwa_link_slug)
        config.environment = request.POST.get('environment', 'SANDBOX')
        config.callback_url = request.POST.get('callback_url', config.callback_url)
        config.save()
        messages.success(request, "PayHero API settings updated successfully!")
        return redirect('configure_payhero')

    return render(request, 'payments/configure_payhero.html', {'config': config})


# -----------------------------------------------------------------------------
# HOW-TO INTEGRATION GUIDE PAGE (FOR THE USER)
# -----------------------------------------------------------------------------
def payhero_howto(request):
    """
    Comprehensive interactive guide page explaining step-by-step
    how to integrate PayHero's Lipwa Link API and STK Push into production.
    """
    config = PayHeroConfig.get_config()
    return render(request, 'payments/payhero_howto.html', {'config': config})
