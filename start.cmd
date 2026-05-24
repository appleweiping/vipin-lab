@echo off
REM start.cmd — launch backend + frontend dev server
echo.
echo   ^<^< Vipin Lab ^>^>
echo.

if not exist .env (
    copy .env.example .env >nul
    echo   [WARN] Add ANTHROPIC_API_KEY to .env
    echo.
)

echo   Starting API backend on http://localhost:8001 ...
start "vlab-api" cmd /k "uvicorn api.server:app --reload --port 8001"

timeout /t 2 /nobreak >nul

echo   Starting UI on http://localhost:5174 ...
start "vlab-ui" cmd /k "cd ui && npm run dev"

echo.
echo   API:  http://localhost:8001
echo   UI:   http://localhost:5174
echo   Docs: http://localhost:8001/docs
echo.
echo   CLI:  vlab              (interactive REPL)
echo   CLI:  vlab discover "LLM4Rec"
echo.
