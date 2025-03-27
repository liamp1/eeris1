from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('is_manager',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (None, {'fields': ('is_manager',)}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'is_manager')
    list_filter = ('is_manager',)

admin.site.register(CustomUser, CustomUserAdmin)
