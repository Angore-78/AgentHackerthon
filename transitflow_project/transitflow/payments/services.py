import requests
import json
import base64
import uuid
from decimal import Decimal
from urllib.parse import urlencode
from django.conf import settings
from .models import PayHeroConfig, PaymentTransaction, PaymentStatus, PaymentMethod

class PayHeroService:
    BASE_URL = "https://backend.payhero.co.ke"

    @classmethod
    def get_config(cls):
        return PayHeroConfig.get_config()

    @classmethod
    def format_phone_number(cls, phone):
        """Standardize phone format to e.g. 07XXXXXXXX or 254XXXXXXXXX"""
        if not phone:
            return "0700000000"
        phone = phone.strip().replace(" ", "").replace("+", "")
        if phone.startswith("254") and len(phone) == 12:
            return phone
        elif phone.startswith("0") and len(phone) == 10:
            return "254" + phone[1:]
        elif len(phone) == 9:
            return "254" + phone
        return phone

    @classmethod
    def generate_lipwa_link(cls, shipment, client, phone_number, amount, request=None):
        """
        Constructs a dynamic PayHero Lipwa Link with pre-filled query parameters.
        Format:
        https://lipwa.link/{slug}?amount=X&phone=Y&name=Z&channel_id=C&reference=R&success_url=S&failed_url=F
        """
        config = cls.get_config()
        clean_phone = cls.format_phone_number(phone_number)
        tx_ref = f"PAY-TF-{uuid.uuid4().hex[:8].upper()}"
        
        # Base URLs for callback/redirect
        host = request.get_host() if request else "localhost:8000"
        protocol = "https" if request and request.is_secure() else "http"
        success_url = f"{protocol}://{host}/payments/success/?ref={tx_ref}"
        failed_url = f"{protocol}://{host}/payments/failed/?ref={tx_ref}"
        
        query_params = {
            'amount': str(int(amount)),
            'phone': clean_phone,
            'name': client.get_full_name() or client.username,
            'channel_id': config.channel_id,
            'reference': tx_ref,
            'success_url': success_url,
            'failed_url': failed_url,
        }
        
        encoded_query = urlencode(query_params)
        lipwa_url = f"https://lipwa.link/{config.lipwa_link_slug}?{encoded_query}"
        
        # Create pending PaymentTransaction record
        transaction = PaymentTransaction.objects.create(
            reference=tx_ref,
            shipment=shipment,
            client=client,
            amount=Decimal(amount),
            currency='KES',
            phone_number=clean_phone,
            payment_method=PaymentMethod.LIPWA_LINK,
            status=PaymentStatus.PENDING,
            lipwa_link_url=lipwa_url,
            request_payload=json.dumps(query_params)
        )
        
        return {
            'transaction': transaction,
            'lipwa_url': lipwa_url,
            'reference': tx_ref
        }

    @classmethod
    def initiate_stk_push(cls, shipment, client, phone_number, amount, request=None):
        """
        Sends programmatic request to POST /api/v2/payments on PayHero backend
        with Basic Auth header.
        """
        config = cls.get_config()
        clean_phone = cls.format_phone_number(phone_number)
        tx_ref = f"STK-TF-{uuid.uuid4().hex[:8].upper()}"
        
        host = request.get_host() if request else "localhost:8000"
        protocol = "https" if request and request.is_secure() else "http"
        callback_url = config.callback_url or f"{protocol}://{host}/payments/callback/"
        
        payload = {
            "amount": int(amount),
            "phone_number": clean_phone,
            "channel_id": int(config.channel_id) if config.channel_id.isdigit() else 133,
            "provider": "m-pesa",
            "external_reference": tx_ref,
            "callback_url": callback_url
        }
        
        transaction = PaymentTransaction.objects.create(
            reference=tx_ref,
            shipment=shipment,
            client=client,
            amount=Decimal(amount),
            currency='KES',
            phone_number=clean_phone,
            payment_method=PaymentMethod.STK_PUSH,
            status=PaymentStatus.PENDING,
            request_payload=json.dumps(payload)
        )
        
        if config.environment == 'SANDBOX':
            # Simulated immediate response for testing
            mock_response = {
                "status": "Success",
                "message": "STK prompt initiated successfully in Sandbox mode. Please enter PIN on device or use the test simulator.",
                "reference": f"MOCK-PH-{uuid.uuid4().hex[:10].upper()}",
                "Success": True
            }
            transaction.payhero_reference = mock_response["reference"]
            transaction.response_payload = json.dumps(mock_response)
            transaction.save()
            return {
                "success": True,
                "transaction": transaction,
                "message": mock_response["message"],
                "is_sandbox": True
            }
        
        # Production Live Request
        try:
            auth_str = f"{config.api_username}:{config.api_password}"
            b64_auth = base64.b64encode(auth_str.encode()).decode()
            headers = {
                "Authorization": f"Basic {b64_auth}",
                "Content-Type": "application/json"
            }
            
            resp = requests.post(
                f"{cls.BASE_URL}/api/v2/payments",
                json=payload,
                headers=headers,
                timeout=15
            )
            data = resp.json() if resp.status_code == 200 else {}
            
            transaction.response_payload = resp.text
            if resp.status_code in [200, 201]:
                transaction.payhero_reference = data.get("reference") or data.get("checkout_id", "")
                transaction.save()
                return {
                    "success": True,
                    "transaction": transaction,
                    "message": "Payment prompt sent to mobile device.",
                    "data": data
                }
            else:
                transaction.status = PaymentStatus.FAILED
                transaction.save()
                return {
                    "success": False,
                    "transaction": transaction,
                    "message": data.get("message", f"PayHero Error {resp.status_code}")
                }
        except Exception as e:
            transaction.status = PaymentStatus.FAILED
            transaction.response_payload = str(e)
            transaction.save()
            return {
                "success": False,
                "transaction": transaction,
                "message": f"Connection error: {str(e)}"
            }
