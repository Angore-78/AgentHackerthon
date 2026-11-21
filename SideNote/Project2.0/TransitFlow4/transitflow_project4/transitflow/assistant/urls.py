from django.urls import path
from . import views

urlpatterns = [
    path('api/message/', views.chatbot_message_api, name='chatbot_message_api'),
    path('api/payment-status/<str:reference>/', views.check_payment_status_api, name='check_payment_status_api'),
]
