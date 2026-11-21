import re
from django.utils import timezone
from logistics.models import Shipment, ShipmentItem, Product, ProductCategory, ShipmentStatus, TransitEvent
from payments.models import PaymentTransaction, PaymentStatus
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
                "💳 Pay pending shipments via Lipwa Link",
                "📦 Where are my shipments right now?",
                "❄️ How are my perishable goods being preserved?",
                "🔗 How to pay with PayHero Lipwa Link?"
            ]

    @classmethod
    def process_query(cls, user, query_text, request=None):
        query = (query_text or "").strip().lower()
        role = getattr(user, 'role', 'CLIENT')
        
        # Check for empty query
        if not query:
            return {
                "reply": "Hello! I am your TransitFlow Assistant. Ask me anything about goods in transit, handling guidelines, shipment status, or payments based on your clearance.",
                "suggested_prompts": cls.get_suggested_prompts(user)
            }

        # If it's an explicit payment action, let the role-specific payment handlers process it
        is_payment_intent = any(w in query for w in ['pay', 'lipwa', 'checkout', 'settle'])

        # Check for explicit tracking number format like TF-XXXX or TF-XXXX-XXXX
        trk_match = re.search(r'\b(tf-[a-z0-9\-]+)\b', query, re.I)
        if trk_match and not is_payment_intent:
            tracking_num = trk_match.group(1).upper()
            return cls._handle_tracking_query(user, tracking_num, request=request)

        # Route by Role-specific logic
        if user.is_manager or user.is_superuser:
            return cls._handle_manager_query(user, query, request=request)
        elif role == 'DRIVER':
            return cls._handle_driver_query(user, query)
        elif role == 'PORTER':
            return cls._handle_porter_query(user, query)
        else:
            return cls._handle_client_query(user, query, request=request)

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

        # Questions about payments / Lipwa Link / invoices
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
                            "reply": f"""### 💳 PayHero Lipwa Link for `{target_shipment.tracking_number}`
- **Shipment:** `{target_shipment.tracking_number}` ({target_shipment.origin} ➔ {target_shipment.destination})
- **Amount Due:** **KES {target_shipment.delivery_fee:,.2f}**
- **Billing Phone:** `{lipwa_res['transaction'].phone_number}`
- **Payment Reference:** `{lipwa_res['reference']}`

👉 [💳 Click Here to Pay KES {target_shipment.delivery_fee:,.2f} via PayHero Lipwa Link]({lipwa_res['lipwa_url']})

💡 **How to complete payment:**
1. Click the **Pay via PayHero Lipwa Link** button above.
2. Review the pre-filled payment details on PayHero's secure checkout.
3. Check your mobile phone and enter your Safaricom M-Pesa PIN.
4. Once authorized, TransitFlow instantly updates this shipment to **PAID** via automated webhook reconciliation!

*(You can also use [Portal Checkout & STK Push](/payments/initiate/{target_shipment.tracking_number}/))*""",
                            "suggested_prompts": [
                                f"📦 Track {target_shipment.tracking_number}",
                                "💳 Do I have other pending payments?",
                                "❄️ Check perishable goods status"
                            ]
                        }
                except Shipment.DoesNotExist:
                    pass

            # General payment inquiry across all client shipments
            unpaid = client_shipments.filter(is_paid=False)
            if not unpaid.exists():
                return {
                    "reply": "✅ **All Clear!** You currently have no outstanding transit balances. All your shipments are fully paid.",
                    "suggested_prompts": cls.get_suggested_prompts(user)
                }

            total_due = sum(s.delivery_fee for s in unpaid)
            cards = []
            suggested = []
            client_phone = getattr(user, 'phone_number', None) or '0712345678'
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
                "reply": f"""### 💳 Pending Payments & PayHero Lipwa Links:
You have **{unpaid.count()}** unpaid shipment(s) totaling **KES {total_due:,.2f}**:

{chr(10).join(cards)}

💡 **How to Pay with PayHero Lipwa Link:**
1. Click the **Pay via Lipwa Link** link for any consignment above.
2. Enter your M-Pesa PIN on your mobile device when prompted.
3. The PayHero webhook will immediately reconcile the payment and flip your shipment to **PAID**!""",
                "suggested_prompts": suggested[:3] + ["📦 Where are my shipments right now?"]
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
            total_revenue = sum(t.amount for t in PaymentTransaction.objects.filter(status=PaymentStatus.SUCCESS))
            
            return {
                "reply": f"""### 💳 Financial & PayHero Integration Report:
- **Total Confirmed Revenue:** KES {total_revenue:,.2f}
- **Successful Transactions:** {paid_count}
- **Pending Payments:** {pending_count}
- **Integration Channels:** PayHero Lipwa Link, STK Push, Paybill

Manage API keys and view real-time webhook callback logs in the **Payments Configuration** panel.""",
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
            "reply": f"Hello Operations Manager {user.get_full_name() or user.username}. You have unrestricted access. Ask about fleet overview, perishable temperature integrity, payment analytics, or specific tracking numbers.",
            "suggested_prompts": cls.get_suggested_prompts(user)
        }
