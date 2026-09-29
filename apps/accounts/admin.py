from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Farm, FarmMembership, FarmUser


class FarmMembershipInline(admin.TabularInline):
    model = FarmMembership
    extra = 1


@admin.register(FarmUser)
class FarmUserAdmin(UserAdmin):
    list_display = ["username", "email", "first_name", "last_name", "is_staff"]
    inlines = [FarmMembershipInline]


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    inlines = [FarmMembershipInline]
