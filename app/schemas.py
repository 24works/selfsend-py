from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _coerce_address_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str) and item.strip()]
    raise ValueError("expected a string or a list of strings")


def _preview(value: object, limit: int = 200) -> str:
    text = repr(value)
    return text[:limit] + "..." if len(text) > limit else text


class Attachment(BaseModel):
    filename: str
    content: str
    content_type: str | None = None


class EmailTag(BaseModel):
    name: str
    value: str


class SendEmailRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(validation_alias=AliasChoices("from", "from_"))
    to: list[str]
    subject: str
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    reply_to: list[str] | None = Field(
        default=None,
        validation_alias=AliasChoices("reply_to", "replyTo"),
    )
    html: str | None = None
    text: str | None = None
    headers: dict[str, str] | None = None
    tags: list[EmailTag] | None = None
    attachments: list[Attachment] | None = None

    @field_validator("to", mode="before")
    @classmethod
    def _coerce_to(cls, value: object) -> list[str]:
        items = _coerce_address_list(value)
        if not items:
            raise ValueError(
                f"'to' must contain at least one valid recipient (got: {_preview(value)})"
            )
        return items

    @field_validator("cc", "bcc", "reply_to", mode="before")
    @classmethod
    def _coerce_optional_addresses(cls, value: object) -> list[str] | None:
        if value is None:
            return None
        return _coerce_address_list(value)

    @field_validator("subject")
    @classmethod
    def _reject_newlines(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("'subject' must not contain line breaks")
        return value

    @model_validator(mode="after")
    def _require_body(self) -> "SendEmailRequest":
        if not self.html and not self.text:
            raise ValueError("either 'html' or 'text' must be provided")
        return self
