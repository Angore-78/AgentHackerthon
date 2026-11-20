import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'transitflow_project.settings')
django.setup()

from decimal import Decimal
from django.utils import timezone
from core.models import User, UserRole
from logistics.models import (
    TransitHub, Product, ProductCategory, SpoilageRisk,
    Shipment, ShipmentItem, ShipmentStatus, TransitEvent
)
from payments.models import PayHeroConfig, PaymentTransaction, PaymentStatus, PaymentMethod

def seed():
    print("🌱 Seeding TransitFlow demonstration data...")

    # 1. Create Users
    admin_user, _ = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@transitflow.ke',
            'first_name': 'System',
            'last_name': 'Administrator',
            'role': UserRole.MANAGER,
            'is_staff': True,
            'is_superuser': True
        }
    )
    admin_user.set_password('admin123')
    admin_user.save()

    manager, _ = User.objects.get_or_create(
        username='manager_alice',
        defaults={
            'email': 'alice@transitflow.ke',
            'first_name': 'Alice',
            'last_name': 'Wanjiku',
            'role': UserRole.MANAGER,
            'phone_number': '+254711000001',
            'company_name': 'TransitFlow Logistics HQ'
        }
    )
    manager.set_password('password123')
    manager.save()

    porter, _ = User.objects.get_or_create(
        username='porter_brian',
        defaults={
            'email': 'brian@transitflow.ke',
            'first_name': 'Brian',
            'last_name': 'Otieno',
            'role': UserRole.PORTER,
            'phone_number': '+254722000002',
            'assigned_hub_name': 'Nairobi Central ICD - Cold Bay 3'
        }
    )
    porter.set_password('password123')
    porter.save()

    driver, _ = User.objects.get_or_create(
        username='driver_david',
        defaults={
            'email': 'david@transitflow.ke',
            'first_name': 'David',
            'last_name': 'Kiprono',
            'role': UserRole.DRIVER,
            'phone_number': '+254733000003',
            'vehicle_plate': 'KDF 420X (Reefer Box-Truck)'
        }
    )
    driver.set_password('password123')
    driver.save()

    client, _ = User.objects.get_or_create(
        username='client_cynthia',
        defaults={
            'email': 'cynthia@savannahproduce.co.ke',
            'first_name': 'Cynthia',
            'last_name': 'Moraa',
            'role': UserRole.CLIENT,
            'phone_number': '0712345678',
            'company_name': 'Savannah Fresh Exporters Ltd'
        }
    )
    client.set_password('password123')
    client.save()

    print("✅ Users created (Passwords: password123 / admin: admin123)")

    # 2. Transit Hubs
    hub_nbi, _ = TransitHub.objects.get_or_create(
        code='HUB-NBI-01',
        defaults={'name': 'Nairobi Central ICD', 'city': 'Nairobi', 'hub_type': 'CENTRAL_DEPOT', 'has_cold_storage': True}
    )
    hub_msa, _ = TransitHub.objects.get_or_create(
        code='HUB-MSA-01',
        defaults={'name': 'Mombasa Port Cold-Storage Terminal', 'city': 'Mombasa', 'hub_type': 'COLD_STORAGE_HUB', 'has_cold_storage': True}
    )
    hub_nv, _ = TransitHub.objects.get_or_create(
        code='HUB-NAI-02',
        defaults={'name': 'Naivasha Industrial Depot', 'city': 'Naivasha', 'hub_type': 'DISTRIBUTION_CENTER', 'has_cold_storage': True}
    )

    # 3. Products: Perishable vs Non-Perishable
    # Perishable Products
    prod_avocado, _ = Product.objects.get_or_create(
        sku='PER-AVO-01',
        defaults={
            'name': 'Fresh Hass Export Avocados',
            'category': ProductCategory.PERISHABLE,
            'description': 'Export-grade Hass avocados in ventilated thermal crates.',
            'unit_weight_kg': Decimal('4.5'),
            'declared_value': Decimal('120000.00'),
            'requires_refrigeration': True,
            'min_temp_celsius': Decimal('2.0'),
            'max_temp_celsius': Decimal('6.0'),
            'spoilage_risk': SpoilageRisk.MEDIUM,
            'shelf_life_days': 16,
            'humidity_requirement': '85-90% RH'
        }
    )

    prod_milk, _ = Product.objects.get_or_create(
        sku='PER-MLK-02',
        defaults={
            'name': 'Grade-A Fresh Dairy Pasteurized Milk',
            'category': ProductCategory.PERISHABLE,
            'description': 'Bottled fresh whole milk. Strict continuous chilling required.',
            'unit_weight_kg': Decimal('12.0'),
            'declared_value': Decimal('85000.00'),
            'requires_refrigeration': True,
            'min_temp_celsius': Decimal('1.0'),
            'max_temp_celsius': Decimal('4.0'),
            'spoilage_risk': SpoilageRisk.CRITICAL,
            'shelf_life_days': 5,
            'humidity_requirement': 'Standard Chilled'
        }
    )

    prod_roses, _ = Product.objects.get_or_create(
        sku='PER-ROS-03',
        defaults={
            'name': 'Naivasha Highland Export Cut Roses',
            'category': ProductCategory.PERISHABLE,
            'description': 'Stemmed red and white roses for air-freight export via Mombasa/Nairobi.',
            'unit_weight_kg': Decimal('2.0'),
            'declared_value': Decimal('250000.00'),
            'requires_refrigeration': True,
            'min_temp_celsius': Decimal('2.0'),
            'max_temp_celsius': Decimal('5.0'),
            'spoilage_risk': SpoilageRisk.HIGH,
            'shelf_life_days': 7,
            'humidity_requirement': '90-95% RH'
        }
    )

    # Non-Perishable Products
    prod_solar, _ = Product.objects.get_or_create(
        sku='NON-SOL-01',
        defaults={
            'name': 'Solar Inverters & Lithium Iron Battery Modules',
            'category': ProductCategory.NON_PERISHABLE,
            'description': 'High-density lithium storage modules. Delicate electronics.',
            'unit_weight_kg': Decimal('48.0'),
            'declared_value': Decimal('450000.00'),
            'is_fragile': True,
            'is_hazardous': True,
            'stackable': False,
            'handling_instructions': 'Handle with Care. Do not expose to moisture. Keep upright.'
        }
    )

    prod_machinery, _ = Product.objects.get_or_create(
        sku='NON-MAC-02',
        defaults={
            'name': 'Heavy Excavator Hydraulic Pump Assemblies',
            'category': ProductCategory.NON_PERISHABLE,
            'description': 'Cast iron precision hydraulic pump units for mining machinery.',
            'unit_weight_kg': Decimal('75.0'),
            'declared_value': Decimal('320000.00'),
            'is_fragile': False,
            'is_hazardous': False,
            'stackable': True,
            'handling_instructions': 'Standard floor pallet strapping. Keep dry.'
        }
    )

    print("✅ Products catalog created (Perishable & Non-Perishable)")

    # 4. Shipments
    # Shipment 1: In Transit Perishable (Normal cold-chain)
    s1, _ = Shipment.objects.get_or_create(
        tracking_number='TF-2026-NBI-001',
        defaults={
            'client': client,
            'assigned_driver': driver,
            'assigned_porter': porter,
            'origin': 'Nairobi Central ICD',
            'destination': 'Mombasa Port Cold-Storage Terminal',
            'current_location': 'Mtito Andei Highway Checkpoint',
            'status': ShipmentStatus.IN_TRANSIT,
            'vehicle_plate': 'KDF 420X (Reefer Truck)',
            'delivery_fee': Decimal('4500.00'),
            'is_paid': False,
            'departure_time': timezone.now() - timezone.timedelta(hours=5),
            'estimated_arrival': timezone.now() + timezone.timedelta(hours=3),
        }
    )
    ShipmentItem.objects.get_or_create(shipment=s1, product=prod_avocado, defaults={'quantity': 40, 'package_type': 'CRATE_CHILLED'})

    TransitEvent.objects.get_or_create(
        shipment=s1,
        event_type='CHECKIN',
        defaults={'logged_by': porter, 'location': 'Nairobi Central ICD', 'temperature_celsius': Decimal('3.5'), 'cargo_condition': 'OPTIMAL', 'remarks': 'Core temperature checked with infrared gun: 3.5°C.'}
    )
    TransitEvent.objects.get_or_create(
        shipment=s1,
        event_type='CHECKPOINT',
        defaults={'logged_by': driver, 'location': 'Mtito Andei Checkpoint', 'temperature_celsius': Decimal('3.8'), 'cargo_condition': 'OPTIMAL', 'remarks': 'Highway transit on schedule. Reefer running smoothly.'}
    )

    # Shipment 2: Perishable with Temperature Breach Alert!
    s2, _ = Shipment.objects.get_or_create(
        tracking_number='TF-2026-NBI-002',
        defaults={
            'client': client,
            'assigned_driver': driver,
            'assigned_porter': porter,
            'origin': 'Nairobi Central ICD',
            'destination': 'Voi Regional Distribution Center',
            'current_location': 'Salama Weighbridge Station',
            'status': ShipmentStatus.TEMP_ALERT,
            'vehicle_plate': 'KDF 420X (Reefer Truck)',
            'delivery_fee': Decimal('3200.00'),
            'is_paid': True,
            'departure_time': timezone.now() - timezone.timedelta(hours=4),
        }
    )
    ShipmentItem.objects.get_or_create(shipment=s2, product=prod_milk, defaults={'quantity': 25, 'package_type': 'CRATE_CHILLED'})

    TransitEvent.objects.get_or_create(
        shipment=s2,
        event_type='TEMP_LOG',
        defaults={'logged_by': driver, 'location': 'Salama Weighbridge Station', 'temperature_celsius': Decimal('8.5'), 'is_temp_breach': True, 'cargo_condition': 'CRITICAL_DAMAGE', 'remarks': 'Reefer compressor failure detected. Temperature spiked to 8.5°C (Limit: 4.0°C). Driver parked for roadside inspection.'}
    )

    # Shipment 3: Non-Perishable (Solar Inverters) - Paid
    s3, _ = Shipment.objects.get_or_create(
        tracking_number='TF-2026-NBI-003',
        defaults={
            'client': client,
            'assigned_driver': driver,
            'assigned_porter': porter,
            'origin': 'Nairobi Central ICD',
            'destination': 'Naivasha Geothermal Plant Substation',
            'current_location': 'Naivasha Industrial Depot',
            'status': ShipmentStatus.AT_CHECKPOINT,
            'vehicle_plate': 'KDF 420X',
            'delivery_fee': Decimal('5500.00'),
            'is_paid': True,
        }
    )
    ShipmentItem.objects.get_or_create(shipment=s3, product=prod_solar, defaults={'quantity': 6, 'package_type': 'PALLET'})

    # Shipment 4: Fresh Cut Roses awaiting departure at depot
    s4, _ = Shipment.objects.get_or_create(
        tracking_number='TF-2026-NBI-004',
        defaults={
            'client': client,
            'assigned_porter': porter,
            'origin': 'Naivasha Flower Depot',
            'destination': 'JKIA Nairobi Cargo Terminal',
            'current_location': 'Naivasha Cold Room Bay 2',
            'status': ShipmentStatus.RECEIVED_AT_HUB,
            'delivery_fee': Decimal('2800.00'),
            'is_paid': False,
        }
    )
    ShipmentItem.objects.get_or_create(shipment=s4, product=prod_roses, defaults={'quantity': 80, 'package_type': 'CRATE_CHILLED'})

    # Shipment 5: Non-Perishable Heavy Machinery - Delivered
    s5, _ = Shipment.objects.get_or_create(
        tracking_number='TF-2026-NBI-005',
        defaults={
            'client': client,
            'assigned_driver': driver,
            'origin': 'Mombasa Port Berth 5',
            'destination': 'Athi River Steel Works',
            'current_location': 'Athi River Steel Works Gate 3',
            'status': ShipmentStatus.DELIVERED,
            'vehicle_plate': 'KDF 420X',
            'delivery_fee': Decimal('8500.00'),
            'is_paid': True,
            'actual_arrival': timezone.now() - timezone.timedelta(hours=1),
        }
    )
    ShipmentItem.objects.get_or_create(shipment=s5, product=prod_machinery, defaults={'quantity': 4, 'package_type': 'PALLET'})

    print("✅ Shipments and items populated")

    # 5. PayHero Config & Sample Payment
    config = PayHeroConfig.get_config()
    config.api_username = "transitflow_demo_api"
    config.api_password = "demo_payhero_key_sec"
    config.channel_id = "133"
    config.lipwa_link_slug = "transitflow"
    config.environment = "SANDBOX"
    config.callback_url = "https://transitflow.ke/payments/callback/"
    config.save()

    # Create sample paid payment transaction for Shipment 3
    tx3, _ = PaymentTransaction.objects.get_or_create(
        reference='PAY-TF-DEMO-001',
        defaults={
            'shipment': s3,
            'client': client,
            'amount': Decimal('5500.00'),
            'currency': 'KES',
            'phone_number': '254712345678',
            'payment_method': PaymentMethod.LIPWA_LINK,
            'status': PaymentStatus.SUCCESS,
            'mpesa_receipt': 'QKB91823A4',
            'lipwa_link_url': 'https://lipwa.link/transitflow?amount=5500&phone=254712345678&reference=PAY-TF-DEMO-001&channel_id=133',
            'callback_payload': '{"status": "Success", "external_reference": "PAY-TF-DEMO-001", "amount": 5500, "MpesaReceiptNumber": "QKB91823A4"}'
        }
    )

    print("✅ PayHero configuration and demo transactions ready")
    print("\n🚀 Seeding finished successfully!")

if __name__ == '__main__':
    seed()
