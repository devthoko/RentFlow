import os
from dataclasses import dataclass
from pathlib import Path
@dataclass
class Config:
    data: Path
    secret: str
    setup_token: str
    secure_cookie: bool = False
    base_url: str = "http://localhost"
    @classmethod
    def environment(cls):
        secret = os.environ.get("RF_SECRET", "")
        if len(secret) < 32: raise RuntimeError("RF_SECRET muss mindestens 32 Zeichen enthalten.")
        return cls(Path(os.environ.get("RF_DATA", "/var/lib/rentflow")), secret,
                   os.environ.get("RF_SETUP_TOKEN", ""), os.environ.get("RF_SECURE_COOKIE", "0") == "1",
                   os.environ.get("RF_BASE_URL", "http://localhost"))
