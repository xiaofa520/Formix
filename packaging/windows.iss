#ifndef BuildArch
  #define BuildArch "x64"
#endif
#define ProjectDir ExtractFileDir(RemoveBackslashUnlessRoot(SourcePath))
[Setup]
SourceDir={#ProjectDir}
AppId=FormixDesktop
AppName={cm:AppTitle}
AppVersion={#Version}
AppPublisher=xiaofa520
VersionInfoCompany=xiaofa520
ShowLanguageDialog=yes
LanguageDetectionMethod=uilanguage
DefaultDirName={code:DefaultInstallDir}
DisableProgramGroupPage=yes
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
[CustomMessages]
AppTitle=Formix
StartMenuTask=Add a shortcut to the Start menu
zh_CN.AppTitle=格式转换通
zh_CN.StartMenuTask=添加到开始菜单
zh_TW.AppTitle=格式轉換通
zh_TW.StartMenuTask=新增至開始功能表
[Tasks]
Name: "startmenu"; Description: "{cm:StartMenuTask}"; Flags: unchecked
[Files]
Source: "build\windows-{#BuildArch}-app\*"; DestDir: "{app}"; Excludes: "\logs\*,\cache\*,\output\*,\models\*,\formix\__pycache__\*"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "build\vc_redist.{#BuildArch}.exe"; DestDir: "{tmp}"; DestName: "vc_redist.{#BuildArch}.exe"; Flags: deleteafterinstall
[Icons]
Name: "{commondesktop}\{cm:AppTitle}"; Filename: "{app}\python\Formix.exe"; WorkingDir: "{app}"; IconFilename: "{app}\formix\assets\logo.ico"
Name: "{commonprograms}\{cm:AppTitle}"; Tasks: startmenu; Filename: "{app}\python\Formix.exe"; WorkingDir: "{app}"; IconFilename: "{app}\formix\assets\logo.ico"

[Code]
function DefaultInstallDir(Param: String): String;
var
  Drive, Folder: String;
begin
  if DirExists('D:\') then Drive := 'D:'
  else Drive := ExpandConstant('{sd}');
  if ActiveLanguage = 'zh_CN' then Folder := '格式转换通'
  else if ActiveLanguage = 'zh_TW' then Folder := '格式轉換通'
  else Folder := 'Formix';
  Result := Drive + '\' + Folder;
end;

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
