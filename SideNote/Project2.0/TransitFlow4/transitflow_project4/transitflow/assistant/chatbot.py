import re
from decimal import Decimal
from django.utils import timezone
from logistics.models import Shipment, ShipmentItem, Product, ProductCategory, ShipmentStatus, TransitEvent
from payments.models import PaymentTransaction, PaymentStatus, ClientCreditLog
from payments.services import PayHeroService

class TransitChatbot:
    """
    Privilege-aware AI Assistant for TransitFlow Logistics.
    Enforces strict access control depending on user role:
    - MANAGER: Full operational, financial, and transit fleet oversight.
    - DRIVER: Assigned transit runs, cargo specifications, cold-chain thresholds, route milestones.
    - PORTER: Depot handling, loading/offloading checklists, cold-room storage, cargo inspection.
    - CLIENT: Own shipments, tracking timeline, cargo care, invoices & PayHero payment access.
    """

    @classmethod
    def get_suggested_prompts(cls, user):
        role = getattr(user, 'role', 'CLIENT')
        if user.is_manager or user.is_superuser:
            return [
                "📊 Overall transit overview",
                "❄️ Perishable goods status & alerts",
                "💳 Financial & payment summary",
                "🏷️ Set freight rates for goods",
                "💰 Client credit balance overview",
                "🚚 Active drivers on route",
                "⚠️ Any delayed shipments?"
            ]
        elif role == 'DRIVER':
            return [
                "🚚 What cargo am I transporting today?",
                "❄️ Are there perishable items needing cold storage?",
                "📍 Destination & route checkpoints",
                "📝 How to log a checkpoint update?"
            ]
        elif role == 'PORTER':
            return [
                "📦 Goods awaiting loading / unloading",
                "❄️ Perishable items requiring cold room",
                "🛡️ Fragile & hazardous cargo handling notes",
                "🌡️ How to log a temperature check?"
            ]
        else: # CLIENT
            return [
                "💰 What is my credit balance?",
                "💳 Pay pending shipments via Lipwa Link",
                "📦 Where are my shipments right now?",
                "❄️ How are my perishable goods being preserved?",
                "🔗 How to pay with PayHero Lipwa Link?"
            ]

    @classmethod
    def clean_for_speech(cls, text):
        if not text:
            return ""
        # Remove markdown links, keep label
        clean = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Convert transit symbols
        clean = clean.replace('➔', ' to ').replace('•', ', ').replace('🚨', 'Alert: ')
        clean = clean.replace('❄️', 'Cold-chain: ').replace('📦', 'Package: ').replace('💳', 'Payment: ')
        clean = clean.replace('⚠️', 'Warning: ').replace('✅', 'Confirmed: ')
        clean = clean.replace('👉', '').replace('💡', '').replace('🗣️', '')
        clean = clean.replace('KES', 'Kenyan Shillings')
        clean = re.sub(r'[*#_`~]', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    @classmethod
    def process_query(cls, user, query_text, request=None):
        query = (query_text or "").strip().lower()
        role = getattr(user, 'role', 'CLIENT')
        
        # Check for empty query
        if not query:
            return {
                "reply": "Hello! I am your TransitFlow Assistant. Ask me anything about goods in transit, handling guidelines, shipment status, or payments based on your clearance.",
                "spoken_text": "Hello! I am your TransitFlow Voice Assistant. Ask me about your shipments, cargo temperature, or say 'pay my balance' to make an M-Pesa payment.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # If it's an explicit payment action, let the role-specific payment handlers process it
        is_payment_intent = any(
            w in query for w in [
                'pay', 'lipwa', 'checkout', 'settle', 'stk', 'cost', 'fee',
                'invoice', 'balance', 'owe', 'money', 'mpesa', 'yes', 'confirm',
                'proceed', 'send prompt', 'trigger prompt', 'trigger payment',
                'credit', 'wallet', 'credit balance', 'my credit'
            ]
        )

        # Check for explicit tracking number format like TF-XXXX or TF-XXXX-XXXX
        trk_match = re.search(r'\b(tf-[a-z0-9\-]+)\b', query, re.I)
        if trk_match and not is_payment_intent:
            tracking_num = trk_match.group(1).upper()
            res = cls._handle_tracking_query(user, tracking_num, request=request)
            if 'spoken_text' not in res:
                res['spoken_text'] = cls.clean_for_speech(res.get('reply', ''))
            return res

        # Route by Role-specific logic
        if user.is_manager or user.is_superuser:
            res = cls._handle_manager_query(user, query, request=request)
        elif role == 'DRIVER':
            res = cls._handle_driver_query(user, query)
        elif role == 'PORTER':
            res = cls._handle_porter_query(user, query)
        else:
            res = cls._handle_client_query(user, query, request=request)

        if 'spoken_text' not in res:
            res['spoken_text'] = cls.clean_for_speech(res.get('reply', ''))

        return res

    # -------------------------------------------------------------
    # TRACKING QUERY HANDLER WITH ACCESS CONTROL
    # -------------------------------------------------------------
    @classmethod
    def _handle_tracking_query(cls, user, tracking_num, request=None):
        try:
            shipment = Shipment.objects.prefetch_related('items__product', 'transit_events').get(tracking_number__iexact=tracking_num)
        except Shipment.DoesNotExist:
            return {
                "reply": f"🔍 Shipment with tracking code **{tracking_num}** was not found in the transit registry. Please double-check the tracking ID.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        role = getattr(user, 'role', 'CLIENT')

        # Access check: Client can only view their own shipment
        if role == 'CLIENT' and shipment.client_id != user.id:
            return {
                "reply": f"🔒 **Access Restricted:** You do not have permission to view shipment **{tracking_num}**. Clients can only view shipments booked under their own account.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }
        
        # Driver check: Only assigned driver or manager
        if role == 'DRIVER' and shipment.assigned_driver_id != user.id and not (user.is_manager or user.is_superuser):
            return {
                "reply": f"🔒 **Access Restricted:** Shipment **{tracking_num}** is not assigned to your vehicle manifest.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # Build detailed cargo profile
        items_summary = []
        has_perishable = False
        for item in shipment.items.all():
            prod = item.product
            if prod.category == ProductCategory.PERISHABLE:
                has_perishable = True
                temp_range = f"{prod.min_temp_celsius}°C to {prod.max_temp_celsius}°C" if prod.min_temp_celsius is not None else "Refrigerated"
                items_summary.append(f"• ❄️ **{item.quantity}x {prod.name}** [PERISHABLE: Keep at {temp_range}, Risk: {prod.get_spoilage_risk_display()}]")
            else:
                fragile_txt = " (Fragile)" if prod.is_fragile else ""
                items_summary.append(f"• 📦 **{item.quantity}x {prod.name}** [NON-PERISHABLE{fragile_txt}]")

        last_event = shipment.transit_events.order_by('-timestamp').first()
        last_loc_txt = f"{last_event.location} ({last_event.get_event_type_display()})" if last_event else shipment.current_location

        # Payment status with interactive Lipwa Link if unpaid
        prompts = cls.get_suggested_prompts(user)
        if not shipment.is_paid:
            if user.is_manager or user.is_superuser or shipment.client_id == user.id:
                client_phone = getattr(user, 'phone_number', None) or getattr(shipment.client, 'phone_number', None) or '0712345678'
                lipwa_data = PayHeroService.generate_lipwa_link(
                    shipment=shipment,
                    client=shipment.client,
                    phone_number=client_phone,
                    amount=shipment.delivery_fee,
                    request=request
                )
                payment_txt = f"⚠️ **Unpaid (KES {shipment.delivery_fee:,.2f})** &bull; [💳 Pay via PayHero Lipwa Link]({lipwa_data['lipwa_url']}) &bull; [Portal Checkout](/payments/initiate/{shipment.tracking_number}/)"
                prompts = [f"💳 Pay for {shipment.tracking_number} via Lipwa Link"] + [p for p in prompts if p != f"💳 Pay for {shipment.tracking_number} via Lipwa Link"]
            else:
                payment_txt = f"⚠️ Unpaid (KES {shipment.delivery_fee:,.2f})"
        else:
            payment_txt = "✅ **Paid** (M-Pesa Verified)"

        reply = f"""### 🚚 Shipment Record: `{shipment.tracking_number}`
- **Current Status:** `{shipment.get_status_display()}`
- **Route:** {shipment.origin} ➔ {shipment.destination}
- **Current Location:** {last_loc_txt}
- **Cargo Classification:** {'❄️ Perishable Goods Detected' if has_perishable else '📦 Standard Non-Perishable Goods'}
- **Payment:** {payment_txt}

#### 📋 Products on Transit:
{chr(10).join(items_summary) if items_summary else "No individual items registered."}

{f"**Driver Assigned:** {shipment.assigned_driver.get_full_name() or shipment.assigned_driver.username} ({shipment.vehicle_plate or 'No plate assigned'})" if shipment.assigned_driver else "**Driver Assigned:** Awaiting dispatch assignment"}
"""
        return {
            "reply": reply,
            "suggested_prompts": prompts
        }

    # -------------------------------------------------------------
    # CLIENT QUERIES (STRICTLY SCOPED TO CLIENT'S OWN SHIPMENTS)
    # -------------------------------------------------------------
    @classmethod
    def _handle_client_query(cls, user, query, request=None):
        client_shipments = Shipment.objects.filter(client=user).prefetch_related('items__product')
        
        # Question about other users / system-wide data -> Deny
        if any(w in query for w in ['all shipments', 'system revenue', 'other clients', 'all drivers', 'database']):
            return {
                "reply": "🔒 **Clearance Notice:** As a Client, your assistant view is strictly scoped to goods, shipments, and billing transactions registered under your account.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # 1. Client Credit Balance Query
        is_credit_query = any(
            phrase in query for phrase in [
                'credit balance', 'my credit', 'credit wallet', 'how much credit',
                'available credit', 'my wallet', 'credit account', 'compensatory',
                'what is my balance', 'account balance', 'how much do i have',
                'wallet balance', 'my account balance'
            ]
        )
        if is_credit_query:
            credit_bal = user.credit_balance or Decimal('0.00')
            credit_logs = ClientCreditLog.objects.filter(client=user).order_by('-created_at')[:3]
            log_lines = []
            for log in credit_logs:
                action_label = "Credited +" if log.action_type == 'CREDIT' else "Debited -"
                log_lines.append(f"• {log.created_at.strftime('%b %d %H:%M')}: {action_label}KES {log.amount:,.2f} — {log.reason[:60]}{'...' if len(log.reason) > 60 else ''}")

            if credit_bal > 0:
                reply = f"""### 💰 Your TransitFlow Credit Balance

**Available Credit: KES {credit_bal:,.2f}**

Your credit wallet holds funds compensated for failed or cancelled payments. You can use this credit to:
- Settle any unpaid shipment delivery fee **instantly** (no M-Pesa PIN required)
- Select **"Pay with Credit Balance"** on any pending shipment checkout

#### Recent Credit Activity:
{chr(10).join(log_lines) if log_lines else "No previous credit activity."}

👉 [View Payments & Settle with Credit Balance](/payments/)"""
                spoken = f"Your available TransitFlow credit balance is {int(credit_bal)} Kenyan Shillings. You can use this to pay your shipment fees instantly without M-Pesa. Would you like me to apply your credit to a pending shipment? Just say 'Pay with credit'."
            else:
                reply = """### 💰 Your TransitFlow Credit Balance

**Available Credit: KES 0.00**

You currently have no pending compensatory credit. Credits are automatically added to your wallet whenever:
- An M-Pesa payment prompt times out or is cancelled by M-Pesa
- A PayHero gateway transaction fails for any technical reason
- A Lipwa Link checkout session expires without completion

This **Zero-Loss Guarantee** ensures you are never financially disadvantaged by payment gateway failures!"""
                spoken = "Your TransitFlow credit balance is currently zero. If a future payment fails, the full amount will be automatically credited to your wallet here. You can then use it to pay shipment fees instantly."

            return {
                "reply": reply,
                "spoken_text": spoken,
                "action": "credit_balance_info",
                "credit_balance": float(credit_bal),
                "suggested_prompts": [
                    "💳 Pay my pending shipment",
                    "🗣️ Pay with my credit balance",
                    "📦 Track my shipments"
                ]
            }

        # 2. Payment Failure Acknowledgement Handler — spoken aloud for Voice AI accessibility
        # Triggers when user says "my payment failed", "transaction failed", etc.
        is_failure_query = any(
            phrase in query for phrase in [
                'payment failed', 'transaction failed', 'failed payment', 'mpesa failed',
                'my payment did not go', 'payment declined', 'failed transaction',
                'why did my payment fail', 'payment not successful', 'stk failed'
            ]
        )
        if is_failure_query:
            latest_failed = PaymentTransaction.objects.filter(
                client=user, status=PaymentStatus.FAILED
            ).order_by('-created_at').first()
            if latest_failed:
                credit_bal = user.credit_balance or Decimal('0.00')
                reason = latest_failed.failure_reason or "M-Pesa gateway timeout or cancellation"
                credited = latest_failed.is_credited
                credited_amt = latest_failed.credited_amount or Decimal('0.00')

                reply = f"""### ⚠️ Payment Failure — Zero-Loss Guarantee Activated

**Transaction:** `{latest_failed.reference}`
**Amount:** KES {latest_failed.amount:,.2f}
**Failure Reason:** {reason}

"""
                if credited:
                    reply += f"""#### ✅ Compensatory Credit Applied Automatically:
KES **{credited_amt:,.2f}** has been credited to your TransitFlow wallet immediately upon failure.
**Current Credit Balance: KES {credit_bal:,.2f}**

You can now:
- Settle shipment **{latest_failed.shipment.tracking_number}** using your credit balance (no M-Pesa required)
- Or retry the M-Pesa payment from the [Payments Portal](/payments/initiate/{latest_failed.shipment.tracking_number}/)"""
                    spoken = f"Your payment failed. Reason: {reason}. Do not worry — as per TransitFlow's Zero-Loss Guarantee, {int(credited_amt)} Kenyan Shillings have been automatically credited to your account wallet. Your current credit balance is {int(credit_bal)} shillings. You can use this credit to pay shipment {latest_failed.shipment.tracking_number} instantly without M-Pesa. Just say 'Pay with credit'."
                else:
                    reply += "The system is processing your compensatory credit. Please check your credit balance shortly."
                    spoken = f"Your payment for {int(latest_failed.amount)} Kenyan Shillings failed. Reason: {reason}. Your account credit is being processed."

                return {
                    "reply": reply,
                    "spoken_text": spoken,
                    "action": "payment_failed_info",
                    "credit_balance": float(credit_bal),
                    "reference": latest_failed.reference,
                    "suggested_prompts": [
                        "🗣️ Pay with my credit balance",
                        f"💳 Retry payment for {latest_failed.shipment.tracking_number}",
                        "💰 What is my credit balance?"
                    ]
                }

        # 3. Voice Payment Status Inquiry
        if any(phrase in query for phrase in ['status of payment', 'payment status', 'did my payment go through', 'did it go through', 'is it paid', 'check payment', 'payment confirmed']):
            latest_tx = PaymentTransaction.objects.filter(client=user).order_by('-created_at').first()
            if latest_tx:
                if latest_tx.status == PaymentStatus.SUCCESS or latest_tx.shipment.is_paid:
                    rep = f"✅ Payment for shipment **{latest_tx.shipment.tracking_number}** (KES {latest_tx.amount:,.2f}) was **CONFIRMED**! M-Pesa Receipt: `{latest_tx.mpesa_receipt or 'CONFIRMED'}`."
                    spk = f"Good news! Your payment of {int(latest_tx.amount)} Kenyan Shillings for shipment {latest_tx.shipment.tracking_number} has been confirmed. The shipment is officially marked as paid."
                    return {
                        "reply": rep,
                        "spoken_text": spk,
                        "action": "payment_confirmed",
                        "status": "SUCCESS",
                        "reference": latest_tx.reference,
                        "suggested_prompts": cls.get_suggested_prompts(user)
                    }
                elif latest_tx.status == PaymentStatus.PENDING:
                    rep = f"⏳ Payment of **KES {latest_tx.amount:,.2f}** for `{latest_tx.shipment.tracking_number}` is still **PENDING**. Please authorize the prompt on your phone."
                    spk = f"Your payment of {int(latest_tx.amount)} Kenyan Shillings for shipment {latest_tx.shipment.tracking_number} is currently pending M-Pesa authorization. Please enter your PIN on your phone."
                    return {
                        "reply": rep,
                        "spoken_text": spk,
                        "action": "payment_pending",
                        "status": "PENDING",
                        "reference": latest_tx.reference,
                        "suggested_prompts": ["🔍 Check payment status again", "📦 Track shipment"]
                    }

        # 3. Voice Payment Status Inquiry
        if any(phrase in query for phrase in ['status of payment', 'payment status', 'did my payment go through', 'did it go through', 'is it paid', 'check payment', 'payment confirmed']):
            latest_tx = PaymentTransaction.objects.filter(client=user).order_by('-created_at').first()
            if latest_tx:
                if latest_tx.status == PaymentStatus.SUCCESS or latest_tx.shipment.is_paid:
                    rep = f"✅ Payment for shipment **{latest_tx.shipment.tracking_number}** (KES {latest_tx.amount:,.2f}) was **CONFIRMED**! M-Pesa Receipt: `{latest_tx.mpesa_receipt or 'CONFIRMED'}`."
                    spk = f"Good news! Your payment of {int(latest_tx.amount)} Kenyan Shillings for shipment {latest_tx.shipment.tracking_number} has been confirmed. The shipment is officially marked as paid."
                    return {
                        "reply": rep,
                        "spoken_text": spk,
                        "action": "payment_confirmed",
                        "status": "SUCCESS",
                        "reference": latest_tx.reference,
                        "suggested_prompts": cls.get_suggested_prompts(user)
                    }
                elif latest_tx.status == PaymentStatus.FAILED:
                    credit_bal = user.credit_balance or Decimal('0.00')
                    reason = latest_tx.failure_reason or "Payment gateway error or cancellation"
                    rep = f"⚠️ Your last payment of **KES {latest_tx.amount:,.2f}** for `{latest_tx.shipment.tracking_number}` **FAILED**.\n\n**Reason:** {reason}\n\n✅ **KES {latest_tx.credited_amount:,.2f} has been automatically credited** to your TransitFlow wallet. Your current credit balance is **KES {credit_bal:,.2f}**."
                    spk = f"Alert: Your last payment of {int(latest_tx.amount)} Kenyan Shillings failed. Reason: {reason}. Do not worry — {int(latest_tx.credited_amount)} Kenyan Shillings have been automatically credited to your account. Your credit balance is now {int(credit_bal)} Kenyan Shillings. You can use this to pay instantly without M-Pesa."
                    return {
                        "reply": rep,
                        "spoken_text": spk,
                        "action": "payment_failed",
                        "status": "FAILED",
                        "credit_balance": float(credit_bal),
                        "reference": latest_tx.reference,
                        "suggested_prompts": [
                            "🗣️ Pay with my credit balance",
                            f"💳 Retry payment for {latest_tx.shipment.tracking_number}",
                            "💰 What is my credit balance?"
                        ]
                    }
                elif latest_tx.status == PaymentStatus.PENDING:
                    rep = f"⏳ Payment of **KES {latest_tx.amount:,.2f}** for `{latest_tx.shipment.tracking_number}` is still **PENDING**. Please authorize the prompt on your phone."
                    spk = f"Your payment of {int(latest_tx.amount)} Kenyan Shillings for shipment {latest_tx.shipment.tracking_number} is currently pending M-Pesa authorization. Please enter your PIN on your phone."
                    return {
                        "reply": rep,
                        "spoken_text": spk,
                        "action": "payment_pending",
                        "status": "PENDING",
                        "reference": latest_tx.reference,
                        "suggested_prompts": ["🔍 Check payment status again", "📦 Track shipment"]
                    }

        # 4. Voice Credit Payment Trigger — "pay with credit", "use my credit"
        is_credit_payment = any(
            phrase in query for phrase in [
                'pay with credit', 'use my credit', 'pay using credit',
                'use credit balance', 'settle with credit', 'pay from wallet',
                'use wallet', 'pay with wallet'
            ]
        )
        if is_credit_payment:
            credit_bal = user.credit_balance or Decimal('0.00')
            unpaid = client_shipments.filter(is_paid=False)
            trk_match = re.search(r'\b(tf-[a-z0-9\-]+)\b', query, re.I)
            target = None
            if trk_match:
                target = unpaid.filter(tracking_number__iexact=trk_match.group(1).upper()).first()
            if not target:
                target = unpaid.first()

            if not target:
                return {
                    "reply": "✅ **All Clear!** You have no outstanding unpaid shipments. All your freight is fully settled.",
                    "spoken_text": "All clear! You have no outstanding shipment fees to pay.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

            if credit_bal < target.delivery_fee:
                return {
                    "reply": f"❌ **Insufficient Credit Balance:** Shipment **{target.tracking_number}** requires KES {target.delivery_fee:,.2f} but your credit balance is only KES {credit_bal:,.2f}. Please use M-Pesa or top up your credit.\n\n👉 [Pay via Lipwa Link or STK Push](/payments/initiate/{target.tracking_number}/)",
                    "spoken_text": f"You do not have enough credit balance. The shipment requires {int(target.delivery_fee)} shillings but you only have {int(credit_bal)} in credit. Please use M-Pesa instead.",
                    "suggested_prompts": ["💳 Pay via Lipwa Link", "🗣️ Trigger M-Pesa prompt"]
                }

            return {
                "reply": f"""### 💰 Credit Payment Available
You have **KES {credit_bal:,.2f}** in credit — enough to settle shipment **{target.tracking_number}** (KES {target.delivery_fee:,.2f}).

👉 **[Click here to pay with Credit Balance instantly](/payments/pay-credit/{target.tracking_number}/)**

This will deduct KES {target.delivery_fee:,.2f} from your wallet and mark the shipment as fully paid — no M-Pesa PIN needed!""",
                "spoken_text": f"You have {int(credit_bal)} Kenyan Shillings in credit. That is enough to pay for shipment {target.tracking_number} which costs {int(target.delivery_fee)} shillings. Click the link on screen or navigate to the payment portal to settle instantly using your credit balance.",
                "action": "credit_payment_available",
                "tracking_number": target.tracking_number,
                "credit_balance": float(credit_bal),
                "suggested_prompts": [
                    f"💰 Confirm credit payment for {target.tracking_number}",
                    "📦 Track my shipments"
                ]
            }

        # 5. Voice Payment Affirmation / Direct STK Trigger (Hands-Free for Blind/Paralyzed Users)
        # Handles user saying: "Yes", "Confirm", "Send prompt", "Trigger payment", "Pay now", "Pay my shipment"
        is_voice_confirm = any(
            phrase in query for phrase in [
                'yes', 'confirm', 'proceed', 'send prompt', 'trigger prompt',
                'trigger payment', 'trigger stk', 'pay now', 'pay with mpesa',
                'send mpesa', 'authorize payment', 'please pay', 'pay my shipment',
                'pay this', 'pay for my shipment'
            ]
        )
        if is_voice_confirm:
            unpaid = client_shipments.filter(is_paid=False)
            trk_match = re.search(r'\b(tf-[a-z0-9\-]+)\b', query, re.I)
            target = None
            if trk_match:
                specific_trk = trk_match.group(1).upper()
                target = unpaid.filter(tracking_number__iexact=specific_trk).first()
            if not target:
                target = unpaid.first()

            if not target:
                return {
                    "reply": "✅ **All Clear!** You currently have no outstanding transit balances. All your shipments are fully paid.",
                    "spoken_text": "All clear! You currently have no outstanding transit balances. All your shipments are fully paid.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

            # Trigger live STK push to client phone!
            client_phone = getattr(user, 'phone_number', None) or '0712345678'
            stk_res = PayHeroService.initiate_stk_push(
                shipment=target,
                client=user,
                phone_number=client_phone,
                amount=target.delivery_fee,
                request=request
            )
            tx = stk_res['transaction']

            rep = f"""### 📲 M-Pesa Payment Prompt Dispatched!
- **Shipment:** `{target.tracking_number}` ({target.origin} ➔ {target.destination})
- **Amount:** **KES {target.delivery_fee:,.2f}**
- **Mobile Handset:** `{client_phone}`
- **Transaction Reference:** `{tx.reference}`

🔔 **Action on Your Mobile Phone:**
Safaricom has sent the payment prompt to your device. Please enter your M-Pesa PIN.
TransitFlow Voice AI is monitoring this transaction in real-time and will announce confirmation as soon as it succeeds!"""

            spk = f"I have sent an M-Pesa payment prompt of {int(target.delivery_fee)} Kenyan Shillings directly to your mobile phone ending in {client_phone[-4:]}. Please unlock your phone and enter your M-Pesa PIN. I am now monitoring for confirmation and will let you know once it is approved."

            return {
                "reply": rep,
                "spoken_text": spk,
                "action": "stk_push_sent",
                "reference": tx.reference,
                "tracking_number": target.tracking_number,
                "amount": float(target.delivery_fee),
                "suggested_prompts": [
                    f"🔍 Check status of {tx.reference}",
                    f"📦 Track {target.tracking_number}",
                    "💳 Pending payments"
                ]
            }

        # 3. Questions about payments / Lipwa Link / invoices
        if any(w in query for w in ['pay', 'lipwa', 'stk', 'cost', 'fee', 'invoice', 'balance', 'owe', 'money', 'mpesa', 'checkout', 'settle']):
            # Check if specific tracking number was mentioned
            trk_match = re.search(r'\b(tf-[a-z0-9\-]+)\b', query, re.I)
            if trk_match:
                specific_trk = trk_match.group(1).upper()
                try:
                    target_shipment = client_shipments.get(tracking_number__iexact=specific_trk)
                    if target_shipment.is_paid:
                        return {
                            "reply": f"✅ Shipment **{target_shipment.tracking_number}** is already **FULLY PAID** (Amount: KES {target_shipment.delivery_fee:,.2f}). No further payment is needed.",
                            "spoken_text": f"Shipment {target_shipment.tracking_number} is already fully paid. Amount was {int(target_shipment.delivery_fee)} shillings.",
                            "suggested_prompts": cls.get_suggested_prompts(user)
                        }
                    else:
                        client_phone = getattr(user, 'phone_number', None) or '0712345678'
                        lipwa_res = PayHeroService.generate_lipwa_link(
                            shipment=target_shipment,
                            client=user,
                            phone_number=client_phone,
                            amount=target_shipment.delivery_fee,
                            request=request
                        )
                        return {
                            "reply": f"""### 💳 Pending Payment: `{target_shipment.tracking_number}`
- **Shipment:** `{target_shipment.tracking_number}` ({target_shipment.origin} ➔ {target_shipment.destination})
- **Amount Due:** **KES {target_shipment.delivery_fee:,.2f}**
- **Billing Phone:** `{lipwa_res['transaction'].phone_number}`
- **Payment Reference:** `{lipwa_res['reference']}`

🗣️ **Voice AI Hands-Free Assistance:**
Say **'Yes'** or **'Send prompt'** to trigger an instant M-Pesa prompt directly to your phone.

👉 [💳 Click Here to Pay KES {target_shipment.delivery_fee:,.2f} via PayHero Lipwa Link]({lipwa_res['lipwa_url']})

*(You can also use [Portal Checkout & STK Push](/payments/initiate/{target_shipment.tracking_number}/))*""",
                            "spoken_text": f"You have an unpaid shipment, {target_shipment.tracking_number}, from {target_shipment.origin} to {target_shipment.destination}. The amount due is {int(target_shipment.delivery_fee)} Kenyan Shillings. Would you like me to trigger an M-Pesa payment prompt directly to your phone ending in {client_phone[-4:]}? Just say 'Yes' or 'Trigger payment' and I will send the prompt immediately.",
                            "action": "awaiting_payment_confirmation",
                            "tracking_number": target_shipment.tracking_number,
                            "amount": float(target_shipment.delivery_fee),
                            "suggested_prompts": [
                                "🗣️ Yes, send M-Pesa prompt to my phone",
                                f"💳 Pay {target_shipment.tracking_number} via Lipwa Link",
                                "📦 Track shipment"
                            ]
                        }
                except Shipment.DoesNotExist:
                    pass

            # General payment inquiry across all client shipments
            unpaid = client_shipments.filter(is_paid=False)
            if not unpaid.exists():
                return {
                    "reply": "✅ **All Clear!** You currently have no outstanding transit balances. All your shipments are fully paid.",
                    "spoken_text": "All clear! You currently have no outstanding transit balances. All your shipments are fully paid.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

            total_due = sum(s.delivery_fee for s in unpaid)
            cards = []
            suggested = []
            client_phone = getattr(user, 'phone_number', None) or '0712345678'
            first_unpaid = unpaid.first()
            for s in unpaid:
                lipwa_res = PayHeroService.generate_lipwa_link(
                    shipment=s,
                    client=user,
                    phone_number=client_phone,
                    amount=s.delivery_fee,
                    request=request
                )
                cards.append(
                    f"• **{s.tracking_number}** ({s.origin} ➔ {s.destination}): **KES {s.delivery_fee:,.2f}**\n"
                    f"  👉 [💳 Pay KES {s.delivery_fee:,.2f} via Lipwa Link]({lipwa_res['lipwa_url']}) &bull; [Portal Checkout](/payments/initiate/{s.tracking_number}/)"
                )
                suggested.append(f"💳 Pay for {s.tracking_number} via Lipwa Link")
            
            return {
                "reply": f"""### 💳 Pending Payments ({unpaid.count()} Consignment{'s' if unpaid.count() > 1 else ''}):
You have **{unpaid.count()}** unpaid shipment(s) totaling **KES {total_due:,.2f}**:

{chr(10).join(cards)}

🗣️ **Voice AI Hands-Free Assistance:**
Say **'Yes'** or **'Pay my shipment'** to trigger an instant M-Pesa prompt directly to your phone `{client_phone}`!""",
                "spoken_text": f"You have {unpaid.count()} unpaid shipment totaling {int(total_due)} Kenyan Shillings. For example, shipment {first_unpaid.tracking_number} is {int(first_unpaid.delivery_fee)} shillings. Would you like me to trigger an M-Pesa prompt to your phone ending in {client_phone[-4:]}? Just say 'Yes' or 'Trigger payment'.",
                "action": "awaiting_payment_confirmation",
                "tracking_number": first_unpaid.tracking_number,
                "amount": float(first_unpaid.delivery_fee),
                "suggested_prompts": [
                    "🗣️ Yes, trigger M-Pesa prompt",
                    f"💳 Pay {first_unpaid.tracking_number} via Lipwa Link",
                    "📦 Where are my shipments right now?"
                ]
            }

        # Questions about perishable goods
        if any(w in query for w in ['perishable', 'temperature', 'cold', 'spoil', 'fresh', 'expiry', 'fruit', 'meat', 'flower']):
            perishable_shipments = [s for s in client_shipments if s.has_perishable_items]
            if not perishable_shipments:
                return {
                    "reply": "ℹ️ None of your active shipments currently contain perishable goods. All registered items are classified as standard non-perishable freight.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }
            
            cards = []
            for s in perishable_shipments:
                p_items = s.items.filter(product__category=ProductCategory.PERISHABLE)
                names = ", ".join([f"{item.product.name} ({item.product.min_temp_celsius}°C to {item.product.max_temp_celsius}°C)" for item in p_items])
                cards.append(f"• **{s.tracking_number}** [{s.get_status_display()}]: {names} | Location: `{s.current_location}`")

            return {
                "reply": f"""### ❄️ Your Perishable Cargo in Transit:
We maintain strict cold-chain protocols for your temperature-sensitive products:
{chr(10).join(cards)}

All refrigerated shipments are monitored at transit checkpoints with temperature logs.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # Questions about shipment tracking / whereabouts
        if any(w in query for w in ['where', 'track', 'status', 'transit', 'location', 'package', 'goods', 'eta', 'delivery']):
            if not client_shipments.exists():
                return {
                    "reply": "You do not have any registered transit shipments yet. Click **'Book Shipment'** in your portal to dispatch goods.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }
            
            lines = []
            for s in client_shipments[:5]:
                cat = "❄️ Perishable" if s.has_perishable_items else "📦 Standard"
                lines.append(f"• **{s.tracking_number}** ({cat}): `{s.get_status_display()}` | Current Hub: **{s.current_location}** | Route: {s.origin} ➔ {s.destination}")

            return {
                "reply": f"""### 📍 Your Shipments in Transit:
{chr(10).join(lines)}

*Type any tracking number (e.g. `TF-2026-001`) to inspect complete event history and product breakdown.*""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # Fallback friendly response
        return {
            "reply": f"Hello {user.get_full_name() or user.username}! As a client, you can ask me to track your orders, check cold-chain condition for perishable goods, or check invoice balances for PayHero Lipwa Link payment.",
            "suggested_prompts": cls.get_suggested_prompts(user)
        }

    # -------------------------------------------------------------
    # DRIVER QUERIES (ASSIGNED VEHICLE & MANIFEST)
    # -------------------------------------------------------------
    @classmethod
    def _handle_driver_query(cls, user, query):
        driver_shipments = Shipment.objects.filter(assigned_driver=user).prefetch_related('items__product')

        if any(w in query for w in ['cargo', 'goods', 'transport', 'carrying', 'manifest', 'load', 'items']):
            if not driver_shipments.exists():
                return {
                    "reply": "🚛 You have no active transit shipments currently assigned to your vehicle.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }
            
            lines = []
            for s in driver_shipments:
                item_descs = [f"{i.quantity}x {i.product.name} ({'❄️ Cold' if i.product.is_perishable else '📦 Dry'})" for i in s.items.all()]
                lines.append(f"• **{s.tracking_number}** [{s.get_status_display()}] ➔ Destination: **{s.destination}**\n  Items: {', '.join(item_descs) if item_descs else 'No listed items'}")

            return {
                "reply": f"""### 🚚 Your Assigned Cargo Manifest:
Vehicle: `{user.vehicle_plate or 'Assigned Vehicle'}`
{chr(10).join(lines)}""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['perishable', 'temp', 'cold', 'refrigerat', 'freeze']):
            perishables = []
            for s in driver_shipments:
                for item in s.items.filter(product__category=ProductCategory.PERISHABLE):
                    perishables.append(
                        f"• **{item.product.name}** in `{s.tracking_number}`: Allowed temp **{item.product.min_temp_celsius}°C to {item.product.max_temp_celsius}°C** (Risk: {item.product.get_spoilage_risk_display()})"
                    )

            if not perishables:
                return {
                    "reply": "✅ There are no perishable or temperature-sensitive goods on your current manifest. All loaded items are non-perishable freight.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

            return {
                "reply": f"""### ❄️ Critical Perishable Goods Alert for Your Vehicle:
Ensure onboard reefer cooling units are functioning within target ranges:
{chr(10).join(perishables)}

⚠️ *If refrigeration dips or rises outside these boundaries, report a Checkpoint Incident immediately.*""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['checkpoint', 'log', 'update', 'status', 'incident', 'delay']):
            return {
                "reply": """### 📝 Driver Route Check-in Instructions:
1. Open your **Driver Transit Portal**.
2. Click **'Update Route Status'** on your active shipment.
3. Select current location (e.g., Highway Checkpoint, Toll Station, Depot Arrival).
4. If transporting perishable cargo, record the current trailer temperature (°C).
5. Mark arrival at destination to trigger delivery sign-off.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        return {
            "reply": f"Hello Driver {user.get_full_name() or user.username}. I can assist you with your cargo manifest, cold-chain temperature thresholds, and route checkpoint logging.",
            "suggested_prompts": cls.get_suggested_prompts(user)
        }

    # -------------------------------------------------------------
    # PORTER QUERIES (DEPOT HANDLING, LOADING & INSPECTION)
    # -------------------------------------------------------------
    @classmethod
    def _handle_porter_query(cls, user, query):
        if any(w in query for w in ['perishable', 'cold room', 'temp', 'refrigerat', 'fresh', 'spoil']):
            perishable_prods = Product.objects.filter(category=ProductCategory.PERISHABLE)
            lines = [f"• **{p.name}** (SKU: {p.sku}): Target {p.min_temp_celsius}°C - {p.max_temp_celsius}°C | Shelf life: {p.shelf_life_days or 'N/A'} days" for p in perishable_prods[:6]]
            return {
                "reply": f"""### ❄️ Cold-Room Storage Protocols (Perishable Cargo):
Porters must verify the following temperature tolerances during handling:
{chr(10).join(lines)}

**Handling Rule:** Perishable items must not remain on open loading docks for more than 15 minutes before transfer to refrigerated storage or chilled trailers.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['fragile', 'hazard', 'safety', 'stack', 'handling', 'non-perishable']):
            fragile_prods = Product.objects.filter(category=ProductCategory.NON_PERISHABLE, is_fragile=True)
            lines = [f"• **{p.name}** (SKU: {p.sku}): Handle with care. Stacking: {'Yes' if p.stackable else 'NO - Top Load Only'}" for p in fragile_prods[:5]]
            return {
                "reply": f"""### 📦 Fragile & Non-Perishable Cargo Handling:
{chr(10).join(lines) if lines else "No designated fragile non-perishables in active queue."}

**Stowage Best Practices:**
- Heavy non-perishables go on floor pallets.
- Fragile cartons must never be stacked underneath bulk sacks or machinery.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['inspect', 'checkin', 'checklist', 'load', 'unload']):
            return {
                "reply": """### 📋 Porter Loading / Unloading Checklist:
1. Verify package count against the Manifest / Waybill.
2. For **Perishable Goods**, take physical temperature with infrared thermometer.
3. Inspect seals, strapping, and moisture barriers.
4. Record cargo check-in in the **Porter Portal** with condition status (Optimal, Minor Issue, or Damaged).""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        return {
            "reply": f"Hello Porter {user.get_full_name() or user.username}. I can provide loading checklists, perishable cold-room specifications, and cargo inspection guidance.",
            "suggested_prompts": cls.get_suggested_prompts(user)
        }

    # -------------------------------------------------------------
    # MANAGER QUERIES (FULL OVERSIGHT & METRICS)
    # -------------------------------------------------------------
    @classmethod
    def _handle_manager_query(cls, user, query, request=None):
        total_shipments = Shipment.objects.count()
        in_transit = Shipment.objects.filter(status=ShipmentStatus.IN_TRANSIT).count()
        temp_alerts = Shipment.objects.filter(status=ShipmentStatus.TEMP_ALERT).count()
        delayed = Shipment.objects.filter(status=ShipmentStatus.DELAYED).count()
        
        perishable_items_count = ShipmentItem.objects.filter(product__category=ProductCategory.PERISHABLE).count()
        non_perishable_count = ShipmentItem.objects.filter(product__category=ProductCategory.NON_PERISHABLE).count()

        if any(w in query for w in ['overview', 'summary', 'status', 'system', 'dashboard', 'fleet']):
            return {
                "reply": f"""### 📊 TransitFlow Fleet & Cargo Executive Summary:
- **Total Shipments Logged:** {total_shipments}
- **Active on Highway (In-Transit):** {in_transit}
- **Perishable Cargo Consignments:** {perishable_items_count} units
- **Non-Perishable Cargo Consignments:** {non_perishable_count} units
- **⚠️ Temperature Alerts:** {temp_alerts}
- **⏱️ Transit Delays:** {delayed}

Operational status is within nominal parameters across regional depots.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['unpaid', 'pending payment', 'lipwa link', 'pay link', 'outstanding']):
            unpaid_shipments = Shipment.objects.filter(is_paid=False).select_related('client')
            if not unpaid_shipments.exists():
                return {
                    "reply": "✅ **All Clear!** There are zero unpaid shipments across all clients in the registry.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }
            lines = []
            for s in unpaid_shipments[:5]:
                client_phone = getattr(s.client, 'phone_number', None) or '0712345678'
                lipwa_res = PayHeroService.generate_lipwa_link(
                    shipment=s,
                    client=s.client,
                    phone_number=client_phone,
                    amount=s.delivery_fee,
                    request=request
                )
                lines.append(
                    f"• **{s.tracking_number}** (Client: {s.client.get_full_name() or s.client.username}): **KES {s.delivery_fee:,.2f}**\n"
                    f"  👉 [💳 Open Lipwa Link]({lipwa_res['lipwa_url']}) &bull; [Portal Checkout](/payments/initiate/{s.tracking_number}/)"
                )
            return {
                "reply": f"""### 💳 Unpaid Consignments ({unpaid_shipments.count()} Pending):
{chr(10).join(lines)}

*You can open any Lipwa Link directly or manage credentials in API settings.*""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['perishable', 'cold', 'temp', 'alert', 'spoil']):
            alerts = Shipment.objects.filter(status=ShipmentStatus.TEMP_ALERT)
            alert_lines = [f"• 🚨 **{s.tracking_number}** at `{s.current_location}` | Driver: {s.assigned_driver or 'None'}" for s in alerts]
            
            return {
                "reply": f"""### ❄️ Perishable Goods Health & Temperature Watch:
- **Total Perishable Consignments:** {perishable_items_count}
- **Active Alerts:** {temp_alerts}
{chr(10).join(alert_lines) if alert_lines else "✅ Zero critical temperature excursions currently active."}

Perishable freight is categorized with strict bounds (2°C - 6°C cold-chain or chilled) and monitored at all checkpoints.""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['financial', 'revenue', 'payment', 'money', 'payhero', 'lipwa', 'sales']):
            paid_count = PaymentTransaction.objects.filter(status=PaymentStatus.SUCCESS).count()
            pending_count = PaymentTransaction.objects.filter(status=PaymentStatus.PENDING).count()
            failed_count = PaymentTransaction.objects.filter(status=PaymentStatus.FAILED).count()
            total_revenue = sum(t.amount for t in PaymentTransaction.objects.filter(status=PaymentStatus.SUCCESS))
            total_credited = sum(log.amount for log in ClientCreditLog.objects.filter(action_type='CREDIT'))
            
            return {
                "reply": f"""### 💳 Financial & PayHero Integration Report:
- **Total Confirmed Revenue:** KES {total_revenue:,.2f}
- **Successful Transactions:** {paid_count}
- **Pending Payments:** {pending_count}
- **Failed Transactions:** {failed_count}
- **Total Client Compensatory Credits Issued:** KES {total_credited:,.2f}
- **Integration Channels:** PayHero Lipwa Link, STK Push, Paybill, Credit Balance

Manage API keys and view real-time webhook callback logs in the **Payments Configuration** panel.
👉 [View Credit Audit Logs & Compensations](/payments/)""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # Manager Rate Setting — "set rate for product", "update freight tariff", "change rate"
        is_rate_query = any(
            phrase in query for phrase in [
                'set rate', 'update rate', 'change rate', 'freight rate', 'tariff',
                'set tariff', 'goods rate', 'shipping rate', 'handling fee',
                'set freight', 'update tariff', 'configure rate', 'manage rates'
            ]
        )
        if is_rate_query:
            # Check if a specific product is named
            products = Product.objects.all()[:10]
            prod_lines = [
                f"• **{p.name}** (SKU: {p.sku}) — Current Rate: **KES {p.shipping_rate_per_kg:,.2f}/kg** | Base Handling: **KES {p.base_handling_fee:,.2f}**"
                for p in products
            ]
            return {
                "reply": f"""### 🏷️ Freight Rate Management — Manager Control

You can configure freight tariffs and per-kilogram shipping rates for all client goods.

#### Current Product Rates:
{chr(10).join(prod_lines) if prod_lines else "No products registered yet."}

#### How to Update Rates:
1. Navigate to **[Goods Rates & Tariffs Dashboard](/logistics/rates/)**
2. Edit the rate directly in the table for any product
3. For individual shipments, click **"Set Rate"** or **"Auto Tariff"** buttons

**Formula used:**
> Fee = (Product Weight × Rate/kg) + Base Handling Fee + Cold-Chain Surcharge (KES 800 for perishables)

You can also type: *"Set rate for TF-2026-001 to 5000"* to override a specific shipment's fee.""",
                "spoken_text": f"You can configure freight rates from the Goods Rates and Tariffs panel. There are currently {products.count()} products configured. Navigate to the rates dashboard to update per-kilogram charges and base handling fees.",
                "suggested_prompts": [
                    "🏷️ Show all product rates",
                    "💳 Financial & payment summary",
                    "📊 Overall transit overview"
                ]
            }

        # Manager setting a specific shipment rate via chatbot: "Set rate for TF-2026-001 to 4500"
        set_rate_match = re.search(r'set\s+rate\s+for\s+(tf-[a-z0-9\-]+)\s+to\s+([\d,]+(?:\.\d+)?)', query, re.I)
        if set_rate_match:
            tracking = set_rate_match.group(1).upper()
            rate_str = set_rate_match.group(2).replace(',', '')
            try:
                new_fee = Decimal(rate_str)
                try:
                    shipment = Shipment.objects.get(tracking_number__iexact=tracking)
                    old_fee = shipment.delivery_fee
                    shipment.delivery_fee = new_fee
                    shipment.save(update_fields=['delivery_fee'])
                    return {
                        "reply": f"✅ **Rate Updated!** Shipment **{tracking}** delivery fee updated from **KES {old_fee:,.2f}** to **KES {new_fee:,.2f}**.\n\n👉 [View Shipment](/logistics/shipments/{tracking}/)",
                        "spoken_text": f"Done. I have updated the delivery fee for shipment {tracking} from {int(old_fee)} to {int(new_fee)} Kenyan Shillings.",
                        "action": "rate_updated",
                        "tracking_number": tracking,
                        "new_fee": float(new_fee),
                        "suggested_prompts": [
                            f"📦 View shipment {tracking}",
                            "🏷️ Manage all freight rates",
                            "📊 Fleet overview"
                        ]
                    }
                except Shipment.DoesNotExist:
                    return {
                        "reply": f"🔍 Shipment **{tracking}** was not found in the system. Please verify the tracking number.",
                        "suggested_prompts": cls.get_suggested_prompts(user)
                    }
            except Exception:
                return {
                    "reply": f"❌ Invalid rate value: `{rate_str}`. Please provide a numeric fee (e.g., 'Set rate for TF-2026-001 to 4500').",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

        # Manager credit balance / compensation overview
        is_credit_overview = any(
            phrase in query for phrase in [
                'credit balance', 'client credit', 'compensatory credit', 'credit overview',
                'credits issued', 'failed transactions credit', 'credit log', 'compensation'
            ]
        )
        if is_credit_overview:
            from core.models import User as UserModel
            credits_issued = ClientCreditLog.objects.filter(action_type='CREDIT').count()
            total_credited = sum(log.amount for log in ClientCreditLog.objects.filter(action_type='CREDIT'))
            failed_txs = PaymentTransaction.objects.filter(status=PaymentStatus.FAILED, is_credited=True).count()
            # Clients with non-zero balances
            clients_with_credit = UserModel.objects.filter(role='CLIENT', credit_balance__gt=0).values_list('username', 'credit_balance')[:8]
            client_lines = [f"• **{name}**: KES {bal:,.2f}" for name, bal in clients_with_credit]
            return {
                "reply": f"""### 💰 Client Credit Balance & Compensation Overview

- **Total Compensation Credits Issued:** {credits_issued} events
- **Total Amount Compensated:** KES {total_credited:,.2f}
- **Failed Txs with Auto-Credit Applied:** {failed_txs}

#### Clients with Active Credit Balances:
{chr(10).join(client_lines) if client_lines else "No clients currently hold outstanding credit balances."}

👉 [View Full Credit Audit Log](/payments/)""",
                "spoken_text": f"As a manager, you have issued {credits_issued} compensatory credit events totalling {int(total_credited)} Kenyan Shillings to clients whose payments failed.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        if any(w in query for w in ['driver', 'drivers', 'vehicle', 'fleet', 'truck']):
            from core.models import User, UserRole
            drivers = User.objects.filter(role=UserRole.DRIVER)
            lines = [f"• **{d.get_full_name() or d.username}** (Plate: `{d.vehicle_plate or 'Not Assigned'}`) - Active Runs: {d.driver_shipments.filter(status=ShipmentStatus.IN_TRANSIT).count()}" for d in drivers[:6]]
            return {
                "reply": f"""### 🚚 Active Driver Registry:
{chr(10).join(lines) if lines else "No drivers registered yet."}""",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        return {
            "reply": f"Hello Operations Manager {user.get_full_name() or user.username}. You have unrestricted access. Ask about fleet overview, perishable temperature integrity, payment analytics, freight tariff rates, client credit balances, or specific tracking numbers. You can also type 'Set rate for TF-XXXX to 4500' to update a shipment's delivery fee directly from here.",
            "spoken_text": f"Hello Manager {user.get_full_name() or user.username}. You have full operational access. Ask me about fleet overview, temperature alerts, payment analytics, or freight tariff rates. You can also set shipment rates directly by saying 'Set rate for a tracking number to an amount'.",
            "suggested_prompts": cls.get_suggested_prompts(user)
        }
