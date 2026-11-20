from django.db import models
from django.contrib.auth.models import AbstractUser

class UserRole(models.TextChoices):
    MANAGER = 'MANAGER', 'Manager'
    PORTER = 'PORTER', 'Porter'
    DRIVER = 'DRIVER', 'Driver'
    CLIENT = 'CLIENT', 'Client'

class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.CLIENT,
        help_text="Designates the user's access portal and privilege scope."
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True, help_text="e.g. +254712345678")
    national_id = models.CharField(max_length=30, blank=True, null=True, help_text="National ID / Passport Number")
    company_name = models.CharField(max_length=120, blank=True, null=True, help_text="For clients or logistics contractors")
    assigned_hub_name = models.CharField(max_length=100, blank=True, null=True, help_text="Primary depot/warehouse for porters/drivers")
    vehicle_plate = models.CharField(max_length=30, blank=True, null=True, help_text="Assigned vehicle for drivers (e.g. KCA 123X)")
    license_number = models.CharField(max_length=50, blank=True, null=True, help_text="Driving license / Porter certification")
    avatar_color = models.CharField(max_length=10, default='#3b82f6')

    class Meta:
        verbose_name = 'TransitFlow User'
        verbose_name_plural = 'TransitFlow Users'

    @property
    def is_manager(self):
        return self.role == UserRole.MANAGER or self.is_superuser

    @property
    def is_porter(self):
        return self.role == UserRole.PORTER

    @property
    def is_driver(self):
        return self.role == UserRole.DRIVER

    @property
    def is_client(self):
        return self.role == UserRole.CLIENT

    @property
    def role_badge_class(self):
        badges = {
            UserRole.MANAGER: 'bg-purple-100 text-purple-800 border-purple-200',
            UserRole.PORTER: 'bg-amber-100 text-amber-800 border-amber-200',
            UserRole.DRIVER: 'bg-emerald-100 text-emerald-800 border-emerald-200',
            UserRole.CLIENT: 'bg-blue-100 text-blue-800 border-blue-200',
        }
        return badges.get(self.role, 'bg-gray-100 text-gray-800 border-gray-200')

    @property
    def portal_url_name(self):
        mapping = {
            UserRole.MANAGER: 'manager_dashboard',
            UserRole.PORTER: 'porter_dashboard',
            UserRole.DRIVER: 'driver_dashboard',
            UserRole.CLIENT: 'client_dashboard',
        }
        return mapping.get(self.role, 'client_dashboard')

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"
