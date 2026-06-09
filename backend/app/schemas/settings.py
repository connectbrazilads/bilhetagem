from pydantic import BaseModel, Field

class LDAPSettings(BaseModel):
    server: str = Field(..., min_length=5, description="LDAP server URL (e.g. ldap://localhost:389)")
    bind_dn: str = Field(..., min_length=2, description="Bind DN (e.g. cn=admin,dc=example,dc=com)")
    bind_password: str = Field(..., min_length=1, description="Bind password")
    search_base: str = Field(..., min_length=2, description="Search base (e.g. dc=example,dc=com)")
