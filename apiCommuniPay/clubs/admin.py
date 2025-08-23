from django.contrib import admin
from .models import Plan, PlanChannel, Subscription
from django.db.models import Count


class PlanChannelInline(admin.TabularInline):
    model = PlanChannel
    extra = 0
    autocomplete_fields = ["chat"]  # если включите search, будет удобно


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "project", "price", "is_public", "channels_count","created_at")
    ordering = ("-created_at",)
    list_select_related = ("project",)
    search_fields = ("name", "project__name")
    list_filter = ("project", "is_public")
    filter_horizontal = ("channels",)  # удобно выбирать M2M

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # аннотируем distinct-счётчик каналов, чтобы не ловить дубликаты через through
        return qs.annotate(_channels_cnt=Count("channels", distinct=True))

    def channels_count(self, obj):
        return getattr(obj, "_channels_cnt", obj.channels.count())
    channels_count.short_description = "Каналов"
    channels_count.admin_order_field = "_channels_cnt"

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "plan", "status", "starts_at", "ends_at")
    list_filter = ("status", "plan__project")
    search_fields = ("user__email", "plan__name")


# Если нужно отдельно редактировать связ (обычно хватает инлайна)
@admin.register(PlanChannel)
class PlanChannelAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "chat")
    list_filter = ("plan__project",)
    search_fields = ("plan__name", "chat__title", "chat__tg_chat_id")
