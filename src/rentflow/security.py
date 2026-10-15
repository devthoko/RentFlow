import base64, hashlib
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet
from email_validator import validate_email, EmailNotValidError
hasher = PasswordHasher()
def password_hash(password):
    if len(password) < 12: raise ValueError("Das Passwort muss mindestens 12 Zeichen enthalten.")
    return hasher.hash(password)
def password_valid(hashed, password):
    try: return hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError): return False
def email(value):
    try: return validate_email(value.strip(), check_deliverability=False).normalized
    except EmailNotValidError: raise ValueError("Bitte eine gültige E-Mail-Adresse eingeben.")
def cipher(config): return Fernet(base64.urlsafe_b64encode(hashlib.sha256(config.secret.encode()).digest()))
def encrypt(config, value): return cipher(config).encrypt(value.encode()).decode() if value else ""
def decrypt(config, value): return cipher(config).decrypt(value.encode()).decode() if value else ""
