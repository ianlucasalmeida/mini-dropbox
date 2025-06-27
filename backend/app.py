import os
import boto3
import io
import zipfile
from flask import Flask, request, redirect, url_for, render_template, flash, jsonify, Response
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from sqlalchemy import and_, or_

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configuração da Aplicação Flask ---
app = Flask(__name__, template_folder='templates', static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'uma-chave-secreta-padrao-e-insegura')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Configuração do Banco de Dados e Login ---
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Por favor, faça login para acessar esta página."
login_manager.login_message_category = "info"

# --- Modelos do Banco de Dados ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    files = db.relationship('File', backref='owner', lazy=True, cascade="all, delete-orphan")

class File(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(1024), nullable=False, default='/')
    is_folder = db.Column(db.Boolean, default=False)
    tag = db.Column(db.String(20), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    s3_key = db.Column(db.String(1024), unique=True, nullable=True)
    size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# --- Configuração do Cliente S3 ---
try:
    s3_client = boto3.client(
        's3',
        endpoint_url=os.getenv('S3_ENDPOINT_URL'),
        aws_access_key_id=os.getenv('S3_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('S3_SECRET_ACCESS_KEY')
    )
    S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME')
except Exception as e:
    s3_client = None
    print(f"ERRO: Não foi possível conectar ao S3/MinIO. Verifique as variáveis de ambiente. Erro: {e}")

# --- Rotas de Autenticação ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if not user or not check_password_hash(user.password, request.form.get('password')):
            flash('Usuário ou senha inválidos.', 'danger')
            return redirect(url_for('login'))
        login_user(user)
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        if User.query.filter_by(username=request.form.get('username')).first():
            flash('Este nome de usuário já existe.', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=request.form.get('username'), password=generate_password_hash(request.form.get('password'), method='pbkdf2:sha256'))
        db.session.add(new_user)
        db.session.commit()
        flash('Conta criada com sucesso! Por favor, faça login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Rotas Principais ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
@login_required
def index(path):
    current_path = f"/{path}".replace('//', '/')
    folders = File.query.filter_by(user_id=current_user.id, path=current_path, is_folder=True).order_by(File.name).all()
    files_db = File.query.filter_by(user_id=current_user.id, path=current_path, is_folder=False).order_by(File.name).all()
    for file_item in files_db:
        file_item.thumbnail_url = None
        if file_item.mime_type and file_item.mime_type.startswith('image/'):
            try:
                url = s3_client.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET_NAME, 'Key': file_item.s3_key}, ExpiresIn=3600)
                file_item.thumbnail_url = url
            except Exception as e:
                print(f"Erro ao gerar thumbnail url para {file_item.s3_key}: {e}")
    path_parts = list(filter(None, current_path.split('/')))
    breadcrumbs = [{'name': part, 'path': '/'.join(path_parts[:i+1])} for i, part in enumerate(path_parts)]
    return render_template('index.html', folders=folders, files=files_db, current_path=current_path, breadcrumbs=breadcrumbs, username=current_user.username)

# --- NOVA ROTA: Visualizador de Arquivo ---
@app.route('/view/<int:file_id>')
@login_required
def view_file(file_id):
    file_item = db.session.get(File, file_id)
    if not file_item or file_item.user_id != current_user.id or file_item.is_folder:
        flash("Arquivo não encontrado ou acesso negado.", "danger")
        return redirect(url_for('index'))
    
    file_url = s3_client.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET_NAME, 'Key': file_item.s3_key}, ExpiresIn=3600)
    
    return render_template('view.html', file=file_item, file_url=file_url)

# --- Rotas de Ação (Upload, Create, Delete, etc.) ---
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    current_path = request.form.get('current_path', '/')
    uploaded_file = request.files.get('file')
    if not uploaded_file or uploaded_file.filename == '':
        flash('Nenhum arquivo selecionado.', 'warning'); return redirect(current_path)
    filename = secure_filename(uploaded_file.filename)
    if File.query.filter_by(user_id=current_user.id, path=current_path, name=filename).first():
        flash(f'Um item chamado "{filename}" já existe nesta pasta.', 'danger'); return redirect(current_path)
    path_parts = [p for p in current_path.split('/') if p]; path_parts.append(filename)
    s3_key = f"user_{current_user.id}/{'/'.join(path_parts)}"
    file_size = uploaded_file.seek(0, os.SEEK_END); uploaded_file.seek(0)
    try:
        s3_client.upload_fileobj(uploaded_file, S3_BUCKET_NAME, s3_key, ExtraArgs={'ContentType': uploaded_file.content_type})
        new_file_db = File(name=filename, path=current_path, user_id=current_user.id, s3_key=s3_key, size=file_size, mime_type=uploaded_file.content_type)
        db.session.add(new_file_db); db.session.commit()
        flash(f'Arquivo "{filename}" enviado com sucesso!', 'success')
    except Exception as e: flash(f"Erro no upload: {e}", 'danger')
    return redirect(current_path)

@app.route('/create_folder', methods=['POST'])
@login_required
def create_folder():
    current_path = request.form.get('current_path', '/'); folder_name = secure_filename(request.form.get('folder_name'))
    if not folder_name: flash('O nome da pasta não pode ser vazio.', 'warning'); return redirect(current_path)
    if File.query.filter_by(user_id=current_user.id, path=current_path, name=folder_name).first():
        flash(f'Uma pasta ou arquivo chamado "{folder_name}" já existe.', 'danger'); return redirect(current_path)
    new_folder = File(name=folder_name, path=current_path, is_folder=True, user_id=current_user.id)
    db.session.add(new_folder); db.session.commit()
    flash(f'Pasta "{folder_name}" criada com sucesso!', 'success')
    return redirect(current_path)

@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    item = db.session.get(File, item_id)
    if not item or item.user_id != current_user.id:
        flash("Item não encontrado ou acesso negado.", "danger"); return redirect(url_for('index'))
    parent_path = item.path
    if not item.is_folder:
        try:
            if item.s3_key: s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=item.s3_key)
            db.session.delete(item); db.session.commit()
            flash(f'Arquivo "{item.name}" apagado com sucesso.', 'success')
        except Exception as e: flash(f"Erro ao apagar o arquivo: {e}", "danger"); db.session.rollback()
    else:
        try:
            folder_full_path = os.path.join(item.path, item.name).replace('//', '/')
            files_to_delete_q = File.query.filter(File.user_id == current_user.id, File.is_folder == False, or_(File.path == folder_full_path, File.path.startswith(folder_full_path + '/')))
            s3_keys = [{'Key': f.s3_key} for f in files_to_delete_q.all() if f.s3_key]
            if s3_keys: s3_client.delete_objects(Bucket=S3_BUCKET_NAME, Delete={'Objects': s3_keys})
            db_records_to_delete_q = File.query.filter(File.user_id == current_user.id, or_(File.id == item_id, File.path.startswith(folder_full_path)))
            db_records_to_delete_q.delete(synchronize_session=False); db.session.commit()
            flash(f'Pasta "{item.name}" e seu conteúdo foram apagados.', 'success')
        except Exception as e: flash(f"Erro ao apagar a pasta: {e}", "danger"); db.session.rollback()
    return redirect(parent_path)

@app.route('/download_file/<int:file_id>')
@login_required
def download_file(file_id):
    file_to_download = db.session.get(File, file_id)
    if not file_to_download or file_to_download.user_id != current_user.id:
        flash("Arquivo não encontrado ou acesso negado.", "danger"); return redirect(url_for('index'))
    try:
        content_disposition = f'attachment; filename="{secure_filename(file_to_download.name)}"'
        url = s3_client.generate_presigned_url('get_object', Params={'Bucket': S3_BUCKET_NAME, 'Key': file_to_download.s3_key, 'ResponseContentDisposition': content_disposition}, ExpiresIn=3600)
        return redirect(url)
    except Exception as e: flash(f"Erro ao gerar link de download: {e}", 'danger'); return redirect(file_to_download.path)

@app.route('/download_folder/<int:folder_id>')
@login_required
def download_folder(folder_id):
    folder = db.session.get(File, folder_id)
    if not folder or folder.user_id != current_user.id or not folder.is_folder:
        flash("Acesso negado ou item inválido.", "danger"); return redirect(url_for('index'))
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zip_archive:
        base_path = os.path.join(folder.path, folder.name).replace('//', '/')
        files_to_zip = File.query.filter(File.user_id == current_user.id, File.is_folder == False, or_(File.path == base_path, File.path.startswith(base_path + '/'))).all()
        if not files_to_zip: flash("A pasta está vazia, nada para baixar.", "warning"); return redirect(folder.path)
        for file_db in files_to_zip:
            try:
                file_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=file_db.s3_key)
                relative_path = os.path.relpath(os.path.join(file_db.path, file_db.name), folder.path)
                zip_archive.writestr(relative_path.lstrip('/'), file_obj['Body'].read())
            except Exception as e: print(f"Não foi possível adicionar o arquivo {file_db.s3_key} ao zip: {e}")
    memory_file.seek(0)
    return Response(memory_file, mimetype='application/zip', headers={'Content-Disposition': f'attachment;filename={folder.name}.zip'})

@app.route('/tag_file', methods=['POST'])
@login_required
def tag_file():
    data = request.get_json(); file_id = data.get('file_id'); tag = data.get('tag')
    file_to_tag = db.session.get(File, file_id)
    if not file_to_tag or file_to_tag.user_id != current_user.id:
        return jsonify({'success': False, 'message': 'Arquivo não encontrado ou acesso negado.'}), 404
    file_to_tag.tag = tag if tag != 'none' else None; db.session.commit()
    return jsonify({'success': True, 'message': 'Tag atualizada com sucesso!'})

@app.route('/get_folder_tree', methods=['GET'])
@login_required
def get_folder_tree():
    folders = File.query.filter_by(user_id=current_user.id, is_folder=True).order_by(File.path, File.name).all()
    folder_tree = {'/': {'name': 'Raiz', 'path': '/', 'subfolders': {}}}
    for folder in folders:
        path_parts = [p for p in folder.path.split('/') if p]
        current_level = folder_tree['/']['subfolders']
        for part in path_parts:
            if part not in current_level: current_level[part] = {'name': part, 'subfolders': {}}
            current_level = current_level[part]['subfolders']
        full_path = os.path.join(folder.path, folder.name).replace('//','/')
        current_level[folder.name] = {'name': folder.name, 'path': full_path, 'subfolders': {}}
    return jsonify(folder_tree)

@app.route('/move_item/<int:item_id>', methods=['POST'])
@login_required
def move_item(item_id):
    target_path = request.form.get('target_path', '/')
    item_to_move = db.session.get(File, item_id)
    if not item_to_move or item_to_move.user_id != current_user.id:
        flash("Item não encontrado ou acesso negado.", "danger"); return redirect(url_for('index'))
    if item_to_move.path == target_path:
        flash("O item já está nesta pasta.", "warning"); return redirect(item_to_move.path)
    if item_to_move.is_folder:
        old_full_path = os.path.join(item_to_move.path, item_to_move.name).replace('//', '/')
        if target_path.startswith(old_full_path):
            flash("Não é possível mover uma pasta para dentro de si mesma.", "danger"); return redirect(item_to_move.path)
    try:
        if not item_to_move.is_folder:
            new_s3_key_path = os.path.join(target_path.strip('/'), item_to_move.name)
            new_s3_key = f"user_{current_user.id}/{new_s3_key_path}"
            s3_client.copy_object(CopySource={'Bucket': S3_BUCKET_NAME, 'Key': item_to_move.s3_key}, Bucket=S3_BUCKET_NAME, Key=new_s3_key)
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=item_to_move.s3_key)
            item_to_move.path = target_path
            item_to_move.s3_key = new_s3_key
        else:
            old_full_path = os.path.join(item_to_move.path, item_to_move.name).replace('//', '/')
            descendants = File.query.filter(File.user_id == current_user.id, or_(File.path == old_full_path, File.path.startswith(old_full_path + '/'))).all()
            s3_ops_to_delete = []
            for item in descendants:
                relative_item_path = os.path.relpath(item.path, old_full_path)
                new_item_path = os.path.join(target_path, item_to_move.name, relative_item_path).replace('/./', '/').replace('//', '/')
                if not item.is_folder:
                    new_s3_key_path = os.path.join(new_item_path.strip('/'), item.name)
                    new_s3_key = f"user_{current_user.id}/{new_s3_key_path}"
                    s3_client.copy_object(CopySource={'Bucket': S3_BUCKET_NAME, 'Key': item.s3_key}, Bucket=S3_BUCKET_NAME, Key=new_s3_key)
                    s3_ops_to_delete.append({'Key': item.s3_key})
                    item.s3_key = new_s3_key
                item.path = new_item_path
            item_to_move.path = target_path
            if s3_ops_to_delete: s3_client.delete_objects(Bucket=S3_BUCKET_NAME, Delete={'Objects': s3_ops_to_delete})
        db.session.commit()
        flash(f'"{item_to_move.name}" movido com sucesso!', 'success')
        return redirect(target_path)
    except Exception as e:
        db.session.rollback()
        flash(f"Erro ao mover item: {e}", "danger")
        return redirect(item_to_move.path if item_to_move else url_for('index'))

# --- Inicialização ---
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0')
