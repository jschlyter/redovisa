import re
import uuid
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from .oidc import Session


class ExpenseItem(BaseModel):
    account: int
    account_name: str | None
    description: str | None
    amount: float


class Recipient(BaseModel):
    name: str
    email: str
    account: int


class ExpenseReport(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    date: date
    items: list[ExpenseItem]
    total_amount: float
    recipient: Recipient

    @classmethod
    def from_form(
        cls,
        form,
        session: Session,
        accounts: dict[str, str],
    ):
        items = []

        for name in form:
            if match := re.match(r"^(\d+):account$", name):
                row = match.group(1)

                if account := form.get(name):
                    items.append(
                        ExpenseItem(
                            account=int(account),
                            account_name=accounts.get(account),
                            description=form.get(f"{row}:description"),
                            amount=float(form.get(f"{row}:amount")),
                        )
                    )

        return cls(
            date=form["date"],
            items=items,
            total_amount=sum([item.amount for item in items]),
            recipient=Recipient(
                name=session.name,
                email=session.email,
                account=int(re.sub(r"[^\d]", "", form["recipient_account"])),
            ),
        )
