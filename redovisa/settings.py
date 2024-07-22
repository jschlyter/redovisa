from typing import Tuple, Type

from fastapi_mail import ConnectionConfig
from pydantic import BaseModel, EmailStr, Field, HttpUrl
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
    username: str | None = Field(default=True)
    password: str | None = Field(default=True)
    starttls: bool = Field(default=True)

    def get_connection_config(self) -> ConnectionConfig:
        return ConnectionConfig(
            MAIL_SERVER=self.server,
            MAIL_FROM=self.sender,
            MAIL_USERNAME=self.username,
            MAIL_PASSWORD=self.password,
            MAIL_PORT=self.port,
            MAIL_STARTTLS=self.starttls,
            MAIL_SSL_TLS=True,
        )


class OidcSettings(BaseModel):
    configuration_uri: HttpUrl
    client_id: str
    client_secret: str
    base_uri: HttpUrl
    auth_ttl: int = 3600


class RedisSettings(BaseModel):
    host: str
    port: int = 6379


class Settings(BaseSettings):
    smtp: SmtpSettings
    oidc: OidcSettings
    redis: RedisSettings
    context: dict[str, str] = Field(default={})

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
