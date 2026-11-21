from django.urls import path
from . import views

urlpatterns = [
    path('', views.payments_index, name='payments_index'),
    path('initiate/<str:tracking_number>/', views.initiate_payment, name='initiate_payment'),
    path('pay-credit/<str:tracking_number>/', views.pay_with_credit, name='pay_with_credit'),
    path('detail/<str:reference>/', views.payment_detail, name='payment_detail'),
    path('callback/', views.payhero_callback, name='payhero_callback'),
    path('success/', views.payment_success_landing, name='payment_success_landing'),
    path('failed/', views.payment_failed_landing, name='payment_failed_landing'),
    path('simulate/<str:reference>/', views.simulate_payment_success, name='simulate_payment'),
    path('simulate-fail/<str:reference>/', views.simulate_payment_failure, name='simulate_payment_failure'),
    path('configure/', views.configure_payhero, name='configure_payhero'),
]
