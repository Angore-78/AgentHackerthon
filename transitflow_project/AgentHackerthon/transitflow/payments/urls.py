from django.urls import path
from . import views

urlpatterns = [
    path('', views.payments_index, name='payments_index'),
    path('initiate/<str:tracking_number>/', views.initiate_payment, name='initiate_payment'),
    path('detail/<str:reference>/', views.payment_detail, name='payment_detail'),
    path('callback/', views.payhero_callback, name='payhero_callback'),
    path('simulate/<str:reference>/', views.simulate_payment_success, name='simulate_payment'),
    path('configure/', views.configure_payhero, name='configure_payhero'),
    path('howto/', views.payhero_howto, name='payhero_howto'),
]
