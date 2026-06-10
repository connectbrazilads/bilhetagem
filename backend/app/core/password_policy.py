UNSAFE_INITIAL_PASSWORDS = {
    "",
    "admin",
    "agent",
    "admin12345",
    "agent12345",
    "change-me-admin-password",
    "change-me-agent-password",
    "password",
    "senha123",
    "12345678",
}


def is_unsafe_initial_password(password: str) -> bool:
    return password.strip().lower() in UNSAFE_INITIAL_PASSWORDS
