import uuid
from os.path import dirname, join

from pydantic import BaseModel, DirectoryPath, EmailStr, Field, FilePath, HttpUrl
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict, TomlConfigSettingsSource


class SmtpSettings(BaseModel):
    test: bool = Field(default=False, description="Do not send any mail if true")
    server: str = Field(description="SMTP server hostname")
    port: int = Field(default=465, description="SMTP server port")
    sender: EmailStr = Field(description="SMTP sender")
    recipients: set[EmailStr] = Field(description="Default receipients")
    recipients_cc: set[EmailStr] = Field(default=set(), description="Additional receipients (cc)")
    recipients_bcc: set[EmailStr] = Field(default=set(), description="Additional receipients (bcc)")
    subject: str = Field(default="", description="Mail subject")
    username: str | None = Field(default=None, description="SMTP authentication username")
    password: str | None = Field(default=None, description="SMTP authentication password")
    starttls: bool = Field(default=True, description="Use SMTP STARTTLS")


class OidcSettings(BaseModel):
    configuration_uri: HttpUrl = Field(
        description="OIDC Configuration URI, usually issuer/.well-known/openid-configuration"
    )
    client_id: str = Field(description="OIDC Client Identifier")
    client_secret: str = Field(description="OIDC Client Secret")
    base_uri: HttpUrl = Field(description="Base URI for the app itself")
    auth_ttl: int = Field(default=300, description="Authentication timeout")
    session_ttl: int = Field(default=86400, description="Default session timeout (if not set by OIDC)")
    scopes: list[str] = Field(default=["openid", "email", "profile"])


class RedisSettings(BaseModel):
    host: str = Field(description="Redis hostname")
    port: int = Field(description="Redis port", default=6379)


class CookieSettings(BaseModel):
    session: str = Field(default="redovisa_session_id")
    recipient_account: str = Field(default="redovisa_recipient_account")
    recipient_account_days: int = Field(default=180, description="Number of days to keep receipient account")


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


class UsersSettings(BaseModel):
    file: FilePath | None = Field(default=None, description="File with list of allowed email addresses")
    ttl: int = Field(default=300, description="User cache TTL")


class HttpSettings(BaseModel):
    trusted_hosts: list[str] | str | None = Field(default="127.0.0.1", description="List of trusted HTTP proxies")


class GoogleSettings(BaseModel):
    service_account_file: FilePath
    sheet_key: str
    worksheet_reports: str | int
    worksheet_items: str | int


class Settings(BaseSettings):
    oidc: OidcSettings
    redis: RedisSettings | None = None
    paths: PathSettings = PathSettings()
    context: dict[str, str | dict[str, str] | bool] = Field(default={})
    cookies: CookieSettings = CookieSettings()
    csrf: CsrfSettings = CsrfSettings()
    users: UsersSettings = UsersSettings()
    http: HttpSettings = HttpSettings()

    smtp: SmtpSettings | None = None
    google: GoogleSettings | None = None

    model_config = SettingsConfigDict(toml_file="redovisa.toml")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (TomlConfigSettingsSource(settings_cls),)
