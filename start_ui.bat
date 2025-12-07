@echo off
cd /d "c:\Users\seizo\Desktop\BoatRace"
call venv\Scripts\activate
streamlit run ui/app.py
pause
