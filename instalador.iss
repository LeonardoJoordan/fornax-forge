#define AppName "FORNAX Forge"
#define AppDescription "Geração de material personalizado em lote"
#define AppVersion "1.0.0"
#define AppExeName "FORNAX_Forge.exe"
#define AppPublisher "Leonardo Joordan Belisário Lima da Silva"

[Setup]
; Não altere o AppId em versões futuras: ele identifica atualizações e desinstalações.
AppId={{F0599521-F254-4070-91F0-A13FF6F788DA}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppComments={#AppDescription}
AppPublisherURL=https://github.com/LeonardoJoordan/fornax-forge
AppSupportURL=https://github.com/LeonardoJoordan/fornax-forge/issues
AppUpdatesURL=https://github.com/LeonardoJoordan/fornax-forge/releases
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppDescription}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}
LicenseFile=build\main.dist\LICENSE
InfoAfterFile=build\main.dist\docs\AVISO-DISTRIBUICAO.txt
DefaultDirName={autopf}\FORNAX Forge
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=build\installer-windows
OutputBaseFilename=Instalador-FORNAX-Forge-{#AppVersion}
SetupIconFile=assets\icons\fornax-forge.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter={#AppExeName}
RestartApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na Área de Trabalho"; GroupDescription: "Ícones adicionais:"; Flags: unchecked

[Files]
; Execute `python script_nuitka.py` antes de compilar este instalador.
Source: "build\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Plugin removido pelo build atual: uma atualização não deve conservar a cópia antiga.
; Alvo único e restrito; não apagar diretórios nem dados do usuário.
Type: files; Name: "{app}\PySide6\qt-plugins\imageformats\qpdf.dll"

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{group}\Licenças e avisos"; Filename: "{app}\docs\THIRD_PARTY_LICENSES.md"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"

[Registry]
Root: HKA; Subkey: "Software\Classes\.fornax"; ValueType: string; ValueName: ""; ValueData: "FornaxForge.Model"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.fornax"; ValueType: string; ValueName: "Content Type"; ValueData: "application/x-fornax-template"
Root: HKA; Subkey: "Software\Classes\FornaxForge.Model"; ValueType: string; ValueName: ""; ValueData: "Modelo FORNAX Forge"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\FornaxForge.Model\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"
Root: HKA; Subkey: "Software\Classes\FornaxForge.Model\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Executar {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  FullCleanupRequested: Boolean;

function ConfirmFullUninstall(): Boolean;
var
  Form: TForm;
  PromptLabel: TLabel;
  CleanupCheckBox: TCheckBox;
  OkButton, CancelButton: TNewButton;
begin
  Form := TForm.Create(nil);
  try
    Form.ClientWidth := ScaleX(460);
    Form.ClientHeight := ScaleY(175);
    Form.Caption := 'Desinstalar {#AppName}';
    Form.Position := poScreenCenter;
    PromptLabel := TLabel.Create(Form);
    PromptLabel.Parent := Form;
    PromptLabel.Left := ScaleX(20);
    PromptLabel.Top := ScaleY(20);
    PromptLabel.Width := Form.ClientWidth - ScaleX(40);
    PromptLabel.Height := ScaleY(45);
    PromptLabel.AutoSize := False;
    PromptLabel.WordWrap := True;
    PromptLabel.Caption := 'Deseja desinstalar o {#AppName} e seus componentes instalados?';
    PromptLabel.Font.Style := [fsBold];
    CleanupCheckBox := TCheckBox.Create(Form);
    CleanupCheckBox.Parent := Form;
    CleanupCheckBox.Left := ScaleX(20);
    CleanupCheckBox.Top := PromptLabel.Top + PromptLabel.Height + ScaleY(5);
    CleanupCheckBox.Width := Form.ClientWidth - ScaleX(40);
    CleanupCheckBox.Caption := 'Remover também preferências, logs e modelos locais';
    CleanupCheckBox.Checked := False;
    OkButton := TNewButton.Create(Form);
    OkButton.Parent := Form;
    OkButton.Width := ScaleX(90);
    OkButton.Caption := 'Desinstalar';
    OkButton.ModalResult := mrYes;
    OkButton.Top := Form.ClientHeight - OkButton.Height - ScaleY(15);
    OkButton.Left := Form.ClientWidth - (OkButton.Width * 2) - ScaleX(25);
    CancelButton := TNewButton.Create(Form);
    CancelButton.Parent := Form;
    CancelButton.Width := ScaleX(90);
    CancelButton.Caption := 'Cancelar';
    CancelButton.ModalResult := mrNo;
    CancelButton.Top := OkButton.Top;
    CancelButton.Left := Form.ClientWidth - CancelButton.Width - ScaleX(15);
    CancelButton.Cancel := True;
    CancelButton.Default := True;
    if Form.ShowModal() = mrYes then
    begin
      FullCleanupRequested := CleanupCheckBox.Checked;
      Result := True;
    end
    else
      Result := False;
  finally
    Form.Free;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  FullCleanupRequested := False;
  if UninstallSilent then Result := True else Result := ConfirmFullUninstall();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and FullCleanupRequested then
  begin
    DelTree(ExpandConstant('{userappdata}\FornaxForge'), True, True, True);
    RegDeleteKeyIncludingSubkeys(HKCU, 'Software\FORNAX Forge\MainApp');
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = wpPreparing) and WizardForm.PreparingNoRadio.Checked then
  begin
    MsgBox('A instalação foi cancelada para proteger o trabalho em andamento.' + #13#10 +
      'Feche o aplicativo e tente novamente.', mbInformation, MB_OK);
    Result := False;
    WizardForm.Close;
  end;
end;
