@echo off
setlocal EnableExtensions
cd /d "%~1"
echo Running send_email with Jenkins credential gmail-smtp-kodak ...
python mailout\send_email.py || (echo 1> email_failed.flag)
