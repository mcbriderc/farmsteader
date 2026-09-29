from django.contrib.auth.mixins import LoginRequiredMixin


class FarmAccessMixin(LoginRequiredMixin):
    """Mixin that filters querysets to the current farm and auto-sets farm on create."""

    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(qs.model, "farm"):
            qs = qs.filter(farm=self.request.farm)
        return qs

    def form_valid(self, form):
        if hasattr(form.instance, "farm_id"):
            form.instance.farm = self.request.farm
        return super().form_valid(form)
