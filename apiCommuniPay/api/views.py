# apiCommuniPay/api/views.py
from rest_framework import decorators, response, permissions, serializers, views, status
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.validators import UniqueValidator
from apiCommuniPay.accounts.models import Roles
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
import time, hmac, hashlib, json
from urllib.parse import parse_qsl
from django.conf import settings

User = get_user_model()

@decorators.api_view(["GET"])
@decorators.permission_classes([permissions.IsAuthenticated])
def index(_):
    return response.Response({"ok": True})

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    # делаем email уникальным на уровне API (в БД по умолчанию он не unique)
    email = serializers.EmailField(
        required=False, allow_blank=True,
        validators=[UniqueValidator(User.objects.all(), message="User with this email already exists.")],
    )

    class Meta:
        model = User
        fields = ("username", "email", "password")

    def validate_password(self, value):
        # проверяем по стандартным валидаторам Django (длина, common password и т.п.)
        validate_password(value)
        return value

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("User with this email already exists.")
        return value

    def create(self, data):
        email = (data.get("email") or "").strip().lower()
        return User.objects.create_user(
            username=data["username"],
            email=email,
            password=data["password"],
            role=Roles.MEMBER,
        )

class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # защита на уровне вьюхи (на случай пропуска валидации)
        email = (request.data.get("email") or "").strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            return response.Response({"email": ["User with this email already exists."]},
                                     status=status.HTTP_400_BAD_REQUEST)

        s = RegisterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = s.save()
        return response.Response({"id": user.id, "username": user.username}, status=status.HTTP_201_CREATED)

class MeSerializer(serializers.ModelSerializer):
    bot = serializers.SerializerMethodField()
    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "role", "bot")
        read_only_fields = ("id", "username", "role")
    def get_bot(self, obj):
        return {
            "name": getattr(settings, "TELEGRAM_BOT_USERNAME", ""),
            "token": getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        }

class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return response.Response(MeSerializer(request.user).data)

    def patch(self, request):
        s = MeSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return response.Response(s.data, status=status.HTTP_200_OK)

class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": "Incorrect password."})
        validate_password(attrs["new_password"], user=user)
        return attrs

class PasswordChangeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        s = PasswordChangeSerializer(data=request.data, context={"request": request})
        s.is_valid(raise_exception=True)
        user = request.user
        user.set_password(s.validated_data["new_password"])
        user.save(update_fields=["password"])
        # при желании можно принудительно инвалидировать refresh-токены, если включишь blacklisting
        return response.Response(status=status.HTTP_204_NO_CONTENT)

class LogoutView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return response.Response({"detail": "Missing 'refresh'."}, status=400)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError as e:
            return response.Response({"detail": str(e)}, status=400)
        return response.Response(status=status.HTTP_205_RESET_CONTENT)

class TelegramAuthView(views.APIView):
    """
    POST /api/auth/telegram/
    body: { "initData": "<raw initData string>" }
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = "telegram_auth"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        init_data = request.data.get("initData") or request.data.get("init_data")
        if not init_data:
            return response.Response({"detail": "initData is required"}, status=400)

        # parse querystring into dict preserving values
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        their_hash = pairs.pop("hash", None)
        if not their_hash:
            return response.Response({"detail": "hash missing"}, status=400)

        # build data_check_string
        data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))

        bot_token = settings.TELEGRAM_BOT_TOKEN or ""
        if not bot_token:
            return response.Response({"detail": "Server misconfigured: TELEGRAM_BOT_TOKEN is not set"}, status=500)

        # secret_key = hashlib.sha256(bot_token.encode()).digest()
        secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
        my_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(my_hash, their_hash):
            return response.Response({"detail": "Invalid initData signature"}, status=401)

        # optional freshness check (e.g., 24h)
        auth_date = int(pairs.get("auth_date", "0") or "0")
        if auth_date and (time.time() - auth_date) > 24*60*60:
            return response.Response({"detail": "initData is too old"}, status=401)

        # user payload comes as JSON in "user"
        try:
            user_payload = json.loads(pairs.get("user") or "{}")
        except json.JSONDecodeError:
            return response.Response({"detail": "Invalid user payload"}, status=400)

        tg_id = user_payload.get("id")
        if not tg_id:
            return response.Response({"detail": "user.id missing"}, status=400)

        # find or create user by telegram_id
        from django.contrib.auth import get_user_model
        from apiCommuniPay.accounts.models import Roles
        User = get_user_model()

        user, created = User.objects.get_or_create(
            telegram_id=tg_id,
            defaults={
                "username": f"tg_{tg_id}",
                "role": Roles.MEMBER,
                "first_name": user_payload.get("first_name") or "",
                "last_name": user_payload.get("last_name") or "",
                "email": "",  # не используем
            },
        )
        # update tg profile fields on every login
        changed = False
        for field, key in [
            ("tg_username", "username"),
            ("tg_first_name", "first_name"),
            ("tg_last_name", "last_name"),
            ("tg_language_code", "language_code"),
            ("tg_photo_url", "photo_url"),
        ]:
            val = user_payload.get(key) or ""
            if getattr(user, field) != val:
                setattr(user, field, val)
                changed = True
        if changed:
            user.save()

        # issue JWT
        refresh = RefreshToken.for_user(user)
        return response.Response(
            {"access": str(refresh.access_token), "refresh": str(refresh)},
            status=200,
        )