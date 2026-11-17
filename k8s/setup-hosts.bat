@echo off
echo Menambahkan '127.0.0.1 auth.lokal api.lokal' ke C:\Windows\System32\drivers\etc\hosts...
powershell -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -Command \"Add-Content -Path C:\Windows\System32\drivers\etc\hosts -Value `\"`r`n127.0.0.1 auth.lokal api.lokal`\"; ipconfig /flushdns\"'"
echo Selesai! Silakan klik 'Yes' pada jendela konfirmasi Administrator yang muncul.

