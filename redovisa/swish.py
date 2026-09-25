import urllib.parse
from enum import StrEnum

import httpx2

SWISH_APP_URL = "https://app.swish.nu/1/p/sw/"
SWISH_API_QRCODE_URL = "https://mpc.getswish.net/qrg-swish/api/v1/prefilled"

SWISH_QRCODE_DEFAULT_SIZE = 300


class SwishImageFormat(StrEnum):
    PNG = "png"
    JPG = "jpg"
    SVG = "svg"


def get_swish_app_url(
    payee: str,
    amount: float | None = None,
    message: str | None = None,
    edit_amount: bool = False,
    edit_message: bool = False,
) -> str:

    edit: set[str] = {}
    if edit_amount:
        edit.add("amt")
    if edit_message:
        edit.add("msg")

    params = {
        "sw": payee,
        **({"amt": amount} if amount else {}),
        **({"msg": message} if message else {}),
        **({"edit": ",".join(edit)} if edit else {}),
    }

    return SWISH_APP_URL + "?" + urllib.parse.urlencode(params)


def get_swish_qrcode_url(
    payee: str | None = None,
    amount: float | None = None,
    message: str | None = None,
    edit_payee: bool = False,
    edit_amount: bool = False,
    edit_message: bool = False,
    format: SwishImageFormat = SwishImageFormat.PNG,
    size: int | None = None,
    border: int | None = None,
    transparent: bool = False,
) -> bytes:

    if format != SwishImageFormat.SVG and not size:
        size = SWISH_QRCODE_DEFAULT_SIZE

    params = {
        "format": format.value,
        **(
            {
                "payee": {
                    "value": payee,
                    "editable": edit_payee,
                }
            }
            if payee
            else {}
        ),
        **(
            {
                "amount": {
                    "value": amount,
                    "editable": edit_amount,
                }
            }
            if amount
            else {}
        ),
        **(
            {
                "message": {
                    "value": message,
                    "editable": edit_message,
                }
            }
            if message
            else {}
        ),
        **({"size": size} if size else {}),
        **({"border": border} if border else {}),
        **({"transparent": transparent} if transparent else {}),
    }

    response = httpx2.post(SWISH_API_QRCODE_URL, json=params)
    response.raise_for_status()
    return response.content


def format_swish_payee(s: str, size: int = 3, sep: str = " ") -> str:
    """Format a Swish payee string in groups of `size` digits from the right, separated by `sep`."""

    head = len(s) % size
    parts = [s[:head]] if head else []
    parts += [s[i : i + size] for i in range(head, len(s), size)]

    return sep.join(parts)
