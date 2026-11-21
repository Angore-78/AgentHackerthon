from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import uuid

class ProductCategory(models.TextChoices):
    PERISHABLE = 'PERISHABLE', 'Perishable Goods'
    NON_PERISHABLE = 'NON_PERISHABLE', 'Non-Perishable Goods'

class SpoilageRisk(models.TextChoices):
    LOW = 'LOW', 'Low Risk'
    MEDIUM = 'MEDIUM', 'Medium Risk'
    HIGH = 'HIGH', 'High Spoilage Risk'
    CRITICAL = 'CRITICAL', 'Critical (Rapid Expiry)'

class ShipmentStatus(models.TextChoices):
    BOOKED = 'BOOKED', 'Order Booked'
    RECEIVED_AT_HUB = 'RECEIVED_AT_HUB', 'Received at Depot'
    LOADING = 'LOADING', 'Loading onto Transit'
    IN_TRANSIT = 'IN_TRANSIT', 'In Transit'
    AT_CHECKPOINT = 'AT_CHECKPOINT', 'At Transit Checkpoint'
    ARRIVED_DESTINATION = 'ARRIVED_DESTINATION', 'Arrived at Destination Hub'
    OUT_FOR_DELIVERY = 'OUT_FOR_DELIVERY', 'Out for Delivery'
    DELIVERED = 'DELIVERED', 'Delivered & Signed'
    DELAYED = 'DELAYED', 'Transit Delayed'
    TEMP_ALERT = 'TEMP_ALERT', 'Temperature Alert'
    CANCELLED = 'CANCELLED', 'Cancelled'

class TransitHub(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    city = models.CharField(max_length=80)
    hub_type = models.CharField(
        max_length=50,
        choices=[
            ('CENTRAL_DEPOT', 'Central Depot'),
            ('COLD_STORAGE_HUB', 'Cold Storage Terminal'),
            ('TRANSIT_CHECKPOINT', 'Highway Checkpoint'),
            ('DISTRIBUTION_CENTER', 'Distribution Center'),
        ],
        default='CENTRAL_DEPOT'
    )
    has_cold_storage = models.BooleanField(default=True, help_text="Equipped with cold storage for perishable cargo")
    contact_phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.name} ({self.code}) - {self.city}"

class Product(models.Model):
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=50, unique=True)
    category = models.CharField(
        max_length=20,
        choices=ProductCategory.choices,
        default=ProductCategory.NON_PERISHABLE,
        help_text="Crucial distinction: Perishable vs Non-Perishable goods."
    )
    description = models.TextField(blank=True)
    unit_weight_kg = models.DecimalField(max_digits=10, decimal_places=2, default=1.0)
    declared_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Value in KES")

    # Manager-configurable freight tariffs & rates
    shipping_rate_per_kg = models.DecimalField(max_digits=8, decimal_places=2, default=25.00, help_text="Manager-set freight rate per kg in KES")
    base_handling_fee = models.DecimalField(max_digits=8, decimal_places=2, default=500.00, help_text="Base handling/stowage fee in KES")

    # Perishable-specific attributes
    requires_refrigeration = models.BooleanField(default=False)
    min_temp_celsius = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="e.g. 2.0°C")
    max_temp_celsius = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True, help_text="e.g. 6.0°C")
    spoilage_risk = models.CharField(max_length=20, choices=SpoilageRisk.choices, default=SpoilageRisk.LOW)
    shelf_life_days = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum transit days before degradation")
    humidity_requirement = models.CharField(max_length=50, blank=True, help_text="e.g. 85-90% RH")

    # Non-perishable attributes
    is_fragile = models.BooleanField(default=False, help_text="Requires gentle handling")
    is_hazardous = models.BooleanField(default=False, help_text="Flammable / chemical / Hazmat")
    stackable = models.BooleanField(default=True, help_text="Can be stacked in vehicle")
    handling_instructions = models.CharField(max_length=255, blank=True, help_text="e.g. This Side Up, Keep Dry")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def is_perishable(self):
        return self.category == ProductCategory.PERISHABLE

    def __str__(self):
        prefix = "❄️ [PERISHABLE]" if self.is_perishable else "📦 [NON-PERISHABLE]"
        return f"{prefix} {self.name} ({self.sku})"

class Shipment(models.Model):
    tracking_number = models.CharField(max_length=40, unique=True, db_index=True)
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_shipments',
        limit_choices_to={'role': 'CLIENT'}
    )
    assigned_driver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='driver_shipments',
        limit_choices_to={'role': 'DRIVER'}
    )
    assigned_porter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='porter_shipments',
        limit_choices_to={'role': 'PORTER'}
    )
    
    origin = models.CharField(max_length=120, default='Nairobi Central Terminal')
    destination = models.CharField(max_length=120, default='Mombasa Port Logistics Hub')
    origin_hub = models.ForeignKey(TransitHub, on_delete=models.SET_NULL, null=True, blank=True, related_name='origin_shipments')
    destination_hub = models.ForeignKey(TransitHub, on_delete=models.SET_NULL, null=True, blank=True, related_name='destination_shipments')
    
    current_location = models.CharField(max_length=150, default='Nairobi Terminal A')
    status = models.CharField(
        max_length=30,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.BOOKED
    )
    
    vehicle_plate = models.CharField(max_length=30, blank=True, null=True, help_text="e.g. KDF 789M")
    driver_notes = models.TextField(blank=True, help_text="Driver transit log notes")
    porter_notes = models.TextField(blank=True, help_text="Porter handling & loading remarks")
    
    # Financials
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=2500.00, help_text="Amount in KES")
    is_paid = models.BooleanField(default=False)
    
    # Timestamps
    departure_time = models.DateTimeField(null=True, blank=True)
    estimated_arrival = models.DateTimeField(null=True, blank=True)
    actual_arrival = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def has_perishable_items(self):
        return self.items.filter(product__category=ProductCategory.PERISHABLE).exists()

    @property
    def perishable_items_count(self):
        return self.items.filter(product__category=ProductCategory.PERISHABLE).count()

    @property
    def non_perishable_items_count(self):
        return self.items.filter(product__category=ProductCategory.NON_PERISHABLE).count()

    @property
    def total_weight_kg(self):
        total = sum(item.total_weight for item in self.items.all())
        return round(total, 2)

    def calculate_recommended_fee(self):
        """Calculates recommended delivery fee based on manager rates for cargo goods"""
        total = Decimal('0.00')
        for item in self.items.all():
            prod = item.product
            rate = getattr(prod, 'shipping_rate_per_kg', Decimal('25.00'))
            base = getattr(prod, 'base_handling_fee', Decimal('500.00'))
            weight = Decimal(str(item.total_weight))
            total += (weight * rate) + base
            if prod.is_perishable:
                total += Decimal('800.00')  # Cold-chain refrigeration surcharge
        return max(total, Decimal('1500.00'))

    @property
    def status_badge_class(self):
        badges = {
            ShipmentStatus.BOOKED: 'bg-blue-100 text-blue-800 border-blue-200',
            ShipmentStatus.RECEIVED_AT_HUB: 'bg-indigo-100 text-indigo-800 border-indigo-200',
            ShipmentStatus.LOADING: 'bg-amber-100 text-amber-800 border-amber-200',
            ShipmentStatus.IN_TRANSIT: 'bg-cyan-100 text-cyan-800 border-cyan-200',
            ShipmentStatus.AT_CHECKPOINT: 'bg-purple-100 text-purple-800 border-purple-200',
            ShipmentStatus.ARRIVED_DESTINATION: 'bg-teal-100 text-teal-800 border-teal-200',
            ShipmentStatus.OUT_FOR_DELIVERY: 'bg-orange-100 text-orange-800 border-orange-200',
            ShipmentStatus.DELIVERED: 'bg-emerald-100 text-emerald-800 border-emerald-200',
            ShipmentStatus.DELAYED: 'bg-rose-100 text-rose-800 border-rose-200',
            ShipmentStatus.TEMP_ALERT: 'bg-red-200 text-red-900 border-red-300 animate-pulse',
            ShipmentStatus.CANCELLED: 'bg-gray-100 text-gray-800 border-gray-200',
        }
        return badges.get(self.status, 'bg-gray-100 text-gray-800 border-gray-200')

    def __str__(self):
        category_tag = "❄️ Perishable" if self.has_perishable_items else "📦 Standard"
        return f"{self.tracking_number} [{category_tag}] - {self.origin} → {self.destination} ({self.get_status_display()})"

class ShipmentItem(models.Model):
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='shipment_items')
    quantity = models.PositiveIntegerField(default=1)
    package_type = models.CharField(
        max_length=50,
        choices=[
            ('CRATE_CHILLED', 'Refrigerated Thermal Crate'),
            ('PALLET', 'Standard Wooden Pallet'),
            ('CARTON', 'Corrugated Carton Box'),
            ('BARREL', 'Sealed Drum / Barrel'),
            ('SACK', 'Moisture-proof Sack'),
        ],
        default='CARTON'
    )
    notes = models.CharField(max_length=200, blank=True)

    @property
    def total_weight(self):
        return self.quantity * float(self.product.unit_weight_kg)

    def __str__(self):
        return f"{self.quantity}x {self.product.name} in {self.shipment.tracking_number}"

class TransitEvent(models.Model):
    EVENT_TYPES = [
        ('CHECKIN', 'Porter Cargo Check-in & Inspection'),
        ('TEMP_LOG', 'Temperature & Cold-Chain Reading'),
        ('LOADED', 'Cargo Loaded onto Vehicle'),
        ('DEPARTURE', 'Vehicle Departed Transit Hub'),
        ('CHECKPOINT', 'Highway Checkpoint Verification'),
        ('DELAY_REPORT', 'Transit Delay Incident'),
        ('UNLOADED', 'Cargo Unloaded at Destination'),
        ('DELIVERY_CONFIRMED', 'Delivered & Consignee Signed'),
    ]

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='transit_events')
    logged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES, default='CHECKPOINT')
    location = models.CharField(max_length=150)
    temperature_celsius = models.DecimalField(
        max_digits=5, decimal_places=1, null=True, blank=True,
        help_text="Crucial for perishable items - triggers alerts if out of bounds"
    )
    is_temp_breach = models.BooleanField(default=False)
    cargo_condition = models.CharField(
        max_length=30,
        choices=[
            ('OPTIMAL', 'Optimal / Pristine Condition'),
            ('ACCEPTABLE', 'Acceptable Transit Condition'),
            ('MINOR_ISSUE', 'Minor Packaging Wear'),
            ('CRITICAL_DAMAGE', 'Cargo Damage / Temperature Breach'),
        ],
        default='OPTIMAL'
    )
    seal_intact = models.BooleanField(default=True)
    remarks = models.TextField(blank=True)
    timestamp = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-timestamp']

    def save(self, *args, **kwargs):
        # Auto-detect perishable temperature breach if reading provided
        if self.temperature_celsius is not None and self.shipment.has_perishable_items:
            for item in self.shipment.items.filter(product__category=ProductCategory.PERISHABLE):
                min_t = item.product.min_temp_celsius
                max_t = item.product.max_temp_celsius
                if (min_t is not None and self.temperature_celsius < min_t) or \
                   (max_t is not None and self.temperature_celsius > max_t):
                    self.is_temp_breach = True
                    self.cargo_condition = 'CRITICAL_DAMAGE'
                    # Optionally flag shipment status
                    self.shipment.status = ShipmentStatus.TEMP_ALERT
                    self.shipment.save()
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_event_type_display()} at {self.location} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
