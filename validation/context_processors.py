from .branding import auth_cover_url, site_brand
from .models import UserProfile
from .siteconfig import display_name, get_site, meta_description


def user_profile(request):
    brand = site_brand()
    site = get_site()
    data = {
        "auth_bg_url": auth_cover_url(),
        "site": site,
        "site_name": display_name(),
        "site_meta_description": meta_description(),
        "site_logo": brand["logo_url"],
        "site_logo_version": brand["version"],
    }
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        data["user_profile"] = None
        return data
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    data["user_profile"] = profile
    return data
