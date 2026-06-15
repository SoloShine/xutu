@echo off
cd /d %~dp0\..\
where npm >nul 2>nul || (echo [error] 未找到 npm，请先安装 Node.js & exit /b 1)
if not exist src\bedrock\web\static\index.html (
  echo [build] SPA 未构建，执行 npm install + build...
  pushd frontend
  call npm install && call npm run build || (echo [error] build 失败 & popd & exit /b 1)
  popd
)
python -m src.bedrock.web --projects-root projects
