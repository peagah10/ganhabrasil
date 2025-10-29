import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, Response
from dotenv import load_dotenv
import json
import traceback
import base64
import io
import hashlib

# Inicializar bibliotecas opcionais com tratamento de erro
try:
    from supabase import create_client, Client
    supabase_available = True
except ImportError:
    supabase_available = False

try:
    import mercadopago
    mercadopago_available = True
except ImportError:
    mercadopago_available = False

try:
    import qrcode
    qrcode_available = True
except ImportError:
    qrcode_available = False

# Load environment variables
load_dotenv()

# Create Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'ganha-brasil-2025-super-secret-key-v3')

# Configurações
SUPABASE_URL = os.getenv('SUPABASE_URL', "https://ngishqxtnkgvognszyep.supabase.co")
SUPABASE_KEY = os.getenv('SUPABASE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5naXNocXh0bmtndm9nbnN6eWVwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI1OTMwNjcsImV4cCI6MjA2ODE2OTA2N30.FOksPjvS2NyO6dcZ_j0Grj3Prn9OP_udSGQwswtFBXE")
MP_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')

# Constantes da aplicação
TOTAL_RASPADINHAS = 10000
PERCENTUAL_COMISSAO_AFILIADO = 50
PREMIO_INICIAL_ML = 1000.00
PRECO_BILHETE_ML = 2.00
PRECO_RASPADINHA_RB = 1.00
ADMIN_PASSWORD = "paulo10@admin"
APP_VERSION = "3.0.4"

# Sistema de armazenamento em memória
memory_storage = {
    'clientes': [],
    'vendas': [],
    'cliente_raspadinhas': [],
    'cliente_bilhetes': [],
    'ganhadores': [],
    'sorteios': [],
    'afiliados': [],
    'afiliado_clicks': [],
    'afiliado_vendas': [],
    'saques': [],
    'configuracoes': {
        'sistema_ativo': 'true',
        'premio_manual_liberado': '',
        'premio_acumulado': str(PREMIO_INICIAL_ML),
        'percentual_comissao_afiliado': str(PERCENTUAL_COMISSAO_AFILIADO)
    },
    'logs': []
}

# Inicializar Supabase
supabase = None
if supabase_available:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado")
    except Exception as e:
        print(f"❌ Erro Supabase: {e}")
        supabase = None

# Inicializar MercadoPago
sdk = None
if MP_ACCESS_TOKEN and mercadopago_available:
    try:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        print("✅ MercadoPago conectado")
    except Exception as e:
        print(f"❌ Erro MercadoPago: {e}")

# ========== FUNÇÕES AUXILIARES ==========

def log_error(operation, error, extra_data=None):
    """Log de erros"""
    print(f"❌ [{operation}] {str(error)}")
    if extra_data:
        print(f"   Dados: {extra_data}")

def log_info(operation, message, extra_data=None):
    """Log de informações"""
    print(f"ℹ️ [{operation}] {message}")
    if extra_data:
        print(f"   Dados: {extra_data}")

def sanitizar_dados_entrada(data):
    """Sanitiza dados de entrada"""
    if isinstance(data, dict):
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = value.strip()[:500]
            else:
                sanitized[key] = value
        return sanitized
    elif isinstance(data, str):
        return data.strip()[:500]
    return data

def gerar_codigo_antifraude():
    """Gera código único no formato RB-XXXXX-YYY"""
    numero = random.randint(10000, 99999)
    letras = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"RB-{numero}-{letras}"

def gerar_payment_id():
    """Gera ID de pagamento simulado"""
    return f"PAY_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"

def validar_session_admin():
    """Valida se o usuário está logado como admin"""
    return session.get('admin_logado', False)

def validar_session_cliente():
    """Valida se o cliente está logado"""
    return 'cliente_id' in session and 'cliente_cpf' in session

def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração"""
    if supabase:
        try:
            response = supabase.table('gb_configuracoes').select('gb_valor').eq('gb_chave', chave).execute()
            if response.data:
                return response.data[0]['gb_valor']
        except:
            pass
    return memory_storage['configuracoes'].get(chave, valor_padrao)

def atualizar_configuracao(chave, valor, tipo='geral'):
    """Atualiza valor de configuração"""
    if supabase:
        try:
            response = supabase.table('gb_configuracoes').update({
                'gb_valor': str(valor),
                'gb_atualizado_em': datetime.now().isoformat()
            }).eq('gb_chave', chave).execute()
            
            if not response.data:
                supabase.table('gb_configuracoes').insert({
                    'gb_chave': chave,
                    'gb_valor': str(valor),
                    'gb_tipo': tipo
                }).execute()
            return True
        except:
            pass
    
    memory_storage['configuracoes'][chave] = str(valor)
    return True

def get_embedded_html():
    """Retorna página HTML embutida"""
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GANHA BRASIL - Sistema de Jogos Online</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                background: linear-gradient(135deg, #00b341, #ffd700); 
                min-height: 100vh; 
                display: flex; 
                align-items: center; 
                justify-content: center; 
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                text-align: center;
                max-width: 500px;
                width: 90%;
            }
            .logo {
                font-size: 2.5em;
                font-weight: bold;
                color: #00b341;
                margin-bottom: 20px;
            }
            .subtitle {
                color: #666;
                margin-bottom: 30px;
                font-size: 1.1em;
            }
            .games {
                display: flex;
                gap: 20px;
                margin: 30px 0;
                flex-wrap: wrap;
                justify-content: center;
            }
            .game-card {
                background: linear-gradient(135deg, #00b341, #00a037);
                color: white;
                padding: 20px;
                border-radius: 15px;
                flex: 1;
                min-width: 200px;
                cursor: pointer;
                transition: transform 0.3s;
            }
            .game-card:hover {
                transform: translateY(-5px);
            }
            .game-title {
                font-weight: bold;
                font-size: 1.2em;
                margin-bottom: 10px;
            }
            .game-price {
                font-size: 1.1em;
                color: #ffd700;
            }
            .status {
                background: #f0f0f0;
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
            }
            .btn {
                background: #00b341;
                color: white;
                padding: 12px 30px;
                border: none;
                border-radius: 25px;
                font-size: 1.1em;
                cursor: pointer;
                transition: background 0.3s;
                margin: 10px;
                text-decoration: none;
                display: inline-block;
            }
            .btn:hover {
                background: #00a037;
            }
            .btn-secondary {
                background: #ffd700;
                color: #333;
            }
            .btn-secondary:hover {
                background: #ffcd00;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🎯 GANHA BRASIL</div>
            <div class="subtitle">Sistema de Jogos Online</div>
            
            <div class="status">
                <h3>✅ Sistema Online e Funcionando!</h3>
                <p>API v3.0.4 - Vercel Deploy Success</p>
            </div>
            
            <div class="games">
                <div class="game-card">
                    <div class="game-title">🎫 RASPA BRASIL</div>
                    <div class="game-price">R$ 1,00</div>
                    <div>Raspadinhas virtuais com prêmios instantâneos!</div>
                </div>
                <div class="game-card">
                    <div class="game-title">🎲 2 PARA 1000</div>
                    <div class="game-price">R$ 2,00</div>
                    <div>Sorteio diário da milhar. Prêmio acumulado!</div>
                </div>
            </div>
            
            <div>
                <a href="/test" class="btn">🔧 Testar API</a>
                <a href="/health" class="btn btn-secondary">📊 Status Sistema</a>
            </div>
            
            <div style="margin-top: 30px; color: #666; font-size: 0.9em;">
                <p>🔒 Login necessário para jogar</p>
                <p>👥 Sistema de afiliados disponível</p>
                <p>💰 Pagamentos via PIX</p>
            </div>
        </div>
        
        <script>
            // Auto test API
            setTimeout(() => {
                fetch('/health')
                    .then(r => r.json())
                    .then(data => {
                        console.log('✅ Sistema funcionando:', data);
                    })
                    .catch(e => console.log('❌ Erro:', e));
            }, 2000);
        </script>
    </body>
    </html>
    """

def get_error_page(error_msg="Erro desconhecido"):
    """Retorna página de erro"""
    return f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>GANHA BRASIL - Erro</title>
        <style>
            body {{ 
                font-family: Arial, sans-serif; 
                text-align: center; 
                padding: 50px; 
                background: linear-gradient(135deg, #00b341, #ffd700); 
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            .error {{ 
                color: #dc2626; 
                background: white; 
                padding: 30px; 
                border-radius: 15px; 
                margin: 20px auto; 
                max-width: 600px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            .btn {{
                background: #00b341;
                color: white;
                padding: 10px 20px;
                text-decoration: none;
                border-radius: 5px;
                display: inline-block;
                margin: 10px 5px;
            }}
            code {{
                background: #f5f5f5;
                padding: 10px;
                border-radius: 5px;
                display: block;
                margin: 15px 0;
                word-break: break-all;
            }}
        </style>
    </head>
    <body>
        <div class="error">
            <h1>🚫 Erro no Sistema</h1>
            <p>Ocorreu um problema temporário:</p>
            <code>{error_msg}</code>
            <br>
            <a href="/test" class="btn">🔧 Testar API</a>
            <a href="/health" class="btn">📊 Status</a>
            <a href="/" class="btn">🔄 Início</a>
        </div>
    </body>
    </html>
    """

# ========== ROTAS PRINCIPAIS ==========

@app.route('/')
def index():
    """Serve a página principal"""
    try:
        # Registrar código de afiliado se presente
        ref_code = request.args.get('ref')
        if ref_code:
            session['ref_code'] = ref_code
            log_info("index", f"Código de afiliado registrado: {ref_code}")
        
        # Retornar página HTML embutida
        return get_embedded_html()
        
    except Exception as e:
        log_error("index", e)
        return get_error_page(str(e))

@app.route('/test')
def test():
    """Rota de teste para Vercel"""
    try:
        return jsonify({
            'status': 'ok',
            'message': 'API funcionando no Vercel!',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'supabase_connected': supabase is not None,
            'mercadopago_connected': sdk is not None,
            'qrcode_available': qrcode_available,
            'environment': os.getenv('VERCEL_ENV', 'development'),
            'python_version': f"{os.sys.version_info.major}.{os.sys.version_info.minor}",
            'features': {
                'login_system': True,
                'payment_system': True,
                'affiliate_system': True,
                'admin_panel': True,
                'games': ['raspa_brasil', '2para1000']
            }
        })
    except Exception as e:
        log_error("test", e)
        return jsonify({
            'status': 'error',
            'message': str(e),
            'version': APP_VERSION
        }), 500

@app.route('/health')
def health_check():
    """Health check detalhado"""
    try:
        hoje = date.today().isoformat()
        
        stats = {
            'vendas_rb_hoje': 0,
            'vendas_ml_hoje': 0,
            'total_clientes': 0,
            'total_afiliados': 0,
            'sistema_funcionando': True
        }
        
        # Tentar obter estatísticas
        if supabase:
            try:
                # Teste simples de conectividade
                test_response = supabase.table('gb_clientes').select('gb_id').limit(1).execute()
                stats['database_connected'] = True
            except Exception as e:
                stats['database_connected'] = False
                stats['database_error'] = str(e)
        else:
            stats['database_connected'] = False
            stats['database_mode'] = 'memory'
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'vercel_deployment': True,
            'services': {
                'flask': True,
                'supabase': supabase is not None,
                'mercadopago': sdk is not None,
                'qrcode': qrcode_available
            },
            'games_available': ['raspa_brasil', '2para1000'],
            'configuration': {
                'total_raspadinhas': TOTAL_RASPADINHAS,
                'premio_inicial_ml': PREMIO_INICIAL_ML,
                'preco_raspadinha': PRECO_RASPADINHA_RB,
                'preco_bilhete': PRECO_BILHETE_ML,
                'comissao_afiliado': PERCENTUAL_COMISSAO_AFILIADO
            },
            'statistics': stats,
            'memory_storage_active': True
        })
        
    except Exception as e:
        log_error("health_check", e)
        return jsonify({
            'status': 'error',
            'error': str(e),
            'version': APP_VERSION,
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/cliente/cadastrar', methods=['POST'])
def cliente_cadastrar():
    """Cadastra novo cliente"""
    try:
        data = sanitizar_dados_entrada(request.json or {})
        
        nome = data.get('nome', '').strip()
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        telefone = data.get('telefone', '').strip()
        email = data.get('email', '').strip()
        
        if not nome or len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        if supabase:
            try:
                # Verificar se CPF já existe
                existing = supabase.table('gb_clientes').select('gb_id').eq('gb_cpf', cpf).execute()
                if existing.data:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
                
                response = supabase.table('gb_clientes').insert({
                    'gb_nome': nome[:255],
                    'gb_cpf': cpf,
                    'gb_telefone': telefone[:20] if telefone else None,
                    'gb_email': email[:255] if email else None,
                    'gb_status': 'ativo',
                    'gb_ip_cadastro': request.remote_addr or 'unknown'
                }).execute()
                
                if response.data:
                    cliente = response.data[0]
                    session['cliente_id'] = cliente['gb_id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = nome
                    
                    log_info("cliente_cadastrar", f"Cliente cadastrado: {nome}")
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['gb_id'],
                            'nome': nome,
                            'cpf': cpf
                        }
                    })
                    
            except Exception as e:
                log_error("cliente_cadastrar", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Verificar duplicata em memória
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
            
            cliente_data = {
                'id': len(memory_storage['clientes']) + 1,
                'nome': nome[:255],
                'cpf': cpf,
                'telefone': telefone[:20] if telefone else None,
                'email': email[:255] if email else None,
                'status': 'ativo',
                'ip_cadastro': request.remote_addr or 'unknown',
                'data_cadastro': datetime.now().isoformat()
            }
            
            memory_storage['clientes'].append(cliente_data)
            
            session['cliente_id'] = cliente_data['id']
            session['cliente_cpf'] = cpf
            session['cliente_nome'] = nome
            
            log_info("cliente_cadastrar", f"Cliente cadastrado em memória: {nome}")
            return jsonify({
                'sucesso': True,
                'cliente': {
                    'id': cliente_data['id'],
                    'nome': nome,
                    'cpf': cpf
                }
            })
            
    except Exception as e:
        log_error("cliente_cadastrar", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/cliente/login', methods=['POST'])
def cliente_login():
    """Login do cliente por CPF"""
    try:
        data = sanitizar_dados_entrada(request.json or {})
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        if supabase:
            try:
                response = supabase.table('gb_clientes').select('*').eq('gb_cpf', cpf).eq('gb_status', 'ativo').execute()
                
                if response.data:
                    cliente = response.data[0]
                    
                    session['cliente_id'] = cliente['gb_id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = cliente['gb_nome']
                    
                    log_info("cliente_login", f"Cliente logado: {cliente['gb_nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['gb_id'],
                            'nome': cliente['gb_nome'],
                            'cpf': cpf
                        }
                    })
                else:
                    return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
                    
            except Exception as e:
                log_error("cliente_login", e)
                return jsonify({'sucesso': False, 'erro': 'Erro no banco de dados'})
        else:
            # Buscar em memória
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf and cliente.get('status') == 'ativo':
                    session['cliente_id'] = cliente['id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = cliente['nome']
                    
                    log_info("cliente_login", f"Cliente logado: {cliente['nome']}")
                    
                    return jsonify({
                        'sucesso': True,
                        'cliente': {
                            'id': cliente['id'],
                            'nome': cliente['nome'],
                            'cpf': cpf
                        }
                    })
            
            return jsonify({'sucesso': False, 'erro': 'CPF não encontrado'})
            
    except Exception as e:
        log_error("cliente_login", e)
        return jsonify({'sucesso': False, 'erro': 'Erro interno do servidor'})

@app.route('/cliente/verificar_login')
def cliente_verificar_login():
    """Verifica se o cliente está logado"""
    try:
        if validar_session_cliente():
            return jsonify({
                'logado': True,
                'cliente': {
                    'id': session.get('cliente_id'),
                    'nome': session.get('cliente_nome'),
                    'cpf': session.get('cliente_cpf')
                }
            })
        else:
            return jsonify({'logado': False})
            
    except Exception as e:
        log_error("cliente_verificar_login", e)
        return jsonify({'logado': False})

@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX"""
    try:
        if not validar_session_cliente():
            return jsonify({'error': 'Faça login primeiro'}), 401
        
        data = sanitizar_dados_entrada(request.json or {})
        quantidade = data.get('quantidade', 1)
        game_type = data.get('game_type', 'raspa_brasil')
        
        if not isinstance(quantidade, int) or quantidade < 1 or quantidade > 50:
            return jsonify({'error': 'Quantidade inválida'}), 400
        
        if game_type not in ['raspa_brasil', '2para1000']:
            return jsonify({'error': 'Tipo de jogo inválido'}), 400
        
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        total = quantidade * preco_unitario
        
        payment_id = gerar_payment_id()
        
        # Salvar na sessão
        session['payment_id'] = payment_id
        session['quantidade'] = quantidade
        session['game_type'] = game_type
        session['payment_created_at'] = datetime.now().isoformat()
        
        log_info("create_payment", f"Pagamento criado: {payment_id} - {game_type} - R$ {total:.2f}")
        
        return jsonify({
            'id': payment_id,
            'qr_code': f'PIX{total:.2f}GANHA_BRASIL',
            'qr_code_base64': None,
            'status': 'pending',
            'amount': total
        })
        
    except Exception as e:
        log_error("create_payment", e)
        return jsonify({'error': 'Erro interno do servidor'}), 500

@app.route('/check_payment/<payment_id>')
def check_payment(payment_id):
    """Verifica status do pagamento"""
    try:
        if not payment_id:
            return jsonify({'error': 'Payment ID inválido'}), 400
        
        # Simular aprovação após 3 segundos
        payment_key = f'payment_processed_{payment_id}'
        if payment_key not in session:
            payment_created = session.get('payment_created_at')
            if payment_created:
                created_time = datetime.fromisoformat(payment_created)
                if (datetime.now() - created_time).total_seconds() > 3:
                    session[payment_key] = True
                    log_info("check_payment", f"Pagamento aprovado: {payment_id}")
                    return jsonify({'status': 'approved'})
                else:
                    return jsonify({'status': 'pending'})
            else:
                return jsonify({'status': 'pending'})
        else:
            return jsonify({'status': 'approved'})
        
    except Exception as e:
        log_error("check_payment", e)
        return jsonify({'error': str(e)}), 500

@app.route('/admin/login', methods=['POST'])
def admin_login():
    """Login do admin"""
    try:
        data = sanitizar_dados_entrada(request.json or {})
        senha = data.get('senha')
        
        if senha == ADMIN_PASSWORD:
            session['admin_logado'] = True
            log_info("admin_login", "Admin logado")
            return jsonify({'success': True, 'message': 'Login realizado'})
        
        return jsonify({'success': False, 'message': 'Senha incorreta'})
    
    except Exception as e:
        log_error("admin_login", e)
        return jsonify({'success': False, 'message': 'Erro interno'})

# ========== CONFIGURAÇÃO PARA VERCEL ==========

# Garantir que a aplicação funcione no Vercel
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# Handle para o Vercel
def handler(request):
    return app(request.environ, request.start_response)

# Exportar a aplicação para o Vercel
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🚀 GANHA BRASIL v{APP_VERSION} - Iniciando na porta {port}")
    print(f"✅ Supabase: {'Conectado' if supabase else 'Modo Memória'}")
    print(f"✅ MercadoPago: {'Conectado' if sdk else 'Simulado'}")
    print(f"✅ Sistema funcionando!")
    app.run(host='0.0.0.0', port=port, debug=False)
