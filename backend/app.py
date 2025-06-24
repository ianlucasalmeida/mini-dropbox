import os
import boto3
from flask import Flask, request, redirect, url_for, render_template
from botocore.exceptions import ClientError
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates')

# Carrega variáveis de ambiente
S3_ENDPOINT_URL = os.getenv('S3_ENDPOINT_URL', 'http://localhost:9000')
S3_ACCESS_KEY_ID = os.getenv('S3_ACCESS_KEY_ID', 'minioadmin')
S3_SECRET_ACCESS_KEY = os.getenv('S3_SECRET_ACCESS_KEY', 'minioadmin')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'mini-dropbox')

# Configura o cliente S3
s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY_ID,
    aws_secret_access_key=S3_SECRET_ACCESS_KEY
)

def create_bucket_if_not_exists():
    """Cria o bucket se ele não existir"""
    try:
        # Verifica se o bucket existe
        s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
        logger.info(f"Bucket {S3_BUCKET_NAME} já existe")
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == '404':
            try:
                # Cria o bucket se não existir
                s3_client.create_bucket(Bucket=S3_BUCKET_NAME)
                logger.info(f"Bucket {S3_BUCKET_NAME} criado com sucesso")
            except ClientError as create_error:
                logger.error(f"Erro ao criar bucket: {create_error}")
                raise
        else:
            logger.error(f"Erro ao verificar bucket: {e}")
            raise

# Cria o bucket ao iniciar a aplicação
create_bucket_if_not_exists()

@app.route('/')
def index():
    try:
        response = s3_client.list_objects_v2(Bucket=S3_BUCKET_NAME)
        files = response.get('Contents', [])
    except ClientError as e:
        logger.error(f"Erro ao listar arquivos: {e}")
        files = []
    return render_template('index.html', files=files)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "Nenhum arquivo enviado", 400
        
    file = request.files['file']
    if file.filename == '':
        return "Nenhum arquivo selecionado", 400
    
    try:
        s3_client.upload_fileobj(
            file,
            S3_BUCKET_NAME,
            file.filename
        )
        logger.info(f"Arquivo {file.filename} enviado com sucesso")
    except Exception as e:
        logger.error(f"Erro no upload: {e}")
        return f"Erro no upload: {e}", 500

    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': filename},
            ExpiresIn=3600
        )
        return redirect(url)
    except ClientError as e:
        logger.error(f"Erro ao gerar URL: {e}")
        return f"Erro ao baixar arquivo: {e}", 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)