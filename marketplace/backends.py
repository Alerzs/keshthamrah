from .models import AdminAccount


class AdminBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or password is None:
            return None
        try:
            account = AdminAccount.objects.get(username=username)
        except AdminAccount.DoesNotExist:
            return None
        if account.is_active and account.check_password(password):
            return account
        return None

    def get_user(self, user_id):
        try:
            return AdminAccount.objects.get(pk=user_id)
        except AdminAccount.DoesNotExist:
            return None
