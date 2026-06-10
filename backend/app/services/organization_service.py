from sqlalchemy.orm import Session

from app.models.organization import Organization

DEFAULT_ORGANIZATION_SLUG = "default"
DEFAULT_ORGANIZATION_NAME = "Empresa Padrao"


def get_or_create_default_organization(db: Session) -> Organization:
    organization = db.query(Organization).filter(Organization.slug == DEFAULT_ORGANIZATION_SLUG).first()
    if organization:
        return organization
    organization = Organization(name=DEFAULT_ORGANIZATION_NAME, slug=DEFAULT_ORGANIZATION_SLUG, is_active=True)
    db.add(organization)
    db.flush()
    return organization
