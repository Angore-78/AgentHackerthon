from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
import uuid

from core.decorators import role_required
from core.models import User, UserRole
from .models import (
    Shipment, ShipmentItem, Product, ProductCategory,
    ShipmentStatus, TransitEvent, TransitHub, SpoilageRisk
)

# -----------------------------------------------------------------------------
# MANAGER PORTAL
# -----------------------------------------------------------------------------
@login_required
@role_required(['MANAGER'])
def manager_dashboard(request):
    shipments = Shipment.objects.all().select_related('client', 'assigned_driver', 'assigned_porter').prefetch_related('items__product', 'transit_events')
    
    # Filter by category if requested
    cat_filter = request.GET.get('category')
    if cat_filter == 'PERISHABLE':
        shipments = [s for s in shipments if s.has_perishable_items]
    elif cat_filter == 'NON_PERISHABLE':
        shipments = [s for s in shipments if not s.has_perishable_items]

    # Metrics
    all_shipments_list = list(Shipment.objects.all().prefetch_related('items__product'))
    total_count = len(all_shipments_list)
    in_transit_count = sum(1 for s in all_shipments_list if s.status == ShipmentStatus.IN_TRANSIT)
    perishable_count = sum(1 for s in all_shipments_list if s.has_perishable_items)
    non_perishable_count = total_count - perishable_count
    temp_alerts_count = sum(1 for s in all_shipments_list if s.status == ShipmentStatus.TEMP_ALERT)
    delivered_count = sum(1 for s in all_shipments_list if s.status == ShipmentStatus.DELIVERED)

    # Active drivers & porters for assignment dropdowns
    drivers = User.objects.filter(role=UserRole.DRIVER)
    porters = User.objects.filter(role=UserRole.PORTER)
    clients = User.objects.filter(role=UserRole.CLIENT)
    products = Product.objects.all()
    hubs = TransitHub.objects.all()

    context = {
        'shipments': shipments,
        'total_count': total_count,
        'in_transit_count': in_transit_count,
        'perishable_count': perishable_count,
        'non_perishable_count': non_perishable_count,
        'temp_alerts_count': temp_alerts_count,
        'delivered_count': delivered_count,
        'cat_filter': cat_filter,
        'drivers': drivers,
        'porters': porters,
        'clients': clients,
        'products': products,
        'hubs': hubs,
        'statuses': ShipmentStatus.choices,
    }
    return render(request, 'logistics/manager_dashboard.html', context)


# -----------------------------------------------------------------------------
# PORTER PORTAL (CARGO HANDLING & DEPOT INSPECTION)
# -----------------------------------------------------------------------------
@login_required
@role_required(['PORTER', 'MANAGER'])
def porter_dashboard(request):
    # Porters see shipments at origin depot, awaiting loading, or assigned to them
    shipments = Shipment.objects.filter(
        status__in=[
            ShipmentStatus.BOOKED,
            ShipmentStatus.RECEIVED_AT_HUB,
            ShipmentStatus.LOADING,
            ShipmentStatus.ARRIVED_DESTINATION,
            ShipmentStatus.TEMP_ALERT,
        ]
    ).select_related('client', 'assigned_driver').prefetch_related('items__product', 'transit_events')

    perishable_items = Product.objects.filter(category=ProductCategory.PERISHABLE)
    hubs = TransitHub.objects.all()

    context = {
        'shipments': shipments,
        'perishable_items': perishable_items,
        'hubs': hubs,
    }
    return render(request, 'logistics/porter_dashboard.html', context)


# -----------------------------------------------------------------------------
# DRIVER PORTAL (TRANSIT RUNS & HIGHWAY ROUTE CHECKPOINTS)
# -----------------------------------------------------------------------------
@login_required
@role_required(['DRIVER', 'MANAGER'])
def driver_dashboard(request):
    # Drivers see shipments assigned to them
    assigned_shipments = Shipment.objects.filter(
        assigned_driver=request.user
    ).select_related('client', 'assigned_porter').prefetch_related('items__product', 'transit_events')

    active_shipments = assigned_shipments.exclude(status=ShipmentStatus.DELIVERED).exclude(status=ShipmentStatus.CANCELLED)
    delivered_shipments = assigned_shipments.filter(status=ShipmentStatus.DELIVERED)

    context = {
        'active_shipments': active_shipments,
        'delivered_shipments': delivered_shipments,
        'vehicle_plate': request.user.vehicle_plate or "KDF 420X",
    }
    return render(request, 'logistics/driver_dashboard.html', context)


# -----------------------------------------------------------------------------
# CLIENT PORTAL (CONSIGNOR TRACKING & INVOICING)
# -----------------------------------------------------------------------------
@login_required
@role_required(['CLIENT', 'MANAGER'])
def client_dashboard(request):
    # Clients see only their own shipments
    shipments = Shipment.objects.filter(
        client=request.user
    ).select_related('assigned_driver').prefetch_related('items__product', 'transit_events', 'payments')

    products = Product.objects.all()
    unpaid_total = sum(s.delivery_fee for s in shipments if not s.is_paid)

    context = {
        'shipments': shipments,
        'products': products,
        'unpaid_total': unpaid_total,
    }
    return render(request, 'logistics/client_dashboard.html', context)


# -----------------------------------------------------------------------------
# SHIPMENT DETAIL VIEW (UNIVERSAL / SCOPED)
# -----------------------------------------------------------------------------
@login_required
def shipment_detail(request, tracking_number):
    shipment = get_object_or_404(
        Shipment.objects.select_related('client', 'assigned_driver', 'assigned_porter').prefetch_related('items__product', 'transit_events__logged_by', 'payments'),
        tracking_number=tracking_number
    )

    # Permission check: Clients can only see their own
    if request.user.is_client and shipment.client_id != request.user.id:
        messages.error(request, "Access restricted: You cannot view this shipment record.")
        return redirect('client_dashboard')

    # Driver check: Driver can only view assigned or manager
    if request.user.is_driver and shipment.assigned_driver_id != request.user.id and not request.user.is_manager:
        messages.error(request, "Access restricted: Shipment is not on your manifest.")
        return redirect('driver_dashboard')

    events = shipment.transit_events.order_by('-timestamp')
    latest_event = events.first()

    context = {
        'shipment': shipment,
        'events': events,
        'latest_event': latest_event,
        'items': shipment.items.all(),
        'payments': shipment.payments.all(),
    }
    return render(request, 'logistics/shipment_detail.html', context)


# -----------------------------------------------------------------------------
# ACTIONS: LOG TRANSIT EVENT / CHECKPOINT / TEMPERATURE
# -----------------------------------------------------------------------------
@login_required
def log_transit_event(request, tracking_number):
    shipment = get_object_or_404(Shipment, tracking_number=tracking_number)

    if request.method == 'POST':
        event_type = request.POST.get('event_type')
        location = request.POST.get('location', shipment.current_location)
        cargo_condition = request.POST.get('cargo_condition', 'OPTIMAL')
        temp_reading = request.POST.get('temperature_celsius')
        seal_intact = request.POST.get('seal_intact') == 'on'
        remarks = request.POST.get('remarks', '')
        new_status = request.POST.get('new_status')

        temp_val = None
        if temp_reading and temp_reading.strip():
            try:
                temp_val = Decimal(temp_reading.strip())
            except Exception:
                temp_val = None

        event = TransitEvent(
            shipment=shipment,
            logged_by=request.user,
            event_type=event_type,
            location=location,
            temperature_celsius=temp_val,
            cargo_condition=cargo_condition,
            seal_intact=seal_intact,
            remarks=remarks
        )
        event.save()

        # Update shipment location & status
        shipment.current_location = location
        if new_status:
            shipment.status = new_status
            if new_status == ShipmentStatus.DELIVERED:
                shipment.actual_arrival = timezone.now()
            elif new_status == ShipmentStatus.IN_TRANSIT and not shipment.departure_time:
                shipment.departure_time = timezone.now()
        shipment.save()

        if event.is_temp_breach:
            messages.warning(request, f"🚨 TEMPERATURE BREACH RECORDED! Reading ({temp_val}°C) breached permissible limits for perishable goods. Alert triggered!")
        else:
            messages.success(request, f"Checkpoint event successfully logged at {location}.")

    return redirect('shipment_detail', tracking_number=tracking_number)


# -----------------------------------------------------------------------------
# ACTIONS: CREATE SHIPMENT (MANAGER OR CLIENT)
# -----------------------------------------------------------------------------
@login_required
def create_shipment(request):
    if request.method == 'POST':
        # Determine client
        if request.user.is_client:
            client_user = request.user
        else:
            client_id = request.POST.get('client_id')
            client_user = get_object_or_404(User, id=client_id, role=UserRole.CLIENT)

        origin = request.POST.get('origin', 'Nairobi Central Terminal')
        destination = request.POST.get('destination', 'Mombasa Logistics Hub')
        delivery_fee = request.POST.get('delivery_fee', '3500.00')

        # Auto-generate tracking number
        tracking_num = f"TF-{timezone.now().year}-{uuid.uuid4().hex[:6].upper()}"

        shipment = Shipment.objects.create(
            tracking_number=tracking_num,
            client=client_user,
            origin=origin,
            destination=destination,
            current_location=origin,
            delivery_fee=Decimal(delivery_fee),
            status=ShipmentStatus.BOOKED
        )

        # Assign driver/porter if manager
        if request.user.is_manager:
            driver_id = request.POST.get('driver_id')
            porter_id = request.POST.get('porter_id')
            if driver_id:
                shipment.assigned_driver = User.objects.filter(id=driver_id, role=UserRole.DRIVER).first()
            if porter_id:
                shipment.assigned_porter = User.objects.filter(id=porter_id, role=UserRole.PORTER).first()
            shipment.vehicle_plate = request.POST.get('vehicle_plate', '')
            shipment.save()

        # Add items
        product_ids = request.POST.getlist('product_ids')
        quantities = request.POST.getlist('quantities')
        package_types = request.POST.getlist('package_types')

        for i, prod_id in enumerate(product_ids):
            if prod_id:
                prod = Product.objects.filter(id=prod_id).first()
                if prod:
                    qty = int(quantities[i]) if i < len(quantities) and quantities[i].isdigit() else 1
                    pkg = package_types[i] if i < len(package_types) else 'CARTON'
                    ShipmentItem.objects.create(
                        shipment=shipment,
                        product=prod,
                        quantity=qty,
                        package_type=pkg
                    )

        # Apply recommended tariff if requested or delivery fee was left default
        if request.POST.get('auto_rate') == 'on':
            shipment.delivery_fee = shipment.calculate_recommended_fee()
            shipment.save(update_fields=['delivery_fee'])

        # Log initial event
        TransitEvent.objects.create(
            shipment=shipment,
            logged_by=request.user,
            event_type='CHECKIN',
            location=origin,
            cargo_condition='OPTIMAL',
            remarks=f"Shipment booked by {client_user.get_full_name() or client_user.username}"
        )

        messages.success(request, f"New shipment booked successfully! Tracking Number: {tracking_num}")
        return redirect('shipment_detail', tracking_number=tracking_num)

    return redirect('portal_redirect')


# -----------------------------------------------------------------------------
# ACTIONS: CREATE PRODUCT (PERISHABLE VS NON-PERISHABLE & RATES)
# -----------------------------------------------------------------------------
@login_required
@role_required(['MANAGER'])
def create_product(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        sku = request.POST.get('sku') or f"SKU-{uuid.uuid4().hex[:6].upper()}"
        category = request.POST.get('category', ProductCategory.NON_PERISHABLE)
        description = request.POST.get('description', '')
        unit_weight = Decimal(request.POST.get('unit_weight_kg', '1.0'))
        declared_value = Decimal(request.POST.get('declared_value', '0.0'))
        shipping_rate = Decimal(request.POST.get('shipping_rate_per_kg', '25.00'))
        base_fee = Decimal(request.POST.get('base_handling_fee', '500.00'))

        product = Product(
            name=name,
            sku=sku,
            category=category,
            description=description,
            unit_weight_kg=unit_weight,
            declared_value=declared_value,
            shipping_rate_per_kg=shipping_rate,
            base_handling_fee=base_fee,
        )

        if category == ProductCategory.PERISHABLE:
            product.requires_refrigeration = request.POST.get('requires_refrigeration') == 'on'
            min_temp = request.POST.get('min_temp_celsius')
            max_temp = request.POST.get('max_temp_celsius')
            if min_temp: product.min_temp_celsius = Decimal(min_temp)
            if max_temp: product.max_temp_celsius = Decimal(max_temp)
            product.spoilage_risk = request.POST.get('spoilage_risk', SpoilageRisk.MEDIUM)
            shelf_life = request.POST.get('shelf_life_days')
            if shelf_life and shelf_life.isdigit():
                product.shelf_life_days = int(shelf_life)
            product.humidity_requirement = request.POST.get('humidity_requirement', '')
        else:
            product.is_fragile = request.POST.get('is_fragile') == 'on'
            product.is_hazardous = request.POST.get('is_hazardous') == 'on'
            product.stackable = request.POST.get('stackable') == 'on'
            product.handling_instructions = request.POST.get('handling_instructions', '')

        product.save()
        messages.success(request, f"Product registered: {product.name} ({product.get_category_display()}) with rate KES {product.shipping_rate_per_kg}/kg")

    return redirect('manager_dashboard')


# -----------------------------------------------------------------------------
# MANAGER RATES MANAGEMENT (GOODS TARIFFS & SHIPMENT RATES)
# -----------------------------------------------------------------------------
@login_required
@role_required(['MANAGER'])
def manage_rates(request):
    """
    Manager view to review and configure freight rates for client goods (products)
    and adjust or override shipment delivery fees.
    """
    products = Product.objects.all().order_by('category', 'name')
    shipments = Shipment.objects.all().select_related('client').prefetch_related('items__product')[:40]

    # Calculate recommended fees for comparison
    shipments_with_rates = []
    for s in shipments:
        rec_fee = s.calculate_recommended_fee()
        shipments_with_rates.append({
            'shipment': s,
            'recommended_fee': rec_fee,
            'diff': s.delivery_fee - rec_fee
        })

    context = {
        'products': products,
        'shipments_with_rates': shipments_with_rates,
    }
    return render(request, 'logistics/manage_rates.html', context)


@login_required
@role_required(['MANAGER'])
def update_product_rate(request, product_id):
    """
    Allows managers to set the per-kg freight rate and base handling fee for any cargo product.
    """
    product = get_object_or_404(Product, id=product_id)
    if request.method == 'POST':
        rate = request.POST.get('shipping_rate_per_kg')
        base = request.POST.get('base_handling_fee')
        try:
            if rate:
                product.shipping_rate_per_kg = Decimal(rate)
            if base:
                product.base_handling_fee = Decimal(base)
            product.save(update_fields=['shipping_rate_per_kg', 'base_handling_fee'])
            messages.success(
                request,
                f"✅ Rates updated for {product.name}: KES {product.shipping_rate_per_kg:,.2f}/kg, Base Fee: KES {product.base_handling_fee:,.2f}."
            )
        except Exception as e:
            messages.error(request, f"Error updating product rate: {str(e)}")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'manage_rates'
    return redirect(next_url)


@login_required
@role_required(['MANAGER'])
def set_shipment_rate(request, tracking_number):
    """
    Allows managers to set or override the delivery fee for a specific client shipment.
    Also supports applying the automated tariff formula.
    """
    shipment = get_object_or_404(Shipment, tracking_number=tracking_number)
    if request.method == 'POST':
        action = request.POST.get('action', 'custom')
        if action == 'auto':
            new_fee = shipment.calculate_recommended_fee()
            shipment.delivery_fee = new_fee
            shipment.save(update_fields=['delivery_fee'])
            messages.success(
                request,
                f"✅ Automated freight rate applied to #{shipment.tracking_number}: KES {new_fee:,.2f} based on item weights and categories."
            )
        else:
            fee_str = request.POST.get('delivery_fee')
            try:
                new_fee = Decimal(fee_str)
                old_fee = shipment.delivery_fee
                shipment.delivery_fee = new_fee
                shipment.save(update_fields=['delivery_fee'])
                messages.success(
                    request,
                    f"✅ Freight rate for #{shipment.tracking_number} updated from KES {old_fee:,.2f} to KES {new_fee:,.2f}."
                )
            except Exception as e:
                messages.error(request, f"Invalid delivery fee amount: {str(e)}")

    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or 'manage_rates'
    return redirect(next_url)
