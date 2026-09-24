from .branding import auth_cover_url, site_brand
from .models import UserProfile


def user_profile(request):
    brand = site_brand()
    data = {
        "auth_bg_url": auth_cover_url(),
        "site_logo": brand["logo_url"],
        "site_logo_version": brand["version"],
    }
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        data["user_profile"] = None
        return data
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    data["user_profile"] = profile
    return data
