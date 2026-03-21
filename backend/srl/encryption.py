from cryptography.fernet import Fernet, InvalidToken  # noqa: F401
from django.conf import settings


def _get_fernet() -> Fernet:
    """Returns a Fernet instance using the configured encryption key."""
    key = settings.SRC_ENCRYPTION_KEY
    if not key:
        raise ValueError(
            "SRC_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )
    return Fernet(key.encode())


def encrypt_src_key(plain_key: str,) -> str:
    """Encrypts an SRC API key for database storage.

    Args:
        plain_key: The raw SRC API key.

    Returns:
        The Fernet-encrypted ciphertext as a UTF-8 string.
    """
    f = _get_fernet()
    return f.encrypt(plain_key.encode()).decode()


def decrypt_src_key(encrypted_key: str,) -> str:
    """Decrypts a stored SRC API key for use in SRC API calls.

    Args:
        encrypted_key: The Fernet-encrypted ciphertext.

    Returns:
        The original plaintext SRC API key.

    Raises:
        cryptography.fernet.InvalidToken: If the key is corrupted or the
            encryption key has changed.
    """
    f = _get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()
