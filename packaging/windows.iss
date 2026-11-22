#ifndef BuildArch
  #define BuildArch "x64"
#endif
#define ProjectDir ExtractFileDir(RemoveBackslashUnlessRoot(SourcePath))
[Setup]
SourceDir={#ProjectDir}
AppId=FormixDesktop
AppName=格式转换通
AppVersion={#Version}
AppPublisher=xiaofa520
VersionInfoCompany=xiaofa520
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
DefaultDirName={autopf}\Formix
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible arm64
ArchitecturesInstallIn64BitMode=x64compatible arm64
OutputDir=dist
OutputBaseFilename=Formix-windows-{#BuildArch}
Compression=lzma2/fast
SolidCompression=no
UninstallDisplayIcon={app}\formix\assets\logo.ico
[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh_CN"; MessagesFile: "packaging/languages/ChineseSimplified.isl"
Name: "zh_TW"; MessagesFile: "packaging/languages/ChineseTraditional.isl"
Name: "ja"; MessagesFile: "compiler:Languages/Japanese.isl"
Name: "ko"; MessagesFile: "compiler:Languages/Korean.isl"
Name: "ru"; MessagesFile: "compiler:Languages/Russian.isl"
Name: "fr"; MessagesFile: "compiler:Languages/French.isl"
[Files]
Source: "build\windows-{#BuildArch}-app\*"; DestDir: "{app}"; Excludes: "logs\*,cache\*,output\*,models\*,formix\__pycache__\*,*.obj"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "build\vc_redist.{#BuildArch}.exe"; DestDir: "{tmp}"; DestName: "vc_redist.{#BuildArch}.exe"; Flags: deleteafterinstall
[Icons]
Name: "{commonprograms}\格式转换通"; Filename: "{app}\python\Formix.exe"; WorkingDir: "{app}"; IconFilename: "{app}\formix\assets\logo.ico"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then Exit;
  if Exec(ExpandConstant('{tmp}\vc_redist.{#BuildArch}.exe'), '/install /quiet /norestart',
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    if (ResultCode = 0) or (ResultCode = 3010) or (ResultCode = 1638) then Exit;
  Log(Format('VC++ runtime setup failed: %d', [ResultCode]));
  if SuppressibleMsgBox('Microsoft Visual C++ 运行库未能安装。是否打开浏览器下载官方安装包？',
                        mbConfirmation, MB_YESNO, IDNO) = IDYES then
    ShellExecAsOriginalUser('open', 'https://aka.ms/vs/17/release/vc_redist.{#BuildArch}.exe',
                            '', '', SW_SHOWNORMAL, ewNoWait, ResultCode);
end;
