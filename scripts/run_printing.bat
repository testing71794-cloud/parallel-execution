@echo off
cd /d D:\Projects-Meastro\kodak-Smile-with-OpenAI

echo Running Non Printing Flows (Single device mode)...
adb devices
maestro test "Non printing flows"

pause