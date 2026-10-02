#!/usr/bin/env bash
set -uo pipefail

CUTOFF="2026-10-05 08:00:00"
LOG="/home/ekogui/Ekogui/task/resend_excel_scheduled.log"
EXCEL="/home/ekogui/Ekogui/task/ANALISIS SELECCIÓN DE MUESTRA ANS 2 - SEPTIEMBRE.xlsx"

now_epoch=$(date +%s)
cutoff_epoch=$(date -d "$CUTOFF" +%s)

echo "$(date '+%Y-%m-%d %H:%M:%S') - chequeando corte ($CUTOFF)" >> "$LOG"

if [ "$now_epoch" -ge "$cutoff_epoch" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - ya pasó el corte, se quita la tarea de crontab y no se reenvía" >> "$LOG"
    crontab -l 2>/dev/null | grep -v "resend_excel_scheduled.sh" | crontab -
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S') - reenviando excel a searchCaseNumbersBulkExcel" >> "$LOG"

cd "/home/ekogui/Ekogui/task" || exit 1
response=$(curl -s -X POST 'http://localhost:8000/api/v1/ekogui/searchCaseNumbersBulkExcel' \
  -H 'accept: */*' \
  -F "file=@${EXCEL};type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  -F 'entityId=405' \
  -F 'state=PROCESO_ENTIDAD_ACTIVO' \
  -F 'batchSize=10' \
  -w '\nHTTP_STATUS:%{http_code}\n')

echo "$(date '+%Y-%m-%d %H:%M:%S') - respuesta: $response" >> "$LOG"
