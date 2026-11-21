from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import User, UserRole

def login_view(request):
    if request.user.is_authenticated:
        return redirect('portal_redirect')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! Logged in as {user.get_role_display()}.")
            return redirect('portal_redirect')
        else:
            messages.error(request, "Invalid username or password.")

    # Demo quick-login accounts for seamless review
    demo_accounts = [
        {"role": "Manager", "username": "manager_alice", "title": "Fleet & Operations Overseer", "badge": "bg-purple-100 text-purple-800"},
        {"role": "Porter", "username": "porter_brian", "title": "Cold-Chain & Cargo Handling", "badge": "bg-amber-100 text-amber-800"},
        {"role": "Driver", "username": "driver_david", "title": "Highway Route Transit Operator", "badge": "bg-emerald-100 text-emerald-800"},
        {"role": "Client", "username": "client_cynthia", "title": "Fresh Produce Consignor / Importer", "badge": "bg-blue-100 text-blue-800"},
    ]

    return render(request, 'core/login.html', {'demo_accounts': demo_accounts})

def logout_view(request):
    logout(request)
    messages.info(request, "You have been securely logged out.")
    return redirect('login')

@login_required
def portal_redirect(request):
    """Routes the user to their designated role portal."""
    role = getattr(request.user, 'role', UserRole.CLIENT)
    if role == UserRole.MANAGER or request.user.is_superuser:
        return redirect('manager_dashboard')
    elif role == UserRole.PORTER:
        return redirect('porter_dashboard')
    elif role == UserRole.DRIVER:
        return redirect('driver_dashboard')
    else:
        return redirect('client_dashboard')

@login_required
def quick_switch_role(request, target_role):
    """
    Demo/Evaluator feature: Switches current test user or logs in the representative demo user for that role.
    Allows effortless testing of all 4 isolated portals and role sessions!
    """
    demo_map = {
        'MANAGER': 'manager_alice',
        'PORTER': 'porter_brian',
        'DRIVER': 'driver_david',
        'CLIENT': 'client_cynthia',
    }
    target_username = demo_map.get(target_role)
    if target_username:
        try:
            target_user = User.objects.get(username=target_username)
            login(request, target_user)
            messages.success(request, f"Switched session to {target_user.get_role_display()} Portal ({target_user.username}).")
        except User.DoesNotExist:
            request.user.role = target_role
            request.user.save()
            messages.success(request, f"Your role has been set to {target_role}.")

    return redirect('portal_redirect')

def register_view(request):
    if request.user.is_authenticated:
        return redirect('portal_redirect')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name', '')
        last_name = request.POST.get('last_name', '')
        role = request.POST.get('role', UserRole.CLIENT)
        phone = request.POST.get('phone_number', '')
        company = request.POST.get('company_name', '')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists. Please pick another.")
        else:
            user = User.objects.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                phone_number=phone,
                company_name=company
            )
            login(request, user)
            messages.success(request, f"Registration successful! Welcome to TransitFlow as a {user.get_role_display()}.")
            return redirect('portal_redirect')

    return render(request, 'core/register.html', {'roles': UserRole.choices})
