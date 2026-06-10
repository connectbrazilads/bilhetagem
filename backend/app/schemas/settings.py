from pydantic import BaseModel, Field

class LDAPSettings(BaseModel):
    server: str = Field(..., min_length=5, description="LDAP server URL (e.g. ldap://localhost:389)")
    bind_dn: str = Field(..., min_length=2, description="Bind DN (e.g. cn=admin,dc=example,dc=com)")
    bind_password: str = Field(..., min_length=1, description="Bind password")
    search_base: str = Field(..., min_length=2, description="Search base (e.g. dc=example,dc=com)")


class GeneralSettings(BaseModel):
    default_monthly_quota: int = Field(default=500, ge=0)
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
