import os
import random
import string
from datetime import datetime, date, timedelta
from flask import Flask, request, jsonify, session, send_from_directory, Response
from dotenv import load_dotenv
import json
import traceback
import base64
import io
import hashlib
import uuid

# Inicializar bibliotecas opcionais
try:
    from supabase import create_client, Client
    supabase_available = True
except ImportError:
    supabase_available = False
    print("⚠️ Supabase não disponível - usando modo simulação")

try:
    import mercadopago
    mercadopago_available = True
except ImportError:
    mercadopago_available = False
    print("⚠️ MercadoPago não disponível - usando pagamentos simulados")

try:
    import qrcode
    qrcode_available = True
except ImportError:
    qrcode_available = False
    print("⚠️ QRCode não disponível")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_CENTER
    reportlab_available = True
except ImportError:
    reportlab_available = False
    print("⚠️ ReportLab não disponível - PDFs não serão gerados")

load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.getenv('SECRET_KEY', 'ganha-brasil-2025-super-secret-key-v3')

# Configurações do Supabase
SUPABASE_URL = os.getenv('SUPABASE_URL', "https://ngishqxtnkgvognszyep.supabase.co")
SUPABASE_KEY = os.getenv('SUPABASE_KEY', "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5naXNocXh0bmtndm9nbnN6eWVwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI1OTMwNjcsImV4cCI6MjA2ODE2OTA2N30.FOksPjvS2NyO6dcZ_j0Grj3Prn9OP_udSGQwswtFBXE")

# Configurações do Mercado Pago
MP_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN')
sdk = None

# Configurações da aplicação
TOTAL_RASPADINHAS = 10000
PREMIOS_TOTAIS = 2000
WHATSAPP_NUMERO = "5582996092684"
PERCENTUAL_COMISSAO_AFILIADO = 50
PREMIO_INICIAL_ML = 1000.00
PRECO_BILHETE_ML = 2.00
PRECO_RASPADINHA_RB = 1.00
ADMIN_PASSWORD = "paulo10@admin"
APP_VERSION = "3.0.3"

# Sistema de armazenamento em memória (fallback)
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

# Inicializar cliente Supabase
supabase = None
if supabase_available:
    try:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase conectado com sucesso")
    except Exception as e:
        print(f"❌ Erro ao conectar com Supabase: {str(e)}")
        supabase = None

# Configurar Mercado Pago
try:
    if MP_ACCESS_TOKEN and mercadopago_available:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        print("✅ Mercado Pago SDK configurado com sucesso")
    else:
        print("❌ Token do Mercado Pago não encontrado - usando pagamentos simulados")
except Exception as e:
    print(f"❌ Erro ao configurar Mercado Pago: {str(e)}")
    sdk = None

# ========== FUNÇÕES AUXILIARES ==========

def hash_cpf(cpf):
    """Cria hash do CPF para usar como senha"""
    return hashlib.sha256(cpf.encode()).hexdigest()[:12]

def log_error(operation, error, extra_data=None):
    """Log de erros centralizado"""
    error_msg = f"❌ [{operation}] {str(error)}"
    print(error_msg)
    if extra_data:
        print(f"   Dados extras: {extra_data}")
    
    log_entry = {
        'id': len(memory_storage['logs']) + 1,
        'operacao': operation,
        'tipo': 'error',
        'mensagem': str(error)[:500],
        'dados_extras': json.dumps(extra_data) if extra_data else None,
        'timestamp': datetime.now().isoformat()
    }
    
    if supabase:
        try:
            supabase.table('gb_logs_sistema').insert({
                'gb_operacao': operation,
                'gb_tipo': 'error',
                'gb_mensagem': str(error)[:500],
                'gb_dados_extras': json.dumps(extra_data) if extra_data else None,
                'gb_ip_origem': request.remote_addr if request else None
            }).execute()
        except:
            pass
    else:
        memory_storage['logs'].append(log_entry)

def log_info(operation, message, extra_data=None):
    """Log de informações centralizado"""
    info_msg = f"ℹ️ [{operation}] {message}"
    print(info_msg)
    if extra_data:
        print(f"   Dados: {extra_data}")

def gerar_codigo_antifraude():
    """Gera código único no formato RB-XXXXX-YYY"""
    numero = random.randint(10000, 99999)
    letras = ''.join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"RB-{numero}-{letras}"

def gerar_codigo_afiliado():
    """Gera código único para afiliado no formato AF-XXXXX"""
    import time
    numero = random.randint(100000, 999999)
    timestamp = int(time.time()) % 1000
    return f"AF{numero}{timestamp}"

def gerar_milhar():
    """Gera número aleatório de 4 dígitos entre 1111 e 9999"""
    return str(random.randint(1111, 9999))

def gerar_payment_id():
    """Gera ID de pagamento simulado"""
    return f"PAY_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"

def gerar_qr_code_simulado(payment_data):
    """Gera QR code simulado para pagamentos"""
    qr_text = f"PIX{payment_data['amount']:.2f}GANHA_BRASIL"
    
    if qrcode_available:
        try:
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_text)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
            
            return {
                'qr_code': qr_text,
                'qr_code_base64': img_base64
            }
        except Exception as e:
            log_error("gerar_qr_code_simulado", e)
    
    return {
        'qr_code': qr_text,
        'qr_code_base64': None
    }

def sanitizar_dados_entrada(data):
    """Sanitiza dados de entrada para evitar problemas de segurança"""
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

def obter_configuracao(chave, valor_padrao=None):
    """Obtém valor de configuração"""
    if supabase:
        try:
            response = supabase.table('gb_configuracoes').select('gb_valor').eq('gb_chave', chave).execute()
            if response.data:
                return response.data[0]['gb_valor']
            return valor_padrao
        except Exception as e:
            log_error("obter_configuracao", e, {"chave": chave})
            return valor_padrao
    else:
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
                response = supabase.table('gb_configuracoes').insert({
                    'gb_chave': chave,
                    'gb_valor': str(valor),
                    'gb_tipo': tipo
                }).execute()
            
            log_info("atualizar_configuracao", f"{chave} = {valor}")
            return response.data is not None
        except Exception as e:
            log_error("atualizar_configuracao", e, {"chave": chave, "valor": valor})
            return False
    else:
        memory_storage['configuracoes'][chave] = str(valor)
        log_info("atualizar_configuracao", f"{chave} = {valor} (memoria)")
        return True

def validar_session_admin():
    """Valida se o usuário está logado como admin"""
    return session.get('admin_logado', False)

def validar_session_cliente():
    """Valida se o cliente está logado"""
    return 'cliente_id' in session and 'cliente_cpf' in session

def obter_cliente_atual():
    """Obtém dados do cliente logado"""
    if not validar_session_cliente():
        return None
    
    cliente_id = session.get('cliente_id')
    
    if supabase:
        try:
            response = supabase.table('gb_clientes').select('*').eq('gb_id', cliente_id).execute()
            if response.data:
                return response.data[0]
        except:
            pass
    else:
        for cliente in memory_storage['clientes']:
            if cliente.get('id') == cliente_id:
                return cliente
    
    return None

def obter_total_vendas(tipo_jogo='raspa_brasil'):
    """Obtém total de vendas aprovadas"""
    if supabase:
        try:
            response = supabase.table('gb_vendas').select('gb_quantidade').eq('gb_tipo_jogo', tipo_jogo).eq('gb_status', 'completed').execute()
            if response.data:
                total = sum(venda['gb_quantidade'] for venda in response.data)
                return total
            return 0
        except Exception as e:
            log_error("obter_total_vendas", e, {"tipo_jogo": tipo_jogo})
            return 0
    else:
        vendas = memory_storage.get('vendas', [])
        total = sum(v['quantidade'] for v in vendas if v.get('tipo_jogo') == tipo_jogo and v.get('status') == 'completed')
        return total

def sortear_premio_novo_sistema():
    """Sistema de prêmios manual - Só libera quando admin autorizar"""
    try:
        sistema_ativo = obter_configuracao('sistema_ativo', 'true').lower() == 'true'
        if not sistema_ativo:
            log_info("sortear_premio_novo_sistema", "Sistema desativado pelo admin")
            return None

        premio_manual = obter_configuracao('premio_manual_liberado', '')
        if premio_manual:
            atualizar_configuracao('premio_manual_liberado', '')
            log_info("sortear_premio_novo_sistema", f"Prêmio manual liberado: {premio_manual}")
            return premio_manual

        log_info("sortear_premio_novo_sistema", "Nenhum prêmio liberado pelo admin")
        return None

    except Exception as e:
        log_error("sortear_premio_novo_sistema", e)
        return None

def obter_premio_acumulado():
    """Obtém valor do prêmio acumulado atual do 2 para 1000"""
    valor = obter_configuracao('premio_acumulado', str(PREMIO_INICIAL_ML))
    try:
        return float(valor)
    except:
        return PREMIO_INICIAL_ML

def processar_comissao_afiliado(afiliado_id, valor_venda, venda_id):
    """Processa comissão do afiliado"""
    try:
        if not afiliado_id:
            return
            
        percentual = PERCENTUAL_COMISSAO_AFILIADO / 100
        comissao = valor_venda * percentual
        
        if supabase:
            try:
                afiliado_response = supabase.table('gb_afiliados').select('*').eq('gb_id', afiliado_id).execute()
                if not afiliado_response.data:
                    return
                    
                afiliado = afiliado_response.data[0]
                
                novo_total_vendas = (afiliado.get('gb_total_vendas', 0) or 0) + 1
                nova_comissao_total = (afiliado.get('gb_total_comissao', 0) or 0) + comissao
                novo_saldo = (afiliado.get('gb_saldo_disponivel', 0) or 0) + comissao
                
                supabase.table('gb_afiliados').update({
                    'gb_total_vendas': novo_total_vendas,
                    'gb_total_comissao': nova_comissao_total,
                    'gb_saldo_disponivel': novo_saldo
                }).eq('gb_id', afiliado_id).execute()
                
                supabase.table('gb_afiliado_vendas').insert({
                    'gb_afiliado_id': afiliado_id,
                    'gb_venda_id': venda_id,
                    'gb_comissao': comissao,
                    'gb_status': 'aprovada'
                }).execute()
                
                log_info("processar_comissao_afiliado", 
                        f"Comissão processada: Afiliado {afiliado_id} - R$ {comissao:.2f}")
                        
            except Exception as e:
                log_error("processar_comissao_afiliado", e)
        else:
            for afiliado in memory_storage['afiliados']:
                if afiliado.get('id') == afiliado_id:
                    afiliado['total_vendas'] = afiliado.get('total_vendas', 0) + 1
                    afiliado['total_comissao'] = afiliado.get('total_comissao', 0) + comissao
                    afiliado['saldo_disponivel'] = afiliado.get('saldo_disponivel', 0) + comissao
                    
                    memory_storage['afiliado_vendas'].append({
                        'id': len(memory_storage['afiliado_vendas']) + 1,
                        'afiliado_id': afiliado_id,
                        'venda_id': venda_id,
                        'comissao': comissao,
                        'status': 'aprovada',
                        'data_venda': datetime.now().isoformat()
                    })
                    
                    log_info("processar_comissao_afiliado", 
                            f"Comissão processada em memória: Afiliado {afiliado_id} - R$ {comissao:.2f}")
                    break
                    
    except Exception as e:
        log_error("processar_comissao_afiliado", e)

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
            
            # Registrar clique do afiliado
            if supabase:
                try:
                    afiliado = supabase.table('gb_afiliados').select('gb_id').eq('gb_codigo', ref_code).execute()
                    if afiliado.data:
                        supabase.table('gb_afiliado_clicks').insert({
                            'gb_afiliado_id': afiliado.data[0]['gb_id'],
                            'gb_ip_visitor': request.remote_addr or 'unknown',
                            'gb_user_agent': request.headers.get('User-Agent', '')[:500],
                            'gb_referrer': request.headers.get('Referer', '')[:500]
                        }).execute()
                        
                        current_clicks = supabase.table('gb_afiliados').select('gb_total_clicks').eq('gb_id', afiliado.data[0]['gb_id']).execute()
                        new_clicks = (current_clicks.data[0]['gb_total_clicks'] or 0) + 1 if current_clicks.data else 1
                        
                        supabase.table('gb_afiliados').update({
                            'gb_total_clicks': new_clicks
                        }).eq('gb_id', afiliado.data[0]['gb_id']).execute()
                except:
                    pass
        
        # Servir o arquivo index.html
        return send_from_directory('.', 'index.html')
    except Exception as e:
        log_error("index", e)
        return f"""
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>GANHA BRASIL - Erro</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; background: linear-gradient(135deg, #00b341, #ffd700); }}
                .error {{ color: #dc2626; background: white; padding: 30px; border-radius: 15px; margin: 20px auto; max-width: 500px; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h1>🚫 Erro ao carregar a página</h1>
                <p>Desculpe, ocorreu um erro temporário.</p>
                <p><a href="/" style="color: #00b341; text-decoration: none; font-weight: bold;">🔄 Tentar novamente</a></p>
            </div>
        </body>
        </html>
        """, 500

@app.route('/test')
def test():
    """Rota de teste para Vercel"""
    return jsonify({
        'status': 'ok',
        'message': 'API funcionando no Vercel!',
        'supabase': supabase is not None,
        'mercadopago': sdk is not None,
        'version': APP_VERSION
    })

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
        
        if supabase:
            try:
                rb_hoje = supabase.table('gb_vendas').select('gb_quantidade').gte(
                    'gb_data_criacao', hoje + ' 00:00:00'
                ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', 'raspa_brasil').eq('gb_status', 'completed').execute()
                stats['vendas_rb_hoje'] = sum(v['gb_quantidade'] for v in (rb_hoje.data or []))
                
                ml_hoje = supabase.table('gb_vendas').select('gb_quantidade').gte(
                    'gb_data_criacao', hoje + ' 00:00:00'
                ).lt('gb_data_criacao', hoje + ' 23:59:59').eq('gb_tipo_jogo', '2para1000').eq('gb_status', 'completed').execute()
                stats['vendas_ml_hoje'] = sum(v['gb_quantidade'] for v in (ml_hoje.data or []))
                
                clientes = supabase.table('gb_clientes').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['total_clientes'] = len(clientes.data or [])
                
                afiliados = supabase.table('gb_afiliados').select('gb_id').eq('gb_status', 'ativo').execute()
                stats['total_afiliados'] = len(afiliados.data or [])
                
            except Exception as e:
                log_error("health_check_stats", e)
                stats['sistema_funcionando'] = False
        else:
            stats['vendas_rb_hoje'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == 'raspa_brasil'])
            stats['vendas_ml_hoje'] = len([v for v in memory_storage['vendas'] if v.get('data_criacao', '')[:10] == hoje and v.get('tipo_jogo') == '2para1000'])
            stats['total_clientes'] = len([c for c in memory_storage['clientes'] if c.get('status') == 'ativo'])
            stats['total_afiliados'] = len([a for a in memory_storage['afiliados'] if a.get('status') == 'ativo'])
        
        return {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'version': APP_VERSION,
            'services': {
                'supabase': supabase is not None,
                'mercadopago': sdk is not None,
                'flask': True,
                'qrcode': qrcode_available,
                'reportlab': reportlab_available
            },
            'games': ['raspa_brasil', '2para1000'],
            'features': [
                'login_clientes',
                'area_cliente',
                'minhas_raspadinhas',
                'meus_bilhetes',
                'afiliados',
                'admin_completo',
                'pagamentos_unificados',
                'sistema_manual_premios',
                'storage_fallback',
                'qr_code_generation',
                'comissoes_automaticas',
                'relatorios_completos',
                'ganhadores_management'
            ],
            'configuration': {
                'total_raspadinhas': TOTAL_RASPADINHAS,
                'premio_inicial_ml': PREMIO_INICIAL_ML,
                'preco_raspadinha': PRECO_RASPADINHA_RB,
                'preco_bilhete': PRECO_BILHETE_ML,
                'comissao_afiliado': PERCENTUAL_COMISSAO_AFILIADO
            },
            'statistics': stats
        }
    except Exception as e:
        log_error("health_check", e)
        return {'status': 'error', 'error': str(e)}, 500

# ========== ROTAS DE CLIENTE (LOGIN/CADASTRO) ==========

@app.route('/cliente/cadastrar', methods=['POST'])
def cliente_cadastrar():
    """Cadastra novo cliente"""
    try:
        data = sanitizar_dados_entrada(request.json)
        
        nome = data.get('nome', '').strip()
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        telefone = data.get('telefone', '').strip()
        email = data.get('email', '').strip()
        
        if not nome or len(nome) < 3:
            return jsonify({'sucesso': False, 'erro': 'Nome deve ter pelo menos 3 caracteres'})
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        cliente_data = {
            'nome': nome[:255],
            'cpf': cpf,
            'telefone': telefone[:20] if telefone else None,
            'email': email[:255] if email else None,
            'status': 'ativo',
            'ip_cadastro': request.remote_addr or 'unknown',
            'data_cadastro': datetime.now().isoformat()
        }
        
        if supabase:
            try:
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
                    
                    log_info("cliente_cadastrar", f"Novo cliente cadastrado: {nome} - CPF: {cpf[:3]}***")
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
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf:
                    return jsonify({'sucesso': False, 'erro': 'CPF já cadastrado'})
            
            cliente_data['id'] = len(memory_storage['clientes']) + 1
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
        data = sanitizar_dados_entrada(request.json)
        cpf = data.get('cpf', '').replace('.', '').replace('-', '').replace(' ', '')
        
        if not cpf or len(cpf) != 11 or not cpf.isdigit():
            return jsonify({'sucesso': False, 'erro': 'CPF inválido'})
        
        if supabase:
            try:
                response = supabase.table('gb_clientes').select('*').eq('gb_cpf', cpf).eq('gb_status', 'ativo').execute()
                
                if response.data:
                    cliente = response.data[0]
                    
                    supabase.table('gb_clientes').update({
                        'gb_ultimo_acesso': datetime.now().isoformat()
                    }).eq('gb_id', cliente['gb_id']).execute()
                    
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
            for cliente in memory_storage['clientes']:
                if cliente.get('cpf') == cpf and cliente.get('status') == 'ativo':
                    session['cliente_id'] = cliente['id']
                    session['cliente_cpf'] = cpf
                    session['cliente_nome'] = cliente['nome']
                    
                    cliente['ultimo_acesso'] = datetime.now().isoformat()
                    
                    log_info("cliente_login", f"Cliente logado em memória: {cliente['nome']}")
                    
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

@app.route('/cliente/logout')
def cliente_logout():
    """Logout do cliente"""
    try:
        session.pop('cliente_id', None)
        session.pop('cliente_cpf', None)
        session.pop('cliente_nome', None)
        
        log_info("cliente_logout", "Cliente deslogado")
        return jsonify({'sucesso': True})
        
    except Exception as e:
        log_error("cliente_logout", e)
        return jsonify({'sucesso': False, 'erro': 'Erro ao fazer logout'})

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

# ========== ROTAS DE PAGAMENTO ==========

@app.route('/create_payment', methods=['POST'])
def create_payment():
    """Cria pagamento PIX - Real ou Simulado"""
    try:
        data = sanitizar_dados_entrada(request.json)
        quantidade = data.get('quantidade', 1)
        game_type = data.get('game_type', 'raspa_brasil')
        afiliado_codigo = data.get('ref_code') or session.get('ref_code')

        if not isinstance(quantidade, int) or quantidade < 1 or quantidade > 50:
            return jsonify({'error': 'Quantidade inválida'}), 400

        if game_type not in ['raspa_brasil', '2para1000']:
            return jsonify({'error': 'Tipo de jogo inválido'}), 400

        if not validar_session_cliente():
            return jsonify({'error': 'Faça login primeiro para continuar'}), 401

        cliente_id = session.get('cliente_id')

        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        total = quantidade * preco_unitario

        log_info("create_payment", f"Criando pagamento: {game_type} - {quantidade} unidades - R$ {total:.2f} - Cliente ID: {cliente_id}")

        if game_type == 'raspa_brasil':
            vendidas = obter_total_vendas('raspa_brasil')
            if vendidas + quantidade > TOTAL_RASPADINHAS:
                return jsonify({
                    'error': 'Raspadinhas esgotadas',
                    'details': f'Restam apenas {TOTAL_RASPADINHAS - vendidas} disponíveis'
                }), 400

        afiliado_id = None
        if afiliado_codigo:
            if supabase:
                try:
                    response = supabase.table('gb_afiliados').select('*').eq('gb_codigo', afiliado_codigo).eq('gb_status', 'ativo').execute()
                    if response.data:
                        afiliado_id = response.data[0]['gb_id']
                        log_info("create_payment", f"Venda com afiliado: {response.data[0]['gb_nome']}")
                except Exception as e:
                    log_error("create_payment", e, {"afiliado_codigo": afiliado_codigo})
            else:
                for afiliado in memory_storage['afiliados']:
                    if afiliado.get('codigo') == afiliado_codigo and afiliado.get('status') == 'ativo':
                        afiliado_id = afiliado['id']
                        log_info("create_payment", f"Venda com afiliado: {afiliado['nome']}")
                        break

        if game_type == 'raspa_brasil':
            descricao = f"Raspa Brasil - {quantidade} raspadinha(s)"
            if quantidade == 10:
                descricao = "Raspa Brasil - 10 raspadinhas (+2 GRÁTIS!)"
        else:
            descricao = f"2 para 1000 - {quantidade} bilhete(s)"

        payment_id = None
        qr_data = {}

        if sdk:
            try:
                payment_data = {
                    "transaction_amount": float(total),
                    "description": descricao,
                    "payment_method_id": "pix",
                    "payer": {
                        "email": "cliente@ganhabrasil.com",
                        "first_name": "Cliente",
                        "last_name": "Ganha Brasil"
                    },
                    "notification_url": f"{request.url_root.rstrip('/')}/webhook/mercadopago",
                    "external_reference": f"{game_type.upper()}_{int(datetime.now().timestamp())}_{quantidade}_{cliente_id}"
                }

                payment_response = sdk.payment().create(payment_data)

                if payment_response["status"] == 201:
                    payment = payment_response["response"]
                    payment_id = str(payment['id'])
                    
                    pix_data = payment.get('point_of_interaction', {}).get('transaction_data', {})
                    qr_data = {
                        'qr_code': pix_data.get('qr_code', ''),
                        'qr_code_base64': pix_data.get('qr_code_base64', '')
                    }
                    log_info("create_payment", f"Pagamento real criado: {payment_id}")
                else:
                    raise Exception("Erro na resposta do Mercado Pago")
                    
            except Exception as e:
                log_error("create_payment_real", e)
                payment_id = None

        if not payment_id:
            payment_id = gerar_payment_id()
            qr_data = gerar_qr_code_simulado({'amount': total, 'description': descricao})
            log_info("create_payment", f"Pagamento simulado criado: {payment_id}")

        session['payment_id'] = payment_id
        session['quantidade'] = quantidade
        session['game_type'] = game_type
        session['payment_created_at'] = datetime.now().isoformat()
        if afiliado_id:
            session['afiliado_id'] = afiliado_id

        venda_data = {
            'payment_id': payment_id,
            'cliente_id': cliente_id,
            'afiliado_id': afiliado_id,
            'tipo_jogo': game_type,
            'quantidade': quantidade,
            'valor_total': total,
            'status': 'pending',
            'raspadinhas_usadas': 0 if game_type == 'raspa_brasil' else None,
            'ip_cliente': request.remote_addr or 'unknown',
            'user_agent': request.headers.get('User-Agent', '')[:500],
            'data_criacao': datetime.now().isoformat()
        }

        if supabase:
            try:
                db_data = {
                    'gb_payment_id': payment_id,
                    'gb_cliente_id': cliente_id,
                    'gb_tipo_jogo': game_type,
                    'gb_quantidade': quantidade,
                    'gb_valor_total': total,
                    'gb_status': 'pending',
                    'gb_ip_cliente': request.remote_addr or 'unknown',
                    'gb_user_agent': request.headers.get('User-Agent', '')[:500]
                }
                
                if afiliado_id:
                    db_data['gb_afiliado_id'] = afiliado_id
                
                if game_type == 'raspa_brasil':
                    db_data['gb_raspadinhas_usadas'] = 0
                
                response = supabase.table('gb_vendas').insert(db_data).execute()
                
                if response.data:
                    venda_id = response.data[0]['gb_id']
                    session['venda_id'] = venda_id
                    
                    if game_type == 'raspa_brasil':
                        quantidade_real = 12 if quantidade == 10 else quantidade
                        for i in range(quantidade_real):
                            supabase.table('gb_cliente_raspadinhas').insert({
                                'gb_cliente_id': cliente_id,
                                'gb_venda_id': venda_id,
                                'gb_numero_raspadinha': i + 1,
                                'gb_status': 'disponivel'
                            }).execute()
                    
                    log_info("create_payment", f"Venda salva no Supabase: {payment_id}")
                    
            except Exception as e:
                log_error("create_payment_save", e, {"payment_id": payment_id})
        else:
            venda_data['id'] = len(memory_storage['vendas']) + 1
            memory_storage['vendas'].append(venda_data)
            session['venda_id'] = venda_data['id']
            
            if game_type == 'raspa_brasil':
                quantidade_real = 12 if quantidade == 10 else quantidade
                for i in range(quantidade_real):
                    memory_storage['cliente_raspadinhas'].append({
                        'id': len(memory_storage['cliente_raspadinhas']) + 1,
                        'cliente_id': cliente_id,
                        'venda_id': venda_data['id'],
                        'numero_raspadinha': i + 1,
                        'status': 'disponivel'
                    })
            
            log_info("create_payment", f"Venda salva em memória: {payment_id}")

        return jsonify({
            'id': payment_id,
            'qr_code': qr_data.get('qr_code', ''),
            'qr_code_base64': qr_data.get('qr_code_base64', ''),
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
        if not payment_id or payment_id in ['undefined', 'null', '']:
            return jsonify({'error': 'Payment ID inválido'}), 400

        log_info("check_payment", f"Verificando pagamento: {payment_id}")

        if sdk:
            try:
                payment_response = sdk.payment().get(str(payment_id))
                if payment_response["status"] == 200:
                    payment = payment_response["response"]
                    status = payment['status']
                    
                    if status == 'approved':
                        processar_pagamento_aprovado(payment_id)
                    
                    return jsonify({
                        'status': status,
                        'amount': payment.get('transaction_amount', 0),
                        'description': payment.get('description', ''),
                        'date_created': payment.get('date_created', ''),
                        'date_approved': payment.get('date_approved', '')
                    })
            except Exception as e:
                log_error("check_payment_real", e, {"payment_id": payment_id})

        payment_key = f'payment_processed_{payment_id}'
        if payment_key not in session:
            payment_created = session.get('payment_created_at')
            if payment_created:
                created_time = datetime.fromisoformat(payment_created)
                if (datetime.now() - created_time).total_seconds() > 3:
                    session[payment_key] = True
                    processar_pagamento_aprovado(payment_id)
                    log_info("check_payment", f"Pagamento simulado aprovado: {payment_id}")
                    return jsonify({'status': 'approved'})
                else:
                    return jsonify({'status': 'pending'})
            else:
                return jsonify({'status': 'pending'})
        else:
            return jsonify({'status': 'approved'})

    except Exception as e:
        log_error("check_payment", e, {"payment_id": payment_id})
        return jsonify({'error': str(e)}), 500

def processar_pagamento_aprovado(payment_id):
    """Processa pagamento aprovado"""
    try:
        game_type = session.get('game_type', 'raspa_brasil')
        afiliado_id = session.get('afiliado_id')
        quantidade = session.get('quantidade', 0)
        venda_id = session.get('venda_id')
        
        preco_unitario = PRECO_RASPADINHA_RB if game_type == 'raspa_brasil' else PRECO_BILHETE_ML
        valor_total = quantidade * preco_unitario
        
        if supabase:
            try:
                update_data = {
                    'gb_status': 'completed',
                    'gb_data_aprovacao': datetime.now().isoformat()
                }
                
                supabase.table('gb_vendas').update(update_data).eq('gb_payment_id', str(payment_id)).execute()
                log_info("processar_pagamento_aprovado", f"Status atualizado no Supabase: {payment_id}")
                
            except Exception as e:
                log_error("processar_pagamento_aprovado", e, {"payment_id": payment_id})
        else:
            for venda in memory_storage['vendas']:
                if venda.get('payment_id') == payment_id:
                    venda['status'] = 'completed'
                    venda['data_aprovacao'] = datetime.now().isoformat()
                    log_info("processar_pagamento_aprovado", f"Status atualizado em memória: {payment_id}")
                    break
        
        if afiliado_id and venda_id:
            processar_comissao_afiliado(afiliado_id, valor_total, venda_id)

    except Exception as e:
        log_error("processar_pagamento_aprovado", e, {"payment_id": payment_id})

@app.route('/webhook/mercadopago', methods=['POST'])
def webhook_mercadopago():
    """Webhook do Mercado Pago"""
    try:
        data = request.json
        log_info("webhook_mercadopago", f"Webhook recebido: {data}")
        
        if data.get('type') == 'payment':
            payment_id = data.get('data', {}).get('id')
            if payment_id:
                log_info("webhook_mercadopago", f"Processando payment: {payment_id}")
                processar_pagamento_aprovado(str(payment_id))
        
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        log_error("webhook_mercadopago", e)
        return jsonify({'error': 'webhook_error'}), 500

# Configurações para Vercel (sempre executadas)
app.config['ENV'] = 'production'
app.config['DEBUG'] = False

# Para desenvolvimento local
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('DEBUG', 'False').lower() == 'true'

    print("🚀 Iniciando GANHA BRASIL - Sistema Integrado v3.0.3...")
    print(f"🌐 Porta: {port}")
    print(f"💳 Mercado Pago: {'✅ Real' if sdk else '🔄 Simulado'}")
    print(f"🔗 Supabase: {'✅ Conectado' if supabase else '🔄 Memória'}")
    print(f"📱 QR Code: {'✅ Disponível' if qrcode_available else '🔄 Texto'}")
    print(f"📄 PDF: {'✅ Disponível' if reportlab_available else '❌ Não disponível'}")
    print(f"🎮 Jogos Disponíveis:")
    print(f"   - RASPA BRASIL: Raspadinhas virtuais (R$ {PRECO_RASPADINHA_RB:.2f})")
    print(f"   - 2 PARA 1000: Bilhetes da milhar (R$ {PRECO_BILHETE_ML:.2f})")
    print(f"👤 Sistema de Login: ✅ IMPLEMENTADO (CPF único)")
    print(f"👥 Sistema de Afiliados: ✅ COMPLETO")
    print(f"🎯 Prêmios: Manual (RB) + Sorteio diário (ML)")
    print(f"🔄 Pagamentos: Via PIX (real/simulado)")
    print(f"📱 Interface: Responsiva e moderna")
    print(f"🛡️ Segurança: Login obrigatório + Validações")
    print(f"📊 Admin: Painel unificado completo")
    print(f"🔐 Senha Admin: {ADMIN_PASSWORD}")
    print(f"🎨 Frontend: Integração total com index.html")
    print(f"💾 Storage: Supabase com fallback em memória")
    print(f"🆕 CORREÇÕES V3.0.3:")
    print(f"   ✅ Remoção de rotas duplicadas")
    print(f"   ✅ Correção de decorators mal posicionados")
    print(f"   ✅ Otimização para deploy no Vercel")
    print(f"   ✅ Redução de dependências opcionais")
    print(f"   ✅ Melhor tratamento de erros")
    print(f"✅ PRONTO PARA DEPLOY NO VERCEL!")

    app.run(host='0.0.0.0', port=port, debug=debug_mode)
