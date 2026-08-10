# Mapa e Comparativo TOEIC - Paraná

Este repositório contém a aplicação para visualização do mapa de escolas do Paraná participantes do TOEIC e o dashboard comparativo entre as escolas cadastradas (via formulário) e as escolas confirmadas (oficiais).

## Estrutura do Projeto

* `mapa_toeic_pr.html`: Página do mapa interativo contendo a lista de escolas confirmadas.
* `comparativo_toeic_template.html`: Modelo base (template) para a página de comparação.
* `comparativo_toeic.html`: Página gerada automaticamente com a tabela de conciliação.
* `consolidar_dados.py`: Script Python que baixa a planilha de cadastros do Google Sheets, cruza os dados com a lista de confirmados e gera a página de comparação final.
* `Resultado_TOEIC_Ofício - Página1.csv`: Planilha oficial de escolas confirmadas e quantitativo de alunos.
* `.github/workflows/deploy.yml`: Fluxo de automação do GitHub Actions para atualização periódica e deploy no Netlify.

---

## 1. Como Executar e Testar Localmente

Se você deseja testar o cruzamento de dados localmente no seu computador sem configurar a API do Google Sheets:

1. Baixe os dados de cadastro da planilha como CSV.
2. Salve o arquivo na pasta do projeto com o nome `cadastro_escolas.csv`.
3. Certifique-se de ter o Python instalado. Se necessário, instale a biblioteca do Pandas:
   ```bash
   pip install pandas
   ```
4. Execute o script de consolidação:
   ```bash
   python3 consolidar_dados.py
   ```
5. Abra o arquivo `mapa_toeic_pr.html` ou `comparativo_toeic.html` diretamente no seu navegador para ver o resultado.

---

## 2. Configurando a Atualização Automática (Google Cloud)

Para que a automação no GitHub Actions consiga ler a sua planilha do Google Sheets privada, siga estes passos:

### Passo 2.1: Criar Conta de Serviço no Google Cloud Console
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (ex: *TOEIC Parana*).
3. No menu lateral esquerdo, vá em **APIs e Serviços > Painel** e clique em **Ativar APIs e Serviços** no topo.
   - Pesquise por **Google Sheets API** e clique em **Ativar**.
   - Pesquise por **Google Drive API** e clique em **Ativar**.
4. Vá em **IAM e Administrador > Contas de Serviço**.
5. Clique em **Criar Conta de Serviço** no topo:
   - Dê um nome (ex: *leitor-planilha*).
   - Clique em **Criar e Continuar** e depois em **Concluir** (não é necessário adicionar papéis/roles).
6. Na lista de Contas de Serviço, clique sobre o e-mail da conta criada.
7. Vá na aba **Chaves** (Keys), clique em **Adicionar Chave > Criar nova chave**.
8. Selecione o formato **JSON** e clique em **Criar**.
   - Um arquivo contendo suas chaves privadas será baixado no seu computador. **Mantenha este arquivo seguro e não o envie para o GitHub!** (Ele já está no `.gitignore`).

### Passo 2.2: Compartilhar a Planilha
1. Abra a sua planilha do Google Sheets de cadastros.
2. Copie o e-mail da Conta de Serviço que você criou (ex: `leitor-planilha@...iam.gserviceaccount.com`).
3. Clique em **Compartilhar** no canto superior direito da planilha.
4. Cole o e-mail da Conta de Serviço, defina a permissão como **Leitor** (Viewer) e clique em **Compartilhar**.

---

## 3. Configurando a Hospedagem Automática (GitHub + Netlify)

### Passo 3.1: Configurar Secrets no GitHub
Suba a pasta do projeto para o seu repositório privado no GitHub. Depois, configure as chaves secretas para a Action rodar:

1. No seu repositório no GitHub, vá em **Settings > Secrets and variables > Actions**.
2. Clique em **New repository secret** e adicione as seguintes variáveis:

| Nome do Secret | Valor |
| :--- | :--- |
| `GOOGLE_SERVICE_ACCOUNT_KEY` | Abra o arquivo JSON de chave baixado no passo 2.1, copie todo o seu conteúdo de texto e cole aqui. |
| `NETLIFY_AUTH_TOKEN` | Seu Token de Acesso Pessoal do Netlify (Gerado em *Netlify > User Settings > Applications > Personal access tokens*). |
| `NETLIFY_SITE_ID` | O ID do seu site no Netlify (Encontrado em *Netlify > Site configuration > Site details > Site ID*). |

### Passo 3.2: Configurar o Botão "Atualizar Dados"
Para habilitar o funcionamento do botão "Atualizar Dados" na página de comparação sem expor suas credenciais:

1. No painel do seu site no **Netlify**, vá em **Site configuration > Build & deploy > Continuous deployment**.
2. Desça até a seção **Build hooks** e clique em **Add build hook**.
3. Dê um nome (ex: *Botão de Atualizar*) e salve. Ele gerará uma URL. **Copie essa URL**.
4. Agora, vá em **Site configuration > Environment variables** (variáveis de ambiente) no Netlify.
5. Clique em **Add a variable** e adicione a seguinte variável:
   * Key (Chave): `NETLIFY_BUILD_HOOK_URL`
   * Value (Valor): Cole a URL do Build Hook que você acabou de copiar.
6. Clique em **Save**.

---

## Como funciona a atualização?
* **Deploy no Commit:** Toda vez que você fizer um `git push` para o GitHub, o site será reconstruído e publicado no Netlify.
* **Atualização Periódica:** O GitHub Actions executará o script automaticamente a cada 1 hora, baixando os novos cadastros da planilha, gerando o novo comparativo e atualizando a sua página no Netlify.
* **Botão Atualizar Dados (Manual):** Clicando no botão na página de comparação, o Netlify iniciará uma reconstrução instantânea e o site será atualizado com os novos dados em cerca de 1 a 2 minutos.
