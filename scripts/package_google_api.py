"""Build a secret-free Vercel FastAPI source folder from the repository."""
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve()
target.mkdir(parents=True, exist_ok=True)
source = root / 'backend/integrations/google'
package = target / 'backend/integrations/google'
package.mkdir(parents=True, exist_ok=True)
for item in source.glob('*.py'):
    shutil.copyfile(item, package / item.name)
shutil.copyfile(root / 'backend/schemas.py', target / 'backend/schemas.py')
shutil.copyfile(root / 'backend/profile.py', target / 'backend/profile.py')
shutil.copyfile(source / 'requirements.txt', target / 'requirements.txt')
(target / 'app.py').write_text('from backend.integrations.google.public_app import create_public_app\n\napp = create_public_app()\n')
(target / 'vercel.json').write_text('{"framework":"fastapi"}\n')
(target / '.vercelignore').write_text('.env*\n__pycache__\n*.pyc\n')
print('Secret-free Google API package created.')
