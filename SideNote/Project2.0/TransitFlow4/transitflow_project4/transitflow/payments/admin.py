from django.contrib import admin
from .models import PayHeroConfig, PaymentTransaction, ClientCreditLog

@admin.register(PayHeroConfig)
class PayHeroConfigAdmin(admin.ModelAdmin):
    list_display = ('id', 'environment', 'channel_id', 'lipwa_link_slug', 'updated_at')

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('reference', 'shipment', 'client', 'amount', 'status', 'payment_method', 'is_credited', 'credited_amount', 'created_at')
    list_filter = ('status', 'payment_method', 'is_credited')
    search_fields = ('reference', 'phone_number', 'mpesa_receipt', 'shipment__tracking_number')

@admin.register(ClientCreditLog)
class ClientCreditLogAdmin(admin.ModelAdmin):
    list_display = ('client', 'action_type', 'amount', 'balance_after', 'created_at', 'reason')
    list_filter = ('action_type',)
    search_fields = ('client__username', 'reason')
