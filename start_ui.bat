@echo off
echo Starting Streamlit UI...
echo.
echo Access URL: http://localhost:8501
echo.

python -m streamlit run ui/app.py --server.headless false

pause
