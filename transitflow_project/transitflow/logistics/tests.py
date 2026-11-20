from django.test import TestCase, Client
from django.urls import reverse
from decimal import Decimal
from core.models import User, UserRole
from logistics.models import Product, ProductCategory, Shipment, ShipmentItem, ShipmentStatus, TransitEvent
from payments.models import PayHeroConfig, PaymentTransaction, PaymentStatus, PaymentMethod
from payments.services import PayHeroService
from assistant.chatbot import TransitChatbot

class TransitFlowTestCase(TestCase):
    def setUp(self):
        # Users
        self.manager = User.objects.create_user(username='m_alice', password='pass', role=UserRole.MANAGER)
        self.porter = User.objects.create_user(username='p_brian', password='pass', role=UserRole.PORTER)
        self.driver = User.objects.create_user(username='d_david', password='pass', role=UserRole.DRIVER, vehicle_plate='KDF 123Z')
        self.client1 = User.objects.create_user(username='c_cynthia', password='pass', role=UserRole.CLIENT, phone_number='0711111111')
        self.client2 = User.objects.create_user(username='c_bob', password='pass', role=UserRole.CLIENT, phone_number='0722222222')

        # Products
        self.perishable_prod = Product.objects.create(
            name='Fresh Mangoes',
            sku='PER-MNG-01',
            category=ProductCategory.PERISHABLE,
            min_temp_celsius=Decimal('4.0'),
            max_temp_celsius=Decimal('8.0'),
            requires_refrigeration=True
        )
        self.non_perishable_prod = Product.objects.create(
            name='Steel Bolts',
            sku='NON-STL-01',
            category=ProductCategory.NON_PERISHABLE,
            is_fragile=False
        )

        # Shipments
        self.shipment1 = Shipment.objects.create(
            tracking_number='TF-TEST-001',
            client=self.client1,
            assigned_driver=self.driver,
            assigned_porter=self.porter,
            origin='Nairobi',
            destination='Mombasa',
            current_location='Nairobi ICD',
            status=ShipmentStatus.BOOKED,
            delivery_fee=Decimal('3000.00'),
            is_paid=False
        )
        ShipmentItem.objects.create(shipment=self.shipment1, product=self.perishable_prod, quantity=10)

        self.shipment2 = Shipment.objects.create(
            tracking_number='TF-TEST-002',
            client=self.client2,
            assigned_driver=self.driver,
            origin='Kisumu',
            destination='Nairobi',
            status=ShipmentStatus.IN_TRANSIT,
            delivery_fee=Decimal('2500.00'),
            is_paid=True
        )
        ShipmentItem.objects.create(shipment=self.shipment2, product=self.non_perishable_prod, quantity=50)

    # 1. Product separation tests
    def test_perishable_separation(self):
        self.assertTrue(self.perishable_prod.is_perishable)
        self.assertFalse(self.non_perishable_prod.is_perishable)
        self.assertTrue(self.shipment1.has_perishable_items)
        self.assertFalse(self.shipment2.has_perishable_items)

    # 2. Temperature breach alert test
    def test_temperature_breach_alert(self):
        # Allowed range: 4.0°C to 8.0°C. Reading 12.0°C should trigger alert!
        event = TransitEvent.objects.create(
            shipment=self.shipment1,
            logged_by=self.driver,
            event_type='TEMP_LOG',
            location='Athi River',
            temperature_celsius=Decimal('12.0')
        )
        self.assertTrue(event.is_temp_breach)
        self.shipment1.refresh_from_db()
        self.assertEqual(self.shipment1.status, ShipmentStatus.TEMP_ALERT)

    # 3. Portal Isolation and Role Middleware Guards
    def test_role_portal_isolation(self):
        c = Client()
        # Client tries to access Manager dashboard -> should be redirected
        c.login(username='c_cynthia', password='pass')
        resp = c.get(reverse('manager_dashboard'), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/portal/client/', resp.url)

        # Driver tries to access Manager dashboard -> redirected
        c.login(username='d_david', password='pass')
        resp2 = c.get(reverse('manager_dashboard'), follow=False)
        self.assertEqual(resp2.status_code, 302)
        self.assertIn('/portal/driver/', resp2.url)

    # 4. Privilege-Scoped Chatbot Tests
    def test_chatbot_privileges(self):
        # Client asking about own shipment -> Allowed
        res = TransitChatbot.process_query(self.client1, "What is the status of TF-TEST-001?")
        self.assertIn("TF-TEST-001", res["reply"])
        self.assertIn("Fresh Mangoes", res["reply"])

        # Client asking about another client's shipment -> Blocked
        res_blocked = TransitChatbot.process_query(self.client1, "What is the status of TF-TEST-002?")
        self.assertIn("Access Restricted", res_blocked["reply"])

        # Driver asking about assigned cargo -> Allowed
        res_driver = TransitChatbot.process_query(self.driver, "What cargo am I transporting?")
        self.assertIn("Assigned Cargo", res_driver["reply"])

        # Manager asking about system overview -> Full clearance
        res_mgr = TransitChatbot.process_query(self.manager, "Overview of fleet")
        self.assertIn("Executive Summary", res_mgr["reply"])

    # 5. PayHero Lipwa Link Generation & Callback
    def test_payhero_lipwa_link_and_callback(self):
        result = PayHeroService.generate_lipwa_link(
            shipment=self.shipment1,
            client=self.client1,
            phone_number='0711111111',
            amount=Decimal('3000.00')
        )
        self.assertIn('https://lipwa.link/transitflow?', result['lipwa_url'])
        self.assertIn('amount=3000', result['lipwa_url'])
        self.assertIn('reference=', result['lipwa_url'])

        # Simulate callback processing
        tx = result['transaction']
        tx.mark_as_paid(mpesa_receipt='TEST_MPESA_REC')
        self.assertEqual(tx.status, PaymentStatus.SUCCESS)
        self.shipment1.refresh_from_db()
        self.assertTrue(self.shipment1.is_paid)
