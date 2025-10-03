from django.contrib import admin
from .models import Contact


@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("email", "owner", "contact_user", "name", "created_at")
    list_filter = ("created_at",)
    search_fields = ("email", "name", "owner__email", "contact_user__email")
    ordering = ("-created_at",)

# Register your models here.
