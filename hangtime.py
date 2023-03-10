from app import app, db
from app.models import User
# will need to import messager, scheduler runs on its own

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User}
