from allauth.headless.socialaccount.views import ProviderSignupView

from accounts.forms import SRCSignupInput


class SRCProviderSignupView(ProviderSignupView):
    input_class = SRCSignupInput
