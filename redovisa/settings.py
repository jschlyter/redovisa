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
    recipients: list[EmailStr]
    recipients_cc: list[EmailStr] = Field(default=[])
    recipients_bcc: list[EmailStr] = Field(default=[])
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
    session: str = Field(default="session_id")
    recipient_account: str = Field(default="recipient_account")
    recipient_account_days: int = 180


class PathSettings(BaseModel):
    templates: DirectoryPath = Field(default=join(dirname(__file__), "templates"))
    static: DirectoryPath = Field(default=join(dirname(__file__), "static"))


class Settings(BaseSettings):
    smtp: SmtpSettings
    oidc: OidcSettings
    redis: RedisSettings | None = None
    paths: PathSettings = PathSettings()
    context: dict[str, str | dict[str, str]] = Field(default={})
    cookies: CookieSettings = CookieSettings()

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
