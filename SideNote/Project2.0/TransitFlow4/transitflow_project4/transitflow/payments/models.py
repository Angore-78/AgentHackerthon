from django.db import models
from django.conf import settings
from logistics.models import Shipment
from decimal import Decimal
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
    CREDIT_BALANCE = 'CREDIT_BALANCE', 'TransitFlow Client Credit Balance'

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
        config, created = cls.objects.get_or_create(id=1)

        # Check if settings or .secrets contains live credentials
        api_token = getattr(settings, 'PAYHERO_API_TOKEN', None)
        channel_id = getattr(settings, 'PAYHERO_CHANNEL_ID', None)
        username = getattr(settings, 'PAYHERO_API_USERNAME', None)
        password = getattr(settings, 'PAYHERO_API_PASSWORD', None)

        if not api_token:
            secrets_file = settings.BASE_DIR / '.secrets'
            if secrets_file.exists():
                import base64
                try:
                    with open(secrets_file, 'r') as f:
                        for line in f:
                            line = line.strip()
                            if not line or line.startswith('#') or '=' not in line:
                                continue
                            k, v = line.split('=', 1)
                            k, v = k.strip(), v.strip()
                            if k == 'API_Token':
                                api_token = v
                                raw_b64 = v.replace('Basic ', '').strip()
                                try:
                                    decoded = base64.b64decode(raw_b64).decode('utf-8')
                                    if ':' in decoded:
                                        username, password = decoded.split(':', 1)
                                except Exception:
                                    pass
                            elif k == 'ChannelID':
                                channel_id = v
                except Exception:
                    pass

        updated = False
        if username and password and (config.api_username != username or config.api_password != password):
            config.api_username = username
            config.api_password = password
            updated = True

        if channel_id and config.channel_id != channel_id:
            config.channel_id = channel_id
            updated = True

        if (api_token or username) and config.environment != 'LIVE':
            config.environment = 'LIVE'
            updated = True

        if updated or created:
            config.save()

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
    
    # Failure & Compensatory Credit Tracking
    failure_reason = models.CharField(max_length=255, blank=True, null=True, help_text="Specific failure reason")
    is_credited = models.BooleanField(default=False, help_text="True if client was credited compensatory funds upon failure")
    credited_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Credit balance added to client")

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

    def mark_as_failed(self, reason=None, callback_data=None):
        """
        Marks transaction as failed, records reason, and immediately
        credits the client account balance if not already credited.
        """
        self.status = PaymentStatus.FAILED
        if reason:
            self.failure_reason = reason
        if callback_data:
            self.callback_payload = str(callback_data)
            
        if not self.is_credited and self.amount > 0:
            client = self.client
            current_bal = client.credit_balance or Decimal('0.00')
            client.credit_balance = current_bal + self.amount
            client.save(update_fields=['credit_balance'])
            self.is_credited = True
            self.credited_amount = self.amount
            
            # Log credit audit record
            ClientCreditLog.objects.create(
                client=client,
                transaction=self,
                amount=self.amount,
                balance_after=client.credit_balance,
                action_type=CreditActionType.CREDIT,
                reason=f"Compensatory credit for failed transaction {self.reference}: {reason or 'Payment gateway failure'}"
            )
        self.save()

    def __str__(self):
        return f"{self.reference} - {self.currency} {self.amount} ({self.get_status_display()})"


class CreditActionType(models.TextChoices):
    CREDIT = 'CREDIT', 'Compensatory Credit Added'
    DEBIT = 'DEBIT', 'Credit Deducted for Shipment Settlement'

class ClientCreditLog(models.Model):
    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='credit_logs')
    transaction = models.ForeignKey('PaymentTransaction', on_delete=models.SET_NULL, null=True, blank=True, related_name='credit_logs')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    action_type = models.CharField(max_length=10, choices=CreditActionType.choices, default=CreditActionType.CREDIT)
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.client.username} - {self.action_type} KES {self.amount} (Balance: {self.balance_after})"
