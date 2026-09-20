"""Read this checkout's private settings without changing the caller's environment."""
import os
from pathlib import Path
from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parent.parent / '.env.local'


def read_settings(path=ENV_FILE, environ=None):
    values = {key: value for key, value in dotenv_values(path).items() if value is not None} if path.is_file() else {}
    values.update(os.environ if environ is None else environ)
    return values
