from django.http import HttpRequest
from ninja import Router
from srl.models import CountryCodes

from api.v1.schemas.auth import CountryCodeResponse

router = Router()


@router.get(
    "",
    response=list[CountryCodeResponse],
    summary="List Country Codes",
    description="Returns all available country codes sorted alphabetically by name.",
)
def list_countries(
    request: HttpRequest,
) -> list[CountryCodeResponse]:
    return [
        CountryCodeResponse(
            id=c.id,
            name=c.name,
            flag=c.flag.url if c.flag else None,
        )
        for c in CountryCodes.objects.all()
    ]
