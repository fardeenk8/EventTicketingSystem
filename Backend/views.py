from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from Users.models import Profile

def index(request):
    return render(request, "index.html")

def loginn(request):
    return render(request, "login.html")

def register(request):
    ref = (request.GET.get("ref") or "").strip()
    return render(request, "register.html", {"prefill_referral": ref})

def user_login(request):
    if request.method == "POST":
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)

            if user.is_staff or user.is_superuser:
                return redirect('adminhome')
            else:
                return redirect('userhome')
        else:
            # Differentiate invalid credentials from "registered but pending approval".
            pending_user = User.objects.filter(username=username).first()
            if pending_user and pending_user.check_password(password) and not pending_user.is_active:
                messages.warning(request, "Your account is pending admin approval. Please wait for activation.")
                return redirect('loginn')

            messages.error(request, "Invalid username or password.")
            return redirect('loginn')

    return render(request, 'login.html')

def user_registration(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        referral_code = (request.POST.get('referral_code') or "").strip().upper()

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect('register')

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already exists.")
            return redirect('register')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        user.is_active = False  
        user.save()

        referrer = None
        if referral_code:
            ref_profile = (
                Profile.objects.filter(referral_code__iexact=referral_code)
                .exclude(referral_code="")
                .select_related("user")
                .first()
            )
            if ref_profile and ref_profile.user_id != user.id:
                referrer = ref_profile.user
            else:
                messages.warning(request, "Referral code was not recognized; registration continued without it.")

        if referrer:
            prof = user.profile
            if not prof.referred_by_id:
                prof.referred_by = referrer
                prof.save(update_fields=["referred_by"])

        messages.success(request, "Registration successful! Please wait for admin approval.")
        return redirect('loginn')

    return render(request, 'register.html')

def user_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('index')