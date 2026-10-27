from django.contrib import admin

from .models import AuditLog, Claim, FoundReport, LostReport, Match


@admin.register(FoundReport)
class FoundAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "last5", "country", "area", "status", "created_at")
    list_filter = ("status", "country", "area")
    search_fields = ("reference", "full_name", "last5")
    readonly_fields = ("reference", "name_key", "created_at")


@admin.register(LostReport)
class LostAdmin(admin.ModelAdmin):
    list_display = ("reference", "full_name", "last5", "country", "area", "status", "created_at")
    list_filter = ("status", "country", "area")
    search_fields = ("reference", "full_name", "last5")
    readonly_fields = ("reference", "name_key", "created_at")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("lost", "found", "status", "created_at")
    list_filter = ("status",)


@admin.register(Claim)
class ClaimAdmin(admin.ModelAdmin):
    list_display = ("reference", "found", "claimant_name", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("reference", "created_at", "updated_at")


@admin.register(AuditLog)
class AuditAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "target")
    list_filter = ("action",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
