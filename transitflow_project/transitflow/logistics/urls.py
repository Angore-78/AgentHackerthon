from django.urls import path
from . import views

urlpatterns = [
    # Role Portals
    path('portal/manager/', views.manager_dashboard, name='manager_dashboard'),
    path('portal/porter/', views.porter_dashboard, name='porter_dashboard'),
    path('portal/driver/', views.driver_dashboard, name='driver_dashboard'),
    path('portal/client/', views.client_dashboard, name='client_dashboard'),

    # Detail & Actions
    path('shipments/<str:tracking_number>/', views.shipment_detail, name='shipment_detail'),
    path('shipments/<str:tracking_number>/log-event/', views.log_transit_event, name='log_transit_event'),
    path('shipments/create/new/', views.create_shipment, name='create_shipment'),
    path('products/create/new/', views.create_product, name='create_product'),
]
