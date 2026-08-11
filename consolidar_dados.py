#!/usr/bin/env python3
import os
import re
import json
import csv
import unicodedata
import sys
from difflib import SequenceMatcher

# Tenta importar pandas e bibliotecas do Google. Se não conseguir, avisa ou instala.
try:
    import pandas as pd
except ImportError:
    print("Aviso: pandas não está instalado. Por favor, instale usando: pip install pandas")
    pd = None

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("Aviso: gspread ou google-auth não estão instalados. O download automático do Google Sheets não funcionará.")
    gspread = None

# Configurações do Google Sheets
SPREADSHEET_ID = "13yzhG3Ae3L0-wFh-UQ7QF_3Jfe__Prh7bGhWJDF3lZ8"
WORKSHEET_GID = "304698461"
CREDENTIALS_FILE = "credentials.json"
# Nomes alternativos aceitos (o workflow do GitHub Actions grava google_credentials.json)
CREDENTIALS_FILE_ALTS = ["credentials.json", "google_credentials.json"]
LOCAL_CADASTRO_CSV = "cadastro_escolas.csv"
CONFIRMADOS_CSV = "Resultado_TOEIC_Ofício - Página1.csv"
OUTPUT_HTML = "comparativo_toeic.html"
TEMPLATE_HTML = "comparativo_toeic_template.html"

def normalize_name(name):
    if not name or not isinstance(name, str):
        return ""
    # Maiúsculas
    name = name.upper()
    # Remove acentos
    name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn')
    # Substitui pontuações por espaço
    name = re.sub(r'[.\-,\/()\[\]]', ' ', name)
    # Remove palavras comuns de tipos de escola para focar no nome próprio
    palavras_remover = [
        r'\bCOLEGIO ESTADUAL\b', r'\bC E DO CAMPO\b', r'\bC E C\b', r'\bC E\b', 
        r'\bEEB\b', r'\bE E\b', r'\bE F M\b', r'\bEM PROFIS\b', r'\bETI\b', 
        r'\bPROFIS\b', r'\bPROFESSOR\b', r'\bPROF\b', r'\bPROFA\b', r'\bDR\b', 
        r'\bDRA\b', r'\bPE\b', r'\bPADRE\b', r'\bDONA\b', r'\bMAIOR\b', 
        r'\bVER\b', r'\bCEL\b', r'\bGEN\b', r'\bGAL\b', r'\bMAL\b', 
        r'\bSEN\b', r'\bDEP\b', r'\bPRES\b', r'\bMONS\b', r'\bCOLEGIO\b', 
        r'\bESCOLA\b', r'\bESTADUAL\b', r'\bMUNICIPAL\b', r'\bENSINO\b',
        r'\bMEDIO\b', r'\bFUNDAMENTAL\b', r'\bINTEGRAL\b',
        r'\bEFMP\b', r'\bEFM\b', r'\bEM\b', r'\bEF\b', r'\bE F M P\b', r'\bEF M\b'
    ]
    for termo in palavras_remover:
        name = re.sub(termo, ' ', name)
    # Remove múltiplos espaços e espaços no início/fim
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def nre_matches(nre1, nre2):
    if not nre1 or not nre2:
        return False
    def clean(n):
        n = ''.join(c for c in unicodedata.normalize('NFD', n) if unicodedata.category(c) != 'Mn')
        return n.upper().replace('.', ' ').replace('-', ' ').strip()
    c1 = clean(nre1)
    c2 = clean(nre2)
    # Verifica similaridade para tolerar pequenos erros de digitação (ex: LOANDRA vs LOANDA)
    if SequenceMatcher(None, c1, c2).ratio() > 0.8:
        return True
    words1 = set(c1.split())
    words2 = set(c2.split())
    if ("NORTE" in words1 and "NORTE" in words2) and ("METROP" in c1 or "METROPOLITANA" in c1) and ("METROP" in c2 or "METROPOLITANA" in c2):
        return True
    if ("SUL" in words1 and "SUL" in words2) and ("METROP" in c1 or "METROPOLITANA" in c1) and ("METROP" in c2 or "METROPOLITANA" in c2):
        return True
    common = {"AREA", "NRE", "DE", "DA", "DO"}
    w1 = words1 - common
    w2 = words2 - common
    if w1.intersection(w2):
        return True
    return False

def clean_column_name(col):
    return normalize_name(col).lower()

def extract_contacts(item):
    rt = ""
    suporte = ""
    aplicadores = []
    
    # RT
    rt_val = item.get('Nome completo do/a responsável pelo teste (RT)', '')
    if rt_val and str(rt_val).lower().strip() != 'nan':
        rt = str(rt_val).strip()
        
    # Suporte
    sup_val = item.get('Nome completo do/a  responsável de suporte técnico e infraestrutura', '')
    if not sup_val:
        # fallback para diferentes espaçamentos
        for k, v in item.items():
            k_clean = re.sub(r'\s+', ' ', k).strip().lower()
            if 'responsavel de suporte tecnico' in k_clean or 'responsavel de suporte tecnico e infraestrutura' in k_clean:
                sup_val = v
                break
    if sup_val and str(sup_val).lower().strip() != 'nan':
        suporte = str(sup_val).strip()
        
    # Aplicadores
    # Primeiro, verifica se o RT também é aplicador:
    rt_is_aplicador = item.get('Este RT também exercerá a função de aplicador?', '')
    if rt_is_aplicador and str(rt_is_aplicador).strip().lower() in ['sim', 's', 'yes']:
        if rt:
            aplicadores.append(rt)
            
    # Depois, pega os outros aplicadores das colunas específicas
    for k, v in item.items():
        k_clean = re.sub(r'\s+', ' ', k).strip().lower()
        if k_clean.startswith('nome completo do/a aplicador/a') or k_clean.startswith('nome completo do/a aplicador/a_'):
            if v and str(v).lower().strip() != 'nan':
                v_str = str(v).strip()
                if v_str and v_str not in aplicadores:
                    aplicadores.append(v_str)
                    
    # Extra aplicadores
    extra_ap = item.get('Caso você tenha mais algum/a aplicador/a a ser indicado, indique no campo abaixo nome completo, cargo, email institucional e CPF.', '')
    if extra_ap and str(extra_ap).lower().strip() != 'nan' and str(extra_ap).strip() != '':
        extra_ap = str(extra_ap).strip()
    else:
        extra_ap = ""
        
    return {
        'rt': rt,
        'suporte': suporte,
        'aplicadores': aplicadores,
        'extra_aplicadores': extra_ap
    }

def detect_columns(df):
    school_col = None
    nre_col = None
    city_col = None
    
    for col in df.columns:
        clean = clean_column_name(col)
        if 'escola' in clean or 'school' in clean or 'nome' in clean:
            school_col = col
            break
    for col in df.columns:
        clean = clean_column_name(col)
        if 'nre' in clean:
            nre_col = col
            break
    for col in df.columns:
        clean = clean_column_name(col)
        if 'municip' in clean or 'cidade' in clean or 'city' in clean:
            city_col = col
            break
            
    # Fallback
    if not school_col and len(df.columns) > 0:
        school_col = df.columns[0]
    return school_col, nre_col, city_col

def make_headers_unique(headers):
    seen = {}
    unique_headers = []
    for header in headers:
        header_str = str(header).strip()
        if not header_str:
            header_str = "col_empty"
        if header_str in seen:
            seen[header_str] += 1
            unique_headers.append(f"{header_str}_{seen[header_str]}")
        else:
            seen[header_str] = 0
            unique_headers.append(header_str)
    return unique_headers

def get_school_name_from_row(row):
    for col, val in row.items():
        col_lower = col.lower()
        if col_lower.startswith('nre - ') and 'unidade de' in col_lower:
            val_str = str(val).strip()
            if val_str and val_str != 'nan' and val_str != '':
                return val_str
    return None

def get_city_from_row(row):
    for col, val in row.items():
        col_lower = col.lower()
        if col_lower.startswith('municip'):
            val_str = str(val).strip()
            if val_str and val_str != 'nan' and val_str != '':
                return val_str
    return None

def obter_credenciais(scopes):
    """Resolve as credenciais da conta de serviço a partir do ambiente ou de um arquivo local.

    Ordem de preferência:
    1. Variável de ambiente GOOGLE_SERVICE_ACCOUNT_KEY com o JSON da chave (usada em CI/Netlify,
       onde o arquivo de credenciais não existe porque está no .gitignore).
    2. Arquivo local, aceitando os nomes de CREDENTIALS_FILE_ALTS.
    """
    key_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_KEY', '').strip()
    if key_json:
        print("Usando credenciais da variável de ambiente GOOGLE_SERVICE_ACCOUNT_KEY...")
        return Credentials.from_service_account_info(json.loads(key_json), scopes=scopes)

    for caminho in CREDENTIALS_FILE_ALTS:
        if os.path.exists(caminho):
            print(f"Usando credenciais do arquivo {caminho}...")
            return Credentials.from_service_account_file(caminho, scopes=scopes)

    return None

def carregar_cadastros():
    """Tenta carregar os cadastros do Google Sheets ou de um CSV local."""
    df_cadastros = None

    # Método 1: Tenta Google Sheets via Conta de Serviço
    if gspread:
        print("Tentando baixar dados do Google Sheets...")
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            creds = obter_credenciais(scopes)
            if creds is None:
                raise RuntimeError(
                    "Nenhuma credencial encontrada (defina GOOGLE_SERVICE_ACCOUNT_KEY ou "
                    f"crie um destes arquivos: {', '.join(CREDENTIALS_FILE_ALTS)})"
                )
            client = gspread.authorize(creds)
            
            sh = client.open_by_key(SPREADSHEET_ID)
            # Encontra a aba pela GID
            wks = None
            for sheet in sh.worksheets():
                if str(sheet.id) == WORKSHEET_GID:
                    wks = sheet
                    break
            if not wks:
                wks = sh.get_worksheet(0)
                
            values = wks.get_all_values()
            if values:
                headers = make_headers_unique(values[0])
                df_cadastros = pd.DataFrame(values[1:], columns=headers)
            else:
                df_cadastros = pd.DataFrame()
            print(f"Planilha baixada com sucesso! {len(df_cadastros)} registros encontrados.")
            # Salva uma cópia local para cache/segurança
            df_cadastros.to_csv(LOCAL_CADASTRO_CSV, index=False)
        except Exception as e:
            print(f"Erro ao baixar do Google Sheets: {e}")
            print("Tentando usar arquivo local de backup...")

    # Método 2: Tenta ler arquivo CSV local
    if df_cadastros is None:
        if os.path.exists(LOCAL_CADASTRO_CSV):
            print(f"Carregando dados locais do arquivo {LOCAL_CADASTRO_CSV}...")
            if pd:
                df_cadastros = pd.read_csv(LOCAL_CADASTRO_CSV)
            else:
                # Fallback sem pandas
                with open(LOCAL_CADASTRO_CSV, mode='r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    records = list(reader)
                    df_cadastros = records
        else:
            print(f"Erro: Nenhum dado de cadastro encontrado. Coloque um arquivo '{LOCAL_CADASTRO_CSV}' na pasta ou configure as credenciais.")

    return df_cadastros

def processar_dados():
    # Extrai o mapeamento de escolas para cidades a partir do mapa original
    school_to_city_map = {}
    original_map_path = "mapa_toeic_pr.html"
    if os.path.exists(original_map_path):
        try:
            with open(original_map_path, "r", encoding="utf-8") as f:
                content = f.read()
            match = re.search(r'const cityData = (\{.*\});', content)
            if match:
                city_data = json.loads(match.group(1))
                for city_name, city_info in city_data.items():
                    for school in city_info.get('schools', []):
                        school_name = school.get('escola')
                        norm = normalize_name(school_name)
                        if norm:
                            school_to_city_map[norm] = city_name
            print(f"Extraído mapeamento de {len(school_to_city_map)} escolas para cidades a partir de '{original_map_path}'.")
        except Exception as e:
            print(f"Erro ao extrair cidades do mapa original: {e}")

    # Carrega dados oficiais confirmados (CSV local)
    if not os.path.exists(CONFIRMADOS_CSV):
        print(f"Erro: O arquivo de confirmados '{CONFIRMADOS_CSV}' não foi encontrado.")
        sys.exit(1)
        
    print(f"Lendo escolas confirmadas de '{CONFIRMADOS_CSV}'...")
    if pd:
        df_conf = pd.read_csv(CONFIRMADOS_CSV)
        # Propaga o NRE para linhas subsequentes vazias (ffill)
        df_conf['NRE'] = df_conf['NRE'].ffill()
    else:
        # Fallback sem pandas
        df_conf = []
        current_nre = ""
        with open(CONFIRMADOS_CSV, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                nre = row.get('NRE', '').strip()
                if nre:
                    current_nre = nre
                else:
                    row['NRE'] = current_nre
                df_conf.append(row)
        df_conf = pd.DataFrame(df_conf) if pd else df_conf

    # Carrega dados do formulário de cadastro
    df_cad = carregar_cadastros()
    
    # Se não houver dados de cadastro, cria uma lista vazia ou dados mockados para testes
    if df_cad is None or (pd and df_cad.empty) or (not pd and len(df_cad) == 0):
        print("Criando dados mockados de cadastro para demonstração local...")
        # Cria alguns dados fictícios baseados nas escolas de confirmados
        mock_data = []
        # Pega as primeiras 50 escolas confirmadas e finge que algumas se cadastraram
        if pd:
            for idx, row in df_conf.head(60).iterrows():
                if idx % 5 != 0: # 80% de match
                    mock_data.append({
                        "Nome da Escola": row['ESCOLA'],
                        "NRE": row['NRE'],
                        "Município": "Cidade Teste"
                    })
            # Adiciona algumas cadastradas que NÃO estão confirmadas
            mock_data.append({"Nome da Escola": "COLEGIO ESTADUAL FALSO DE TESTE", "NRE": "APUCARANA", "Município": "APUCARANA"})
            mock_data.append({"Nome da Escola": "C E DO CAMPO DA CIDADE INEXISTENTE", "NRE": "LONDRINA", "Município": "LONDRINA"})
            df_cad = pd.DataFrame(mock_data)
        else:
            for idx, row in enumerate(df_conf[:60]):
                if idx % 5 != 0:
                    mock_data.append({
                        "Nome da Escola": row['ESCOLA'],
                        "NRE": row['NRE'],
                        "Município": "Cidade Teste"
                    })
            mock_data.append({"Nome da Escola": "COLEGIO ESTADUAL FALSO DE TESTE", "NRE": "APUCARANA", "Município": "APUCARANA"})
            df_cad = mock_data

    # Cruzamento de dados
    escolas_comparadas = []
    
    # Identifica colunas do cadastro
    if pd:
        school_col_cad, nre_col_cad, city_col_cad = detect_columns(df_cad)
        list_conf = df_conf.to_dict('records')
        list_cad = df_cad.to_dict('records')
    else:
        school_col_cad, nre_col_cad, city_col_cad = "Nome da Escola", "NRE", "Município"
        list_conf = df_conf
        list_cad = df_cad

    # Prepara lista de cadastrados normalizados para busca rápida
    cadastros_normalizados = []
    for item in list_cad:
        raw_name = get_school_name_from_row(item)
        if not raw_name:
            # Se não achou nas colunas de NRE, tenta o fallback detectado
            raw_name = item.get(school_col_cad, '')
            
        if not raw_name:
            continue
            
        # Limpa o sufixo INEP ou código se houver no nome da escola (ex: - INEP 41000000, (41000000), - 41000000)
        raw_name_clean = re.sub(r'\s*-\s*INEP\s*\d+', '', str(raw_name), flags=re.IGNORECASE).strip()
        raw_name_clean = re.sub(r'\s*\(\s*\d+\s*\)\s*$', '', raw_name_clean).strip()
        raw_name_clean = re.sub(r'\s*-\s*\d+\s*$', '', raw_name_clean).strip()
        norm_name = normalize_name(raw_name_clean)
        
        # Tenta extrair NRE e Cidade
        raw_nre = item.get('NRE', '')
        if not raw_nre:
            for col, val in item.items():
                if 'nre' in col.lower() and col.lower() != 'nre':
                    val_str = str(val).strip()
                    if val_str and val_str != 'nan' and val_str != '':
                        raw_nre = val_str
                        break
        clean_nre_val = str(raw_nre).replace('NRE -', '').replace('NRE', '').strip()
        
        cidade = get_city_from_row(item)
        if not cidade:
            cidade = item.get(city_col_cad, 'Cidade indefinida') if city_col_cad else 'Cidade indefinida'
            
        contacts = extract_contacts(item)
        
        if norm_name:
            cadastros_normalizados.append({
                'raw': item,
                'raw_name': raw_name_clean,
                'nre': clean_nre_val,
                'cidade': cidade,
                'norm_name': norm_name,
                'matched': False,
                'contacts': contacts
            })

    # Totalizadores
    total_confirmadas = len(list_conf)
    total_cadastradas = len(list_cad)
    total_both = 0

    # Passada 1: Percorre as escolas confirmadas e cruza com as cadastradas
    id_counter = 1
    for conf_row in list_conf:
        conf_school = conf_row.get('ESCOLA', '')
        conf_nre = conf_row.get('NRE', '')
        conf_students_str = conf_row.get('Total de estudantes que farão o TOIC', '0')
        
        # Converte estudantes para int com segurança
        try:
            conf_students = int(float(str(conf_students_str).replace(',', '.')))
        except ValueError:
            conf_students = 0
            
        norm_conf = normalize_name(conf_school)
        
        # Procura correspondência com validação de NRE
        match_found = None
        for cad_item in cadastros_normalizados:
            if not cad_item['matched'] and cad_item['norm_name'] == norm_conf and nre_matches(cad_item['nre'], conf_nre):
                match_found = cad_item
                break
                
        # Se não achou por igualdade exata de normalização, tenta busca por inclusão (ex: "ARTHUR DA C SILVA" em "ARTHUR DA COSTA SILVA")
        if not match_found:
            for cad_item in cadastros_normalizados:
                if not cad_item['matched']:
                    n_cad = cad_item['norm_name']
                    # Se um nome normalizado contém o outro e o tamanho é próximo
                    if (n_cad in norm_conf or norm_conf in n_cad) and abs(len(n_cad) - len(norm_conf)) < 8:
                        if nre_matches(cad_item['nre'], conf_nre):
                            match_found = cad_item
                            break

        # Tenta encontrar a cidade real associada a essa escola no mapa original
        cidade = school_to_city_map.get(norm_conf, conf_nre)

        if match_found:
            match_found['matched'] = True
            total_both += 1
            escolas_comparadas.append({
                'id': id_counter,
                'escola': conf_school,
                'nre': conf_nre,
                'cidade_planilha': cidade,
                'alunos': conf_students,
                'status': 'both',
                'contacts': match_found['contacts']
            })
        else:
            escolas_comparadas.append({
                'id': id_counter,
                'escola': conf_school,
                'nre': conf_nre,
                'cidade_planilha': cidade,
                'alunos': conf_students,
                'status': 'confirmed_only',
                'contacts': None
            })
        id_counter += 1

    # Passada 2: Adiciona as escolas que cadastraram mas NÃO foram confirmadas
    for cad_item in cadastros_normalizados:
        if not cad_item['matched']:
            escolas_comparadas.append({
                'id': id_counter,
                'escola': cad_item['raw_name'],
                'nre': cad_item['nre'] if cad_item['nre'] else 'NRE indefinido',
                'cidade_planilha': cad_item['cidade'],
                'alunos': 0,
                'status': 'registered_only',
                'contacts': cad_item['contacts']
            })
            id_counter += 1

    # Estatísticas consolidadas
    total_registered_only = total_cadastradas - total_both
    total_confirmed_only = total_confirmadas - total_both

    stats_comparativo = {
        "totalConfirmadas": total_confirmadas,
        "totalCadastradas": total_cadastradas,
        "ambas": total_both,
        "apenasCadastro": total_registered_only,
        "apenasConfirmacao": total_confirmed_only
    }

    # Salva dados na página HTML usando o template
    criar_template_padrao()
        
    with open(TEMPLATE_HTML, 'r', encoding='utf-8') as f:
        html_content = f.read()

    # Injeta os dados nas variáveis do script
    html_content = html_content.replace('/*DATA_STATS_PLACEHOLDER*/', f'const statsComparativo = {json.dumps(stats_comparativo, indent=2)};')
    html_content = html_content.replace('/*DATA_LISTA_PLACEHOLDER*/', f'const listaEscolas = {json.dumps(escolas_comparadas, indent=2)};')
    
    # Injeta a URL de Build Hook do Netlify
    build_hook_url = os.environ.get('NETLIFY_BUILD_HOOK_URL', '')
    html_content = html_content.replace('/*NETLIFY_BUILD_HOOK_URL_PLACEHOLDER*/', build_hook_url)

    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"Página comparativa gerada com sucesso: '{OUTPUT_HTML}'!")
    print(f"Estatísticas: Confirmadas={total_confirmadas} | Cadastradas={total_cadastradas} | Ambas={total_both} | Pendentes={total_registered_only}")

def criar_template_padrao():
    print(f"Criando template padrão em '{TEMPLATE_HTML}'...")
    template = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Comparativo TOEIC - Paraná</title>
  <style>
    :root {
      --bg: #f6f7f2;
      --ink: #17201d;
      --muted: #62706a;
      --line: #d9ded6;
      --panel: #ffffff;
      --panel-soft: #eef4ec;
      --accent: #087f5b;
      --accent-dark: #045c43;
      --warning: #e67e22;
      --warning-light: #fdf5eb;
      --shadow: 0 18px 50px rgba(28, 44, 37, .16);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 Inter, ui-sans-serif, system-ui, sans-serif;
    }
    .navbar {
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      padding: 14px 22px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .navbar-brand {
      font-weight: 700;
      font-size: 18px;
      color: var(--accent-dark);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .navbar-menu {
      display: flex;
      gap: 12px;
    }
    .nav-link {
      color: var(--muted);
      text-decoration: none;
      font-weight: 550;
      padding: 8px 12px;
      border-radius: 6px;
      transition: all 0.2s;
    }
    .nav-link:hover {
      color: var(--ink);
      background: var(--panel-soft);
    }
    .nav-link.active {
      color: var(--panel);
      background: var(--accent);
    }
    .container {
      max-width: 1200px;
      margin: 32px auto;
      padding: 0 22px;
    }
    .header {
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 32px;
      line-height: 1.1;
    }
    .subtitle {
      color: var(--muted);
      margin-top: 6px;
    }

    .grid-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    .card-stat {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    }
    .card-stat span {
      display: block;
      color: var(--muted);
      font-size: 13px;
    }
    .card-stat b {
      display: block;
      font-size: 28px;
      line-height: 1.1;
      margin-top: 6px;
    }
    .card-stat.both b { color: var(--accent); }
    .card-stat.pending b { color: var(--warning); }
    
    .panel-table {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 22px;
    }
    .search-input {
      flex: 1;
      min-width: 260px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      outline: none;
    }
    .search-input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(8, 127, 91, .16);
    }
    .select-filter {
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      outline: none;
      cursor: pointer;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      text-align: left;
      padding: 12px 8px;
      border-bottom: 1px solid var(--line);
    }
    th {
      font-weight: 650;
      color: var(--muted);
      background: #fbfcf8;
    }
    .badge {
      display: inline-block;
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
    }
    .badge.both {
      background: var(--panel-soft);
      color: var(--accent-dark);
      border: 1px solid #c9ded2;
    }
    .badge.registered_only {
      background: var(--warning-light);
      color: var(--warning);
      border: 1px solid #f9ebda;
    }
    .badge.confirmed_only {
      background: #f1f3f0;
      color: var(--muted);
      border: 1px solid var(--line);
    }
    
    /* Equipe / Modal / Info Button Styles */
    .btn-info-team {
      background: var(--panel-soft);
      border: 1px solid var(--accent);
      color: var(--accent);
      cursor: pointer;
      padding: 2px 6px;
      margin-left: 6px;
      vertical-align: middle;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      transition: all 0.2s;
      outline: none;
    }
    .btn-info-team:hover {
      background: var(--accent);
      color: #fff;
      transform: translateY(-1px);
    }
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.4);
      backdrop-filter: blur(4px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      animation: fadeIn 0.2s ease-out;
    }
    .modal-card {
      background: var(--panel);
      border-radius: 8px;
      width: 90%;
      max-width: 450px;
      box-shadow: var(--shadow);
      animation: slideUp 0.2s ease-out;
      border: 1px solid var(--line);
      overflow: hidden;
    }
    .modal-header {
      padding: 16px 20px;
      border-bottom: 1px solid var(--line);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--panel-soft);
    }
    .modal-header h3 {
      margin: 0;
      font-size: 14px;
      font-weight: 700;
      color: var(--accent-dark);
    }
    .modal-close {
      background: none;
      border: none;
      font-size: 24px;
      cursor: pointer;
      color: var(--muted);
      line-height: 1;
      padding: 0;
    }
    .modal-close:hover {
      color: var(--ink);
    }
    .modal-body {
      padding: 20px;
    }
    .modal-section {
      margin-bottom: 16px;
    }
    .modal-section:last-child {
      margin-bottom: 0;
    }
    .modal-section-title {
      font-weight: 700;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 6px;
    }
    .modal-section-content {
      font-size: 14px;
      color: var(--ink);
    }
    .modal-badge-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-top: 4px;
    }
    .modal-badge-item {
      background: var(--panel-soft);
      padding: 6px 10px;
      border-radius: 4px;
      font-size: 13px;
      border-left: 3px solid var(--accent);
      font-weight: 550;
    }
    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }
    @keyframes slideUp {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }
  </style>
</head>
<body>
  <nav class="navbar">
    <div class="navbar-brand">
      <span>TOEIC Paraná</span>
    </div>
    <div class="navbar-menu">
      <a href="mapa_toeic_pr.html" class="nav-link">Mapa Geral</a>
      <a href="comparativo_toeic.html" class="nav-link active">Comparativo Inscrições</a>
    </div>
  </nav>

  <main class="container">
    <header class="header">
      <div>
        <h1>Comparativo de Adesão</h1>
        <div class="subtitle">Análise de conciliação entre escolas que responderam ao formulário e a listagem homologada (oficial).</div>
      </div>
    </header>

    <section class="grid-stats">
      <div class="card-stat">
        <span>Total Cadastradas (Formulário)</span>
        <b id="statCad">0</b>
      </div>
      <div class="card-stat">
        <span>Total Confirmadas (Oficial)</span>
        <b id="statConf">0</b>
      </div>
      <div class="card-stat both">
        <span>Adesão Confirmada (Ambos)</span>
        <b id="statBoth">0</b>
      </div>
      <div class="card-stat pending">
        <span>Cadastrada, fora da lista oficial</span>
        <b id="statPend">0</b>
      </div>
      <div class="card-stat">
        <span>Sem Cadastro</span>
        <b id="statNoCad">0</b>
      </div>
    </section>

    <section class="panel-table">
      <div class="filters">
        <input type="search" id="search" class="search-input" placeholder="Buscar por escola, município ou NRE...">
        <select id="filterStatus" class="select-filter">
          <option value="all">Todos os Status</option>
          <option value="both">Confirmado & Cadastrado</option>
          <option value="registered_only">Cadastrada, fora da lista oficial</option>
          <option value="confirmed_only">Sem Cadastro</option>
        </select>
        <select id="filterNRE" class="select-filter">
          <option value="all">Todos os NREs</option>
        </select>
      </div>

      <div style="overflow-x: auto;">
        <table id="tableEscolas">
          <thead>
            <tr>
              <th>Escola</th>
              <th>Município</th>
              <th>NRE</th>
              <th>Alunos</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            <!-- Preenchido via JS -->
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <!-- Modal de Detalhes da Equipe -->
  <div id="infoModal" class="modal-overlay" style="display: none;">
    <div class="modal-card">
      <div class="modal-header">
        <h3 id="modalSchoolName">Nome da Escola</h3>
        <button onclick="closeModal()" class="modal-close">&times;</button>
      </div>
      <div class="modal-body" id="modalBody">
        <!-- Conteúdo dinâmico via JS -->
      </div>
    </div>
  </div>

  <script>
    /*DATA_STATS_PLACEHOLDER*/
    /*DATA_LISTA_PLACEHOLDER*/

    const fmt = new Intl.NumberFormat('pt-BR');

    // Inicializa Stats
    document.getElementById('statCad').textContent = fmt.format(statsComparativo.totalCadastradas);
    document.getElementById('statConf').textContent = fmt.format(statsComparativo.totalConfirmadas);
    document.getElementById('statBoth').textContent = fmt.format(statsComparativo.ambas);
    document.getElementById('statPend').textContent = fmt.format(statsComparativo.apenasCadastro);
    document.getElementById('statNoCad').textContent = fmt.format(statsComparativo.apenasConfirmacao);

    // Popula o select de NRE
    const nres = [...new Set(listaEscolas.map(e => e.nre).filter(Boolean))].sort();
    const selectNRE = document.getElementById('filterNRE');
    nres.forEach(nre => {
      const opt = document.createElement('option');
      opt.value = nre;
      opt.textContent = nre;
      selectNRE.appendChild(opt);
    });

    const statusLabels = {
      'both': 'Confirmado & Cadastrado',
      'registered_only': 'Cadastrada, fora da lista oficial',
      'confirmed_only': 'Sem Cadastro'
    };

    function esc(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
    }

    function renderTable() {
      const q = document.getElementById('search').value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
      const statusFilter = document.getElementById('filterStatus').value;
      const nreFilter = document.getElementById('filterNRE').value;
      
      const tbody = document.querySelector('#tableEscolas tbody');
      tbody.innerHTML = '';

      const filtradas = listaEscolas.filter(item => {
        // Filtro de Texto
        const textToSearch = [item.escola, item.cidade_planilha, item.nre].join(' ').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toUpperCase();
        const matchesText = !q || textToSearch.includes(q);
        
        // Filtro Status
        const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
        
        // Filtro NRE
        const matchesNRE = nreFilter === 'all' || item.nre === nreFilter;

        return matchesText && matchesStatus && matchesNRE;
      });

      filtradas.forEach(item => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>
            <div style="display: inline-flex; align-items: center; gap: 4px; max-width: 100%;">
              <span style="font-weight: 700;">${esc(item.escola)}</span>
              ${item.contacts ? `
                <button class="btn-info-team" onclick="showTeam(${item.id})" title="Ver Equipe de Aplicação">info</button>
              ` : ''}
            </div>
          </td>
          <td>${esc(item.cidade_planilha)}</td>
          <td>${esc(item.nre)}</td>
          <td>${item.alunos > 0 ? fmt.format(item.alunos) : '-'}</td>
          <td><span class="badge ${item.status}">${statusLabels[item.status]}</span></td>
        `;
        tbody.appendChild(tr);
      });
      
      if (filtradas.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--muted); padding: 24px;">Nenhuma escola corresponde aos filtros aplicados.</td></tr>`;
      }
    }

    window.showTeam = function(id) {
      const item = listaEscolas.find(e => e.id === id);
      if (!item || !item.contacts) return;
      
      document.getElementById('modalSchoolName').textContent = item.escola;
      
      const c = item.contacts;
      let html = '';
      
      // RT
      html += `
        <div class="modal-section">
          <div class="modal-section-title">Responsável pelo Teste (RT)</div>
          <div class="modal-section-content">
            ${c.rt ? `<b>${esc(c.rt)}</b>` : '<i style="color: var(--muted)">Não informado</i>'}
          </div>
        </div>
      `;
      
      // Aplicadores
      let aplicadoresHtml = '';
      if (c.aplicadores && c.aplicadores.length > 0) {
        aplicadoresHtml = `<div class="modal-badge-list">`;
        c.aplicadores.forEach(ap => {
          aplicadoresHtml += `<div class="modal-badge-item">${esc(ap)}</div>`;
        });
        aplicadoresHtml += `</div>`;
      } else {
        aplicadoresHtml = '<i style="color: var(--muted)">Nenhum cadastrado</i>';
      }
      
      html += `
        <div class="modal-section">
          <div class="modal-section-title">Aplicadores</div>
          <div class="modal-section-content">${aplicadoresHtml}</div>
        </div>
      `;
      
      // Suporte Técnico
      html += `
        <div class="modal-section">
          <div class="modal-section-title">Suporte Técnico & Infraestrutura</div>
          <div class="modal-section-content">
            ${c.suporte ? `<b>${esc(c.suporte)}</b>` : '<i style="color: var(--muted)">Não informado</i>'}
          </div>
        </div>
      `;
      
      // Observações / Extra
      if (c.extra_aplicadores) {
        html += `
          <div class="modal-section">
            <div class="modal-section-title">Aplicadores Adicionais / Observações</div>
            <div class="modal-section-content" style="white-space: pre-line; background: var(--panel-soft); padding: 8px; border-radius: 4px; font-size: 12px; max-height: 80px; overflow-y: auto; border: 1px solid var(--line);">
              ${esc(c.extra_aplicadores)}
            </div>
          </div>
        `;
      }
      
      document.getElementById('modalBody').innerHTML = html;
      document.getElementById('infoModal').style.display = 'flex';
    };

    window.closeModal = function() {
      document.getElementById('infoModal').style.display = 'none';
    };

    document.getElementById('infoModal').addEventListener('click', (e) => {
      if (e.target.id === 'infoModal') {
        closeModal();
      }
    });

    document.getElementById('search').addEventListener('input', renderTable);
    document.getElementById('filterStatus').addEventListener('change', renderTable);
    document.getElementById('filterNRE').addEventListener('change', renderTable);

    // Renderiza inicial
    renderTable();


  </script>
</body>
</html>
"""
    with open(TEMPLATE_HTML, 'w', encoding='utf-8') as f:
        f.write(template)

if __name__ == "__main__":
    processar_dados()
