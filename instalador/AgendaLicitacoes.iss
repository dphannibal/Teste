; Instalador da Agenda de Licitações (Inno Setup 6).
; Gerado pelo GitHub Actions (.github/workflows/instalador.yml) a partir do executável que o
; PyInstaller deixa em dist\AgendaLicitacoes. Para gerar à mão, num Windows:
;   pyinstaller --distpath dist instalador\agenda.spec
;   "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /DVersao=1.1.0 instalador\AgendaLicitacoes.iss

#ifndef Versao
  #define Versao "1.1.0"
#endif
#define Nome "Agenda de Licitações"
#define Exe "AgendaLicitacoes.exe"
#define Porta "8080"
#define Tarefa "Agenda de Licitacoes"

[Setup]
AppId={{6E0C5B7A-3F1D-4B8E-9C2A-7D4E1F0A8B35}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher={#Nome}
DefaultDirName=C:\AgendaLicitacoes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=AgendaLicitacoes-Instalador-{#Versao}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome}
CloseApplications=no
SetupLogging=yes

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "iniciar"; Description: "Iniciar o sistema automaticamente com o Windows (recomendado)"
Name: "compartilhar"; Description: "Compartilhar a pasta do programa na rede como ""Licitacoes"", somente leitura (recomendado)"
Name: "firewall"; Description: "Liberar a porta {#Porta} no Firewall do Windows para redes privadas e de domínio (recomendado)"

[Files]
Source: "..\dist\AgendaLicitacoes\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "configurar.ps1"; DestDir: "{app}\instalador"; Flags: ignoreversion

[INI]
; Atalho na área de trabalho do computador hospedeiro.
Filename: "{commondesktop}\{#Nome}.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{#Porta}/"

[Run]
Filename: "{app}\{#Exe}"; Parameters: "--preparar --senha-em ""{tmp}\senha-admin.txt"""; StatusMsg: "Preparando o banco de dados..."; Flags: runhidden waituntilterminated
Filename: "powershell.exe"; Parameters: "{code:ParametrosConfigurar|instalar}"; StatusMsg: "Configurando o Windows..."; Flags: runhidden waituntilterminated
Filename: "{commondesktop}\{#Nome}.url"; Description: "Abrir a Agenda de Licitações"; Tasks: iniciar; Flags: postinstall shellexec nowait skipifsilent
Filename: "{app}\{#Exe}"; Description: "Iniciar a Agenda de Licitações agora (janela do servidor)"; Tasks: not iniciar; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "{code:ParametrosConfigurar|desinstalar}"; Flags: runhidden waituntilterminated; RunOnceId: "Desconfigurar"

[UninstallDelete]
Type: files; Name: "{app}\Abrir Agenda de Licitações.url"
Type: files; Name: "{commondesktop}\{#Nome}.url"

[Code]
var
  SenhaAdmin: String;

{ Parâmetros do configurar.ps1 conforme as opções marcadas no assistente. }
function ParametrosConfigurar(Acao: String): String;
begin
  Result := '-NoProfile -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\instalador\configurar.ps1') + '" -Acao ' + Acao +
    ' -Pasta "' + ExpandConstant('{app}') + '" -Porta {#Porta}';
  if Acao = 'instalar' then
  begin
    if WizardIsTaskSelected('iniciar') then Result := Result + ' -Iniciar';
    if WizardIsTaskSelected('compartilhar') then Result := Result + ' -Compartilhar';
    if WizardIsTaskSelected('firewall') then Result := Result + ' -Firewall';
  end;
end;

{ Atualização: para o sistema em execução antes de substituir os arquivos. }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  Exec(ExpandConstant('{sys}\schtasks.exe'), '/End /TN "{#Tarefa}"', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#Exe}', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;

{ Primeira instalação: mostra a senha temporária do admin, gerada pelo --preparar. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Linhas: TArrayOfString;
begin
  if (CurStep = ssPostInstall) and
     LoadStringsFromFile(ExpandConstant('{tmp}\senha-admin.txt'), Linhas) and
     (GetArrayLength(Linhas) > 0) then
  begin
    SenhaAdmin := Trim(Linhas[0]);
    if not WizardSilent then
      MsgBox('Primeiro acesso ao sistema:' + #13#10#13#10 +
             'Usuário: admin' + #13#10 +
             'Senha temporária: ' + SenhaAdmin + #13#10#13#10 +
             'Anote a senha (Ctrl+C copia esta mensagem). Ela será trocada no primeiro acesso.',
             mbInformation, MB_OK);
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Texto: String;
begin
  if CurPageID = wpFinished then
  begin
    Texto := 'A Agenda de Licitações foi instalada.' + #13#10#13#10 +
      'Neste computador: atalho "{#Nome}" na área de trabalho (http://localhost:{#Porta}/).';
    if WizardIsTaskSelected('compartilhar') then
      Texto := Texto + #13#10#13#10 + 'Nos demais computadores: abra \\' + GetComputerNameString +
        '\Licitacoes e dê dois cliques em "Abrir Agenda de Licitações".';
    if SenhaAdmin <> '' then
      Texto := Texto + #13#10#13#10 + 'Primeiro acesso: usuário admin, senha temporária ' + SenhaAdmin + '.';
    Texto := Texto + #13#10#13#10 + 'Os dados ficam em ' + ExpandConstant('{commonappdata}') +
      '\AgendaLicitacoes (faça backup dessa pasta).';
    WizardForm.FinishedLabel.Caption := Texto;
  end;
end;
