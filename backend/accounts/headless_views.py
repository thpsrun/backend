from allauth.headless.socialaccount.views import ProviderSignupView

from accounts.forms import SRCSignupInput


class SRCProviderSignupView(ProviderSignupView):
    """Headless provider-signup view that swaps in the SRC-key-capturing input form."""

    input_class = SRCSignupInput
