#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

__declspec(dllimport) int Py_Main(int argc, wchar_t **argv);

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command, int show)
{
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONPATH", NULL);
    SetEnvironmentVariableW(L"PYTHONNOUSERSITE", L"1");
    if (__argc > 1)
        return Py_Main(__argc, __wargv);

    wchar_t script[32768];
    DWORD length = GetModuleFileNameW(NULL, script, _countof(script));
    if (!length || length >= _countof(script))
        return 1;
    wchar_t *basename = wcsrchr(script, L'\\');
    if (!basename)
        return 1;
    *basename = L'\0';
    if (wcscat_s(script, _countof(script), L"\\..\\main.py") != 0)
        return 1;
    wchar_t *args[] = {__wargv[0], L"-I", script, NULL};
    return Py_Main(3, args);
}
