@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

::::::: ---------- 配置 ----------
set HOST=192.168.0.61
set DOMAIN=
set PASSWORD=123456

::::::: ---------- 选择起始序号（默认 1） ----------
set "START=1"
:promptStart
set "START_INPUT="
set /p START_INPUT=请输入起始序号(1-500)，回车默认1: 
if "%START_INPUT%"=="" goto start_ok
echo %START_INPUT%| findstr /R "^[0-9][0-9]*$" >nul
if errorlevel 1 goto promptStart
set START=%START_INPUT%
if %START% LSS 1 goto promptStart
if %START% GTR 500 goto promptStart
:start_ok

::::::: ---------- 自动模式选择（输入A启用20秒自动继续，回车跳过） ----------
set "AUTO=0"
set "AUTO_INPUT="
set /p AUTO_INPUT=是否启用自动模式? 输入A启用(20秒无按键默认连接)，回车跳过: 
if /I "%AUTO_INPUT%"=="A" set "AUTO=1"

::::::: ---------- 循环从起始序号到 YD500：回车连接，其他键跳过，P 结束 ----------
for /l %%i in (%START%,1,500) do (
  set "num=00%%i"
  set "USER=YD!num:~-3!"
  set "RDPFILE=%TEMP%\remote_!USER!.rdp"

  rem 计算完整用户名（可选域）
  set "USER_FULL=!USER!"
  if defined DOMAIN set "USER_FULL=%DOMAIN%\!USER!"

  set "NEXT="
  set "DO_CONNECT=1"

  rem 自动模式交互（20秒后默认连接）
  if "%AUTO%"=="1" (
    echo 当前用户 !USER_FULL! ：按回车连接；按P结束；按S跳过 20秒无输入默认连接
    set "NEXT=ENTER"
    choice /C EPS /N /T 20 /D E >nul
    if errorlevel 3 set "NEXT=OTHER"
    if errorlevel 2 set "NEXT=P"
    if errorlevel 1 set "NEXT=ENTER"
  )

  rem 非自动模式交互（等待输入）
  if not "%AUTO%"=="1" (
    set /p NEXT=当前用户 !USER_FULL! ：按回车连接；输入P结束；其他键跳过: 
  )

  rem 处理结束指令
  if /I "!NEXT!"=="P" goto :finish

  rem 计算是否连接标志
  if "%AUTO%"=="1" if /I "!NEXT!"=="OTHER" set "DO_CONNECT=0"
  if not "%AUTO%"=="1" if not "!NEXT!"=="" set "DO_CONNECT=0"

  rem 执行动作
  if "!DO_CONNECT!"=="0" (
    echo 跳过用户 !USER_FULL!
  )
  if "!DO_CONNECT!"=="1" (
    echo 清除已缓存的凭据以避免复用...
    cmdkey /delete:TERMSRV/%HOST% >nul 2>nul
    cmdkey /delete:TERMSRV/%HOST%:3389 >nul 2>nul

    echo 写入凭据 - 用户 !USER_FULL! - 实现免密登录...

    cmdkey /generic:TERMSRV/%HOST% /user:!USER_FULL! /pass:%PASSWORD% >nul

    echo 正在生成临时 RDP 文件: !RDPFILE!  用户 !USER_FULL!
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

    echo 启动远程桌面连接 - %HOST% - 用户: !USER_FULL!
    start "" mstsc "!RDPFILE!"
  )
)

echo 全部连接已启动。
:finish
pause
