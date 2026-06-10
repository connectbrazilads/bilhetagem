UNSAFE_INITIAL_PASSWORDS = {
    "",
    "admin12345",
    "agent12345",
    "change-me-admin-password",
    "change-me-agent-password",
}


def is_unsafe_initial_password(password: str) -> bool:
    return password.strip().lower() in UNSAFE_INITIAL_PASSWORDS
