@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

::::: ---------- 配置 ----------
set HOST=192.168.0.61
set DOMAIN=
set PASSWORD=123456

::::: ---------- 选择起始序号（默认 1） ----------
set "START=1"
:promptStart
set "START_INPUT="
set /p START_INPUT=请输入起始序号(1-500)，回车默认1: 
if "%START_INPUT%"=="" goto start_ok
echo %START_INPUT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 goto promptStart
set START=%START_INPUT%
if %START% LSS 1 goto promptStart
if %START% GTR 199 goto promptStart
:start_ok

::::: ---------- 循环从起始序号到 YD500：回车连接，其他键跳过，P 结束 ----------
for /l %%i in (%START%,1,500) do (
  set "num=00%%i"
  set "USER=YD!num:~-3!"
  set "RDPFILE=%TEMP%\remote_!USER!.rdp"

  if not "%DOMAIN%"=="" (
    set "USER_FULL=%DOMAIN%\!USER!"
  ) else (
    set "USER_FULL=!USER!"
  )

  set "NEXT="
  set /p NEXT=当前用户 !USER_FULL! ：按回车连接；输入P结束；其他键跳过: 
  if /I "!NEXT!"=="P" goto :finish
  if "!NEXT!"=="" (
    echo 清除已缓存的凭据以避免复用...
    cmdkey /delete:TERMSRV/%HOST% >nul 2>nul
    cmdkey /delete:TERMSRV/%HOST%:3389 >nul 2>nul

    echo 写入凭据（!USER_FULL!）以实现免密登录...
    cmdkey /generic:TERMSRV/%HOST% /user:!USER_FULL! /pass:%PASSWORD% >nul

    echo 正在生成临时 RDP 文件：!RDPFILE! （用户：!USER_FULL!）
    > "!RDPFILE!" (
      echo full address:s:%HOST%
      echo username:s:!USER_FULL!
      echo screen mode id:i:2
      echo session bpp:i:32
      echo authentication level:i:2
      echo enablecredsspsupport:i:1
      echo prompt for credentials on client:i:0
      echo promptcredentialonce:i:0
    )

    echo 启动远程桌面连接（%HOST%）- 用户：!USER_FULL!
    start "" mstsc "!RDPFILE!"
  ) else (
    echo 跳过用户 !USER_FULL!
  )
)

echo 全部连接已启动。
:finish
pause
