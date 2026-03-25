import os
from openpyxl import Workbook

root = os.getcwd()
summary_dir = os.path.join(root, 'build-summary')
os.makedirs(summary_dir, exist_ok=True)

rows = []
for suite_dir, suite_name in [('reports', 'nonprinting'), ('reports_printing', 'printing')]:
    full = os.path.join(root, suite_dir)
    if not os.path.isdir(full):
        continue
    for device in sorted(os.listdir(full)):
        device_dir = os.path.join(full, device)
        if not os.path.isdir(device_dir):
            continue
        for name in sorted(os.listdir(device_dir)):
            if name.endswith('.status'):
                flow = name[:-7]
                status = open(os.path.join(device_dir, name), 'r', encoding='utf-8', errors='ignore').read().strip()
                rows.append([suite_name, device, flow, status])

wb = Workbook()
ws = wb.active
ws.title = 'Summary'
ws.append(['Suite', 'Device ID', 'Flow Name', 'Status'])
for row in rows:
    ws.append(row)
wb.save(os.path.join(summary_dir, 'final_execution_report.xlsx'))

html = ['<html><body><h2>Kodak Smile Execution Summary</h2><table border="1" cellspacing="0" cellpadding="4">', '<tr><th>Suite</th><th>Device ID</th><th>Flow Name</th><th>Status</th></tr>']
for suite, device, flow, status in rows:
    html.append(f'<tr><td>{suite}</td><td>{device}</td><td>{flow}</td><td>{status}</td></tr>')
html.append('</table></body></html>')
with open(os.path.join(summary_dir, 'summary.html'), 'w', encoding='utf-8') as f:
    f.write('\n'.join(html))
print('Build summary generated.')
