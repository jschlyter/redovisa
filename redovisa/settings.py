import uuid
from os.path import dirname, join
from typing import Tuple, Type

from pydantic import BaseModel, DirectoryPath, EmailStr, Field, HttpUrl
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class SmtpSettings(BaseModel):
    test: bool = False
    server: str
    port: int = Field(default=465)
    sender: EmailStr
    recipients: set[EmailStr]
    recipients_cc: set[EmailStr] = Field(default=set())
    recipients_bcc: set[EmailStr] = Field(default=set())
    subject: str = Field(default="")
    username: str | None = Field(default=None)
    password: str | None = Field(default=None)
    starttls: bool = Field(default=True)


class OidcSettings(BaseModel):
    configuration_uri: HttpUrl
    client_id: str
    client_secret: str
    base_uri: HttpUrl
    auth_ttl: int = 300
    session_ttl: int = 86400


class RedisSettings(BaseModel):
    host: str
    port: int = 6379


class CookieSettings(BaseModel):
    session: str = Field(default="redovisa_session_id")
    recipient_account: str = Field(default="redovisa_recipient_account")
    recipient_account_days: int = 180


class PathSettings(BaseModel):
    templates: DirectoryPath = Field(default=join(dirname(__file__), "templates"))
    static: DirectoryPath = Field(default=join(dirname(__file__), "static"))


class CsrfSettings(BaseModel):
    cookie_key: str = "redovisa_csrf_token"
    secret_key: str = Field(default_factory=lambda: str(uuid.uuid4()))
    token_key: str = "csrf_token"
    token_location: str = "body"

    def get_settings(self) -> BaseModel:
        return self


class Settings(BaseSettings):
    smtp: SmtpSettings
    oidc: OidcSettings
    redis: RedisSettings | None = None
    paths: PathSettings = PathSettings()
    context: dict[str, str | dict[str, str]] = Field(default={})
    cookies: CookieSettings = CookieSettings()
    csrf: CsrfSettings = CsrfSettings()

    trusted_hosts: list[str] | str | None = "127.0.0.1"

    model_config = SettingsConfigDict(toml_file="redovisa.toml")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (TomlConfigSettingsSource(settings_cls),)
