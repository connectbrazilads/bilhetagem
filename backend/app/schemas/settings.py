from pydantic import BaseModel, Field

class LDAPSettings(BaseModel):
    server: str | None = Field(default=None, min_length=5, max_length=255, description="LDAP server URL (e.g. ldap://localhost:389)")
    bind_dn: str | None = Field(default=None, min_length=2, max_length=255, description="Bind DN (e.g. cn=admin,dc=example,dc=com)")
    bind_password: str | None = Field(default=None, min_length=1, max_length=255, description="Bind password")
    search_base: str | None = Field(default=None, min_length=2, max_length=255, description="Search base (e.g. dc=example,dc=com)")


class LDAPSettingsRead(BaseModel):
    server: str = ""
    bind_dn: str = ""
    search_base: str = ""
    has_bind_password: bool = False


class GeneralSettings(BaseModel):
    default_monthly_quota: int = Field(default=500, ge=0)
    default_printer_cost_mono: float = Field(default=0.05, ge=0)
    default_printer_cost_color: float = Field(default=0.25, ge=0)
    auto_create_users: bool = Field(default=True)
    blocking_enabled: bool = Field(default=True)
    show_balance: bool = Field(default=True)
    safe_release_enabled: bool = Field(default=True)
    web_print_enabled: bool = Field(default=True)


class MonthlyReportEmailSettings(BaseModel):
    enabled: bool = Field(default=False)
    recipients: str = Field(default="", max_length=255)
    day_of_month: int = Field(default=1, ge=1, le=28)
    include_pdf: bool = Field(default=True)
    include_xlsx: bool = Field(default=True)


class OperationalSettings(BaseModel):
    safe_release_enabled: bool = Field(default=True)
