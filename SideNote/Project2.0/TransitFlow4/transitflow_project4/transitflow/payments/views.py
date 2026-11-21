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
from .models import PaymentTransaction, PayHeroConfig, PaymentStatus, PaymentMethod, ClientCreditLog, CreditActionType
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
        credit_logs = ClientCreditLog.objects.all().select_related('client', 'transaction')[:20]
    else:
        transactions = PaymentTransaction.objects.filter(client=request.user).select_related('shipment')
        unpaid_shipments = Shipment.objects.filter(client=request.user, is_paid=False)
        credit_logs = ClientCreditLog.objects.filter(client=request.user).select_related('transaction')[:10]

    total_collected = sum(t.amount for t in transactions if t.status == PaymentStatus.SUCCESS)
    pending_amount = sum(s.delivery_fee for s in unpaid_shipments)

    context = {
        'transactions': transactions,
        'unpaid_shipments': unpaid_shipments,
        'credit_logs': credit_logs,
        'total_collected': total_collected,
        'pending_amount': pending_amount,
        'config': config,
    }
    return render(request, 'payments/payments_index.html', context)


# -----------------------------------------------------------------------------
# INITIATE PAYMENT (LIPWA LINK, STK PUSH, OR CREDIT BALANCE)
# -----------------------------------------------------------------------------
@login_required
def initiate_payment(request, tracking_number):
    shipment = get_object_or_404(Shipment, tracking_number=tracking_number)

    # Permission check: Only client who owns shipment or manager can pay
    if request.user.is_client and shipment.client_id != request.user.id:
        messages.error(request, "Access restricted: You cannot initiate payments for other clients' shipments.")
        return redirect('client_dashboard')

    client = shipment.client
    user_credit = client.credit_balance or Decimal('0.00')

    if request.method == 'POST':
        method = request.POST.get('payment_method', 'LIPWA_LINK')
        phone = request.POST.get('phone_number', request.user.phone_number or '0712345678')
        amount = Decimal(request.POST.get('amount', shipment.delivery_fee))

        # OPTION 1: PAY WITH CREDIT BALANCE
        if method == 'CREDIT_BALANCE':
            if user_credit < amount:
                messages.error(
                    request,
                    f"❌ Insufficient Credit Balance: You have KES {user_credit:,.2f}, but the delivery fee is KES {amount:,.2f}."
                )
                return redirect('initiate_payment', tracking_number=tracking_number)

            # Deduct credit and mark paid
            client.credit_balance = user_credit - amount
            client.save(update_fields=['credit_balance'])

            tx_ref = f"CRD-TF-{uuid.uuid4().hex[:8].upper()}"
            transaction = PaymentTransaction.objects.create(
                reference=tx_ref,
                shipment=shipment,
                client=client,
                amount=amount,
                currency='KES',
                phone_number=phone,
                payment_method=PaymentMethod.CREDIT_BALANCE,
                status=PaymentStatus.SUCCESS,
                mpesa_receipt=f"CREDIT-{uuid.uuid4().hex[:6].upper()}"
            )
            shipment.is_paid = True
            shipment.save(update_fields=['is_paid'])

            ClientCreditLog.objects.create(
                client=client,
                transaction=transaction,
                amount=amount,
                balance_after=client.credit_balance,
                action_type=CreditActionType.DEBIT,
                reason=f"Payment for shipment #{shipment.tracking_number} using credit balance"
            )

            messages.success(
                request,
                f"✅ Shipment fee of KES {amount:,.2f} settled using your credit balance! Remaining balance: KES {client.credit_balance:,.2f}."
            )
            return redirect('payment_detail', reference=transaction.reference)

        # OPTION 2: PAYHERO LIPWA LINK
        elif method == 'LIPWA_LINK':
            result = PayHeroService.generate_lipwa_link(
                shipment=shipment,
                client=client,
                phone_number=phone,
                amount=amount,
                request=request
            )
            transaction = result['transaction']
            lipwa_url = result['lipwa_url']

            if 'open_link' in request.POST:
                return redirect(lipwa_url)

            context = {
                'shipment': shipment,
                'transaction': transaction,
                'lipwa_url': lipwa_url,
                'is_generated': True
            }
            return render(request, 'payments/lipwa_checkout.html', context)

        # OPTION 3: PAYHERO M-PESA STK PUSH
        elif method == 'STK_PUSH':
            result = PayHeroService.initiate_stk_push(
                shipment=shipment,
                client=client,
                phone_number=phone,
                amount=amount,
                request=request
            )
            transaction = result['transaction']

            if result['success']:
                messages.success(request, f"🚀 {result['message']}")
                return redirect('payment_detail', reference=transaction.reference)
            else:
                # Failure encountered: Transaction is already marked failed and credited
                messages.error(
                    request,
                    f"❌ Payment Failed: {result['message']}. As per TransitFlow policy, your account has been credited KES {transaction.credited_amount:,.2f} compensatory credit! Current credit balance: KES {client.credit_balance:,.2f}."
                )
                return redirect('payment_detail', reference=transaction.reference)

    context = {
        'shipment': shipment,
        'client_credit': user_credit,
        'has_sufficient_credit': (user_credit >= shipment.delivery_fee),
        'default_phone': request.user.phone_number or '0712345678',
        'config': PayHeroConfig.get_config(),
    }
    return render(request, 'payments/initiate_payment.html', context)


# -----------------------------------------------------------------------------
# DIRECT ONE-CLICK PAY WITH CREDIT
# -----------------------------------------------------------------------------
@login_required
def pay_with_credit(request, tracking_number):
    shipment = get_object_or_404(Shipment, tracking_number=tracking_number)

    if request.user.is_client and shipment.client_id != request.user.id:
        messages.error(request, "Access restricted.")
        return redirect('client_dashboard')

    if shipment.is_paid:
        messages.info(request, f"Shipment #{shipment.tracking_number} is already paid.")
        return redirect('shipment_detail', tracking_number=tracking_number)

    client = shipment.client
    fee = shipment.delivery_fee
    user_credit = client.credit_balance or Decimal('0.00')

    if user_credit < fee:
        messages.error(
            request,
            f"❌ Cannot pay with credit: Required KES {fee:,.2f}, but your credit balance is KES {user_credit:,.2f}."
        )
        return redirect('initiate_payment', tracking_number=tracking_number)

    # Debit credit
    client.credit_balance = user_credit - fee
    client.save(update_fields=['credit_balance'])

    tx_ref = f"CRD-TF-{uuid.uuid4().hex[:8].upper()}"
    transaction = PaymentTransaction.objects.create(
        reference=tx_ref,
        shipment=shipment,
        client=client,
        amount=fee,
        currency='KES',
        phone_number=client.phone_number or '0700000000',
        payment_method=PaymentMethod.CREDIT_BALANCE,
        status=PaymentStatus.SUCCESS,
        mpesa_receipt=f"CRD-{uuid.uuid4().hex[:6].upper()}"
    )
    shipment.is_paid = True
    shipment.save(update_fields=['is_paid'])

    ClientCreditLog.objects.create(
        client=client,
        transaction=transaction,
        amount=fee,
        balance_after=client.credit_balance,
        action_type=CreditActionType.DEBIT,
        reason=f"Instant credit balance settlement for shipment #{shipment.tracking_number}"
    )

    messages.success(
        request,
        f"🎉 Shipment #{shipment.tracking_number} settled instantly using credit! Remaining credit balance: KES {client.credit_balance:,.2f}."
    )
    return redirect('payment_detail', reference=transaction.reference)


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
        'client_credit': transaction.client.credit_balance,
        'config': PayHeroConfig.get_config(),
    }
    return render(request, 'payments/payment_detail.html', context)


# -----------------------------------------------------------------------------
# PAYHERO WEBHOOK / CALLBACK HANDLER (ASYNC RECONCILIATION & AUTO-CREDIT ON FAIL)
# -----------------------------------------------------------------------------
@csrf_exempt
def payhero_callback(request):
    """
    Webhook endpoint: POST /payments/callback/
    Receives JSON notification from PayHero when customer completes transaction.
    If transaction fails, client is automatically credited compensatory funds.
    """
    if request.method != 'POST':
        return HttpResponse("Method Not Allowed", status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        data = request.POST.dict()

    payload = data.get('response') if isinstance(data.get('response'), dict) else data

    external_ref = (
        payload.get('external_reference') or
        payload.get('ExternalReference') or
        payload.get('reference') or
        payload.get('BillRefNumber') or
        data.get('external_reference') or
        data.get('ExternalReference') or
        data.get('reference')
    )
    status_field = str(payload.get('status') or payload.get('Status') or data.get('status') or data.get('Status') or '').lower()
    
    is_success = (
        'success' in status_field or
        payload.get('status') is True or
        payload.get('Success') is True or
        payload.get('ResultCode') == 0 or
        data.get('Success') is True or
        data.get('status') is True
    )

    mpesa_receipt = (
        payload.get('MpesaReceiptNumber') or
        payload.get('mpesa_receipt') or
        payload.get('receipt_number') or
        data.get('MpesaReceiptNumber') or
        f"PH{uuid.uuid4().hex[:8].upper()}"
    )

    if not external_ref:
        return JsonResponse({"status": "ignored", "message": "No external_reference found"}, status=400)

    try:
        transaction = PaymentTransaction.objects.get(reference=external_ref)
        if is_success:
            transaction.mark_as_paid(mpesa_receipt=mpesa_receipt, callback_data=data)
            return JsonResponse({"status": "success", "message": "Transaction marked as paid"})
        else:
            fail_reason = (
                payload.get('ResultDesc') or
                payload.get('errorMessage') or
                payload.get('message') or
                data.get('ResultDesc') or
                data.get('message') or
                "M-Pesa payment rejected or cancelled by customer"
            )
            transaction.mark_as_failed(reason=fail_reason, callback_data=data)
            return JsonResponse({
                "status": "failed",
                "credited": True,
                "credited_amount": float(transaction.credited_amount),
                "client_balance": float(transaction.client.credit_balance),
                "message": f"Transaction failed. Client credited KES {transaction.credited_amount:,.2f}"
            })
    except PaymentTransaction.DoesNotExist:
        return JsonResponse({"status": "not_found", "message": "Reference not found"}, status=404)


# -----------------------------------------------------------------------------
# LIPWA LINK REDIRECT LANDINGS (SUCCESS & FAILED)
# -----------------------------------------------------------------------------
@login_required
def payment_success_landing(request):
    ref = request.GET.get('ref')
    if ref:
        try:
            transaction = PaymentTransaction.objects.get(reference=ref)
            if transaction.status != PaymentStatus.SUCCESS:
                mock_mpesa = f"LPW{uuid.uuid4().hex[:7].upper()}"
                transaction.mark_as_paid(mpesa_receipt=mock_mpesa)
            messages.success(request, f"🎉 Lipwa Link Payment Confirmed! Shipment #{transaction.shipment.tracking_number} is PAID.")
            return redirect('payment_detail', reference=transaction.reference)
        except PaymentTransaction.DoesNotExist:
            pass
    messages.info(request, "Payment completed.")
    return redirect('payments_index')


@login_required
def payment_failed_landing(request):
    ref = request.GET.get('ref')
    if ref:
        try:
            transaction = PaymentTransaction.objects.get(reference=ref)
            if transaction.status != PaymentStatus.FAILED:
                transaction.mark_as_failed(reason="User cancelled or PayHero checkout session expired")
            messages.error(
                request,
                f"❌ Payment Failed: The checkout session was cancelled or failed. As per TransitFlow policy, your account has been credited KES {transaction.credited_amount:,.2f} compensatory credit! Current balance: KES {transaction.client.credit_balance:,.2f}."
            )
            return redirect('payment_detail', reference=transaction.reference)
        except PaymentTransaction.DoesNotExist:
            pass
    messages.error(request, "Payment was not completed.")
    return redirect('payments_index')


# -----------------------------------------------------------------------------
# SANDBOX SIMULATORS (TEST SUCCESS & TEST FAILURE WITH AUTO-CREDITING)
# -----------------------------------------------------------------------------
@login_required
def simulate_payment_success(request, reference):
    """
    Simulates instant payment completion and marks shipment paid.
    """
    transaction = get_object_or_404(PaymentTransaction, reference=reference)
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


@login_required
def simulate_payment_failure(request, reference):
    """
    Simulates instant payment failure (e.g. M-Pesa timeout, cancelled prompt, insufficient funds).
    Verifies that the client is automatically credited compensatory funds and error message is displayed.
    """
    transaction = get_object_or_404(PaymentTransaction, reference=reference)
    reason = "Simulated Failure: Customer cancelled M-Pesa prompt or insufficient mobile funds"
    
    transaction.mark_as_failed(reason=reason, callback_data={"simulated_error": True, "reason": reason})
    messages.error(
        request,
        f"⚠️ Transaction Failed! [Reason: {reason}]. As per TransitFlow policy, client {transaction.client.username} has been credited KES {transaction.credited_amount:,.2f} compensatory credit! New balance: KES {transaction.client.credit_balance:,.2f}."
    )
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
