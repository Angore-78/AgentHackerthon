from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('portal-redirect/', views.portal_redirect, name='portal_redirect'),
    path('quick-switch/<str:target_role>/', views.quick_switch_role, name='quick_switch_role'),
]
