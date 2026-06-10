import logging
from sqlalchemy.orm import Session
from app.models.user import User, UserRole
from app.models.department import Department
from app.core.security import hash_password
from app.services.quota_service import get_or_create_current_quota

logger = logging.getLogger("ldap_service")

# A list of mock LDAP users and departments to sync
MOCK_LDAP_DATA = [
    {"username": "ana.silva", "full_name": "Ana Silva", "department": "TI"},
    {"username": "pedro.santos", "full_name": "Pedro Santos", "department": "Financeiro"},
    {"username": "carla.souza", "full_name": "Carla Souza", "department": "Recursos Humanos"},
    {"username": "marcos.oliveira", "full_name": "Marcos Oliveira", "department": "Vendas"},
]

def test_ldap_connection(server: str, bind_dn: str, bind_password: str) -> bool:
    """
    Test connection to LDAP server (Mocked).
    If the server address is empty or password is "err" / "invalid", it fails.
    """
    logger.info(f"Testing connection to LDAP server: {server} as {bind_dn}")
    if not server or not bind_dn or not bind_password:
        raise ValueError("Todos os campos de conexão LDAP são obrigatórios.")
    
    if "fail" in server or "error" in bind_password:
        raise ValueError("Falha de conexão com o servidor LDAP. Verifique o endereço e credenciais.")
        
    return True

def sync_ldap_users(db: Session, server: str, bind_dn: str, bind_password: str, search_base: str, organization_id: int | None = None) -> dict:
    """
    Synchronizes users and departments from mock LDAP data into the database.
    """
    # First, test the connection
    test_ldap_connection(server, bind_dn, bind_password)
    if organization_id is None:
        from app.services.organization_service import get_or_create_default_organization
        organization_id = get_or_create_default_organization(db).id
    
    sync_count = 0
    new_users = 0
    updated_users = 0
    
    # Store dynamic department mapping
    dept_cache = {}
    
    for item in MOCK_LDAP_DATA:
        dept_name = item["department"]
        # Resolve department
        if dept_name not in dept_cache:
            dept = db.query(Department).filter(Department.organization_id == organization_id, Department.name == dept_name).first()
            if not dept:
                dept = Department(organization_id=organization_id, name=dept_name)
                db.add(dept)
                db.flush()
            dept_cache[dept_name] = dept.id
            
        dept_id = dept_cache[dept_name]
        
        # Check if user exists
        user = db.query(User).filter(User.organization_id == organization_id, User.username == item["username"]).first()
        if not user:
            user = User(
                organization_id=organization_id,
                username=item["username"],
                full_name=item["full_name"],
                password_hash=hash_password("ldap12345"),
                role=UserRole.user,
                department_id=dept_id,
                is_active=True
            )
            db.add(user)
            db.flush()
            new_users += 1
        else:
            user.full_name = item["full_name"]
            user.department_id = dept_id
            updated_users += 1
            
        # Initialize their quota for current month
        get_or_create_current_quota(db, user)
        sync_count += 1
        
    db.commit()
    
    return {
        "success": True,
        "total_synced": sync_count,
        "new_users": new_users,
        "updated_users": updated_users
    }
