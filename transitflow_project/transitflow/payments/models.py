from django.db import models
from django.conf import settings
from logistics.models import Shipment
import uuid

class PaymentStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Payment'
    SUCCESS = 'SUCCESS', 'Payment Completed (Confirmed)'
    FAILED = 'FAILED', 'Payment Failed'
    CANCELLED = 'CANCELLED', 'Cancelled'

class PaymentMethod(models.TextChoices):
    LIPWA_LINK = 'LIPWA_LINK', 'PayHero Lipwa Link (Direct Checkout)'
    STK_PUSH = 'STK_PUSH', 'PayHero M-Pesa STK Push'
    PAYBILL = 'PAYBILL', 'PayHero Paybill Channel'
    TILL = 'TILL', 'PayHero Buy Goods Till'

class PayHeroConfig(models.Model):
    ENVIRONMENT_CHOICES = [
        ('SANDBOX', 'Sandbox / Simulation Mode'),
        ('LIVE', 'Live Production (backend.payhero.co.ke)'),
    ]

    api_username = models.CharField(
        max_length=150,
        default='transitflow_demo_user',
        help_text="PayHero API Username (Basic Auth)"
    )
    api_password = models.CharField(
        max_length=255,
        default='transitflow_demo_secret_key',
        help_text="PayHero API Password / Secret"
    )
    channel_id = models.CharField(
        max_length=50,
        default='133',
        help_text="PayHero Channel ID (Associated Till, Paybill, or Disbursal Channel)"
    )
    lipwa_link_slug = models.CharField(
        max_length=100,
        default='transitflow',
        help_text="PayHero Lipwa Link Identifier (e.g. lipwa.link/transitflow)"
    )
    environment = models.CharField(
        max_length=20,
        choices=ENVIRONMENT_CHOICES,
        default='SANDBOX',
        help_text="Switch between Live PayHero endpoints and instant Mock Simulation"
    )
    callback_url = models.URLField(
        blank=True,
        default='https://transitflow.ke/payments/callback/',
        help_text="Webhook endpoint receiving instantaneous transaction updates from PayHero"
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'PayHero Configuration'
        verbose_name_plural = 'PayHero Configurations'

    @classmethod
    def get_config(cls):
        config, _ = cls.objects.get_or_create(id=1)
        return config

    def __str__(self):
        return f"PayHero Config [{self.environment}] - Channel #{self.channel_id}"

class PaymentTransaction(models.Model):
    reference = models.CharField(max_length=60, unique=True, db_index=True)
    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name='payments')
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='client_payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='KES')
    phone_number = models.CharField(max_length=25, help_text="e.g. 0712345678 or 254712345678")
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices, default=PaymentMethod.LIPWA_LINK)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    
    # PayHero identifiers
    payhero_reference = models.CharField(max_length=100, blank=True, null=True)
    mpesa_receipt = models.CharField(max_length=50, blank=True, null=True, help_text="M-Pesa Transaction Code")
    lipwa_link_url = models.TextField(blank=True, help_text="Full generated Lipwa Link checkout URL")
    
    # Audit payloads
    request_payload = models.TextField(blank=True, null=True)
    response_payload = models.TextField(blank=True, null=True)
    callback_payload = models.TextField(blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def status_badge_class(self):
        badges = {
            PaymentStatus.SUCCESS: 'bg-emerald-100 text-emerald-800 border-emerald-200',
            PaymentStatus.PENDING: 'bg-amber-100 text-amber-800 border-amber-200',
            PaymentStatus.FAILED: 'bg-red-100 text-red-800 border-red-200',
            PaymentStatus.CANCELLED: 'bg-gray-100 text-gray-800 border-gray-200',
        }
        return badges.get(self.status, 'bg-gray-100 text-gray-800 border-gray-200')

    def mark_as_paid(self, mpesa_receipt=None, callback_data=None):
        self.status = PaymentStatus.SUCCESS
        if mpesa_receipt:
            self.mpesa_receipt = mpesa_receipt
        if callback_data:
            self.callback_payload = str(callback_data)
        self.save()
        
        # Automatically update the associated shipment
        self.shipment.is_paid = True
        self.shipment.save()

    def __str__(self):
        return f"{self.reference} - {self.currency} {self.amount} ({self.get_status_display()})"
