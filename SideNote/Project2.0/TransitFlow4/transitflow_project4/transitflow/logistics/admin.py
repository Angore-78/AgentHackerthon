from django.contrib import admin
from .models import TransitHub, Product, Shipment, ShipmentItem, TransitEvent

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'shipping_rate_per_kg', 'base_handling_fee', 'unit_weight_kg', 'declared_value')
    list_filter = ('category', 'requires_refrigeration', 'spoilage_risk')
    search_fields = ('name', 'sku')

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('tracking_number', 'client', 'status', 'origin', 'destination', 'delivery_fee', 'is_paid')
    list_filter = ('status', 'is_paid')
    search_fields = ('tracking_number', 'client__username')

admin.site.register(TransitHub)
admin.site.register(ShipmentItem)
admin.site.register(TransitEvent)
