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
    auth_ttl: int = 3600


class RedisSettings(BaseModel):
    host: str
    port: int = 6379


class PathSettings(BaseModel):
    templates: DirectoryPath = Field(default=join(dirname(__file__), "templates"))
    static: DirectoryPath = Field(default=join(dirname(__file__), "static"))


class Settings(BaseSettings):
    smtp: SmtpSettings
    oidc: OidcSettings
    redis: RedisSettings
    paths: PathSettings = PathSettings()
    context: dict[str, str | dict[str, str]] = Field(default={})

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
