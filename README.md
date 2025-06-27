Projeto Mini Dropbox Distribuído
Visão Geral
Este projeto é uma prova de conceito de um sistema de armazenamento de arquivos inspirado no Dropbox. Desenvolvido com Python e Flask no backend, e uma interface web interativa com HTML, CSS e JavaScript, o sistema permite que usuários se registrem, gerenciem seus arquivos e pastas em um ambiente isolado e seguro, e organizem seus dados com funcionalidades avançadas.

O principal diferencial do projeto é a utilização de um sistema de armazenamento de objetos distribuído (compatível com Amazon S3, como o MinIO para desenvolvimento local), garantindo que a aplicação seja escalável e tolerante a falhas, princípios fundamentais de arquiteturas de nuvem modernas.

Funcionalidades Implementadas
Autenticação de Usuários: Sistema completo de registro e login para garantir a privacidade e o isolamento dos dados de cada usuário.

Gerenciamento de Arquivos e Pastas:

Upload de arquivos para a pasta atual.

Criação de novas pastas.

Exclusão de arquivos e pastas (com confirmação).

Download de arquivos individuais.

Download de pastas inteiras como um arquivo .zip.

Organização Avançada:

Mover Itens: Mova arquivos ou pastas inteiras para qualquer outro local na sua árvore de diretórios.

Tags de Cor: Marque arquivos com cores (vermelho, azul, verde, amarelo) para uma organização visual, semelhante ao macOS.

Interface Rica:

Visualização Dupla: Alterne entre uma visualização em grade, com pré-visualização de imagens, e uma visualização em lista, mais compacta e detalhada.

Navegação Intuitiva: Navegue pelas pastas com breadcrumbs e uma interface responsiva.

Menu de Contexto: Clique com o botão direito em qualquer item para acessar rapidamente ações como Mover, Apagar ou aplicar Tags.

Arquitetura da Solução
A aplicação foi projetada seguindo uma arquitetura de três camadas, desacoplando a apresentação, a lógica de negócio e o armazenamento de dados.

Diagrama da Arquitetura
      +------------------+      +--------------------+      +-------------------------+
      |                  |      |                    |      |                         |
      |   Navegador Web  |----->|   Frontend (UI)    |----->|      Backend (Flask)    |
      | (Cliente/Usuário)|      | (HTML, CSS, JS)    |      | (Lógica da Aplicação)   |
      |                  |      |                    |      |                         |
      +------------------+      +--------------------+      +-----------+-------------+
                                                                        |
                                                                        |
                                          +-----------------------------+-----------------------------+
                                          |                                                           |
                                          v                                                           v
                              +--------------------+                                        +-------------------------+
                              |                    |                                        |                         |
                              |   Banco de Dados   |                                        | Armazenamento Distribuído|
                              |     (SQLite)       |                                        |    (MinIO / AWS S3)     |
                              | (Metadados dos     |                                        |   (Objetos/Arquivos)    |
                              |   arquivos e       |                                        |                         |
                              |      usuários)     |                                        +-------------------------+
                              +--------------------+


Componentes:
Frontend: A camada de apresentação com a qual o usuário interage. Construída com HTML, CSS (Bootstrap) e JavaScript, ela é responsável por exibir a interface e enviar requisições para o backend.

Backend (Flask): O cérebro da aplicação. Ele gerencia a lógica de negócio, processa as requisições HTTP, autentica usuários, interage com o banco de dados para gerenciar metadados e orquestra as operações de upload, download e exclusão no sistema de armazenamento.

Banco de Dados (SQLite): Armazena os metadados da aplicação. Isso inclui a tabela de usuários (nomes, senhas) e a tabela de arquivos (nomes, caminhos, tags, dono, etc.). A separação dos metadados dos arquivos em si é crucial para a performance.

Armazenamento Distribuído (MinIO/S3): É onde os arquivos brutos (objetos) são de fato armazenados. Este serviço é projetado para alta durabilidade, disponibilidade e escalabilidade.

Justificativas Técnicas
Escalabilidade
A arquitetura foi pensada para ser escalável horizontalmente:

Backend sem estado (Stateless): O estado da aplicação (arquivos e sessões de usuário) é mantido fora do servidor Flask, no S3 e no banco de dados. Isso permite que múltiplas instâncias do servidor backend rodem em paralelo por trás de um balanceador de carga (Load Balancer). Se o tráfego aumentar, basta adicionar mais servidores para distribuir a carga, sem impacto para o usuário.

Armazenamento Escalável: O Amazon S3 (e o MinIO em modo distribuído) é um serviço massivamente escalável. Ele pode lidar com um volume virtualmente ilimitado de dados e um número altíssimo de requisições, sem a necessidade de gerenciamento de discos ou infraestrutura por nossa parte.

Tolerância a Falhas
O sistema é resiliente a falhas em múltiplos níveis:

Backend: Com múltiplas instâncias do servidor rodando, se uma delas falhar, o balanceador de carga automaticamente redireciona o tráfego para as instâncias saudáveis, garantindo que a aplicação permaneça online.

Armazenamento: O S3 replica os dados automaticamente em múltiplas Zonas de Disponibilidade (data centers fisicamente separados). Isso significa que, mesmo na falha de um data center inteiro, os dados permanecem seguros e acessíveis. O MinIO pode ser configurado de forma semelhante para replicar dados entre diferentes servidores e discos.

Banco de Dados: Embora este projeto use SQLite para simplicidade, em um ambiente de produção, um serviço de banco de dados gerenciado (como Amazon RDS) seria usado. Estes serviços também oferecem replicação e failover automático entre múltiplas zonas.

Como Executar o Projeto
Siga os passos abaixo para configurar e rodar a aplicação em seu ambiente local.

Pré-requisitos
Python 3.10+

Pip (gerenciador de pacotes do Python)

Docker e Docker Compose (para rodar o MinIO facilmente)

1. Clonar o Repositório
git clone <url-do-seu-repositorio>
cd mini-dropbox

2. Configurar o Ambiente Python
É altamente recomendado usar um ambiente virtual para isolar as dependências.

# Navegue até a pasta do backend
cd backend

# Crie o ambiente virtual
python -m venv venv

# Ative o ambiente
# No Windows:
venv\Scripts\activate
# No macOS/Linux:
source venv/bin/activate

# Instale as dependências
pip install -r requirements.txt

3. Iniciar o Serviço de Armazenamento (MinIO)
Vamos usar o Docker para rodar uma instância local do MinIO.

# Na raiz do projeto, execute o comando:
docker run -p 9000:9000 -p 9001:9001 \
  --name minio-dropbox \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"

Acesse o console do MinIO em http://localhost:9001.

Faça login com minioadmin / minioadmin.

Crie um bucket chamado uploads.

4. Configurar Variáveis de Ambiente
Crie um arquivo chamado .env dentro da pasta backend/.

# backend/.env

# Chave secreta para segurança da sessão do Flask. Mude para uma string aleatória.
SECRET_KEY='uma-chave-secreta-muito-segura-e-aleatoria'

# Credenciais e endereço do MinIO
S3_ENDPOINT_URL=[http://127.0.0.1:9000](http://127.0.0.1:9000)
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=minioadmin
S3_BUCKET_NAME=uploads

5. Executar a Aplicação
Com o ambiente virtual ativo e dentro da pasta backend/, execute o Flask.

flask run

O banco de dados db.sqlite será criado automaticamente na primeira vez que você rodar.

Acesse http://127.0.0.1:5000 em seu navegador para começar a usar o Mini Dropbox!