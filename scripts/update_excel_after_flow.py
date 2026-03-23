import argparse
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from openpyxl import Workbook, load_workbook

parser = argparse.ArgumentParser()
parser.add_argument('--flow', required=True)
parser.add_argument('--type', required=True, choices=['nonprinting', 'printing'])
args = parser.parse_args()

flow_base = os.path.splitext(os.path.basename(args.flow))[0]
report_dir = os.path.join('reports', 'raw')
excel_path = os.path.join('reports', 'excel', f'{args.type}_execution.xlsx')
os.makedirs(os.path.dirname(excel_path), exist_ok=True)

if os.path.exists(excel_path):
    wb = load_workbook(excel_path)
    ws = wb.active
else:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Execution Summary'
    ws.append([
        'Flow', 'Device', 'Suite Type', 'Status', 'Timestamp', 'Report File', 'Failure Message'
    ])

matched = []
if os.path.isdir(report_dir):
    for name in os.listdir(report_dir):
        if name.startswith(flow_base + '_') and name.lower().endswith('.xml'):
            matched.append(name)

matched.sort()
for name in matched:
    path = os.path.join(report_dir, name)
    status = 'PASS'
    failure_message = ''
    try:
        root = ET.parse(path).getroot()
        for testcase in root.iter('testcase'):
            failure = testcase.find('failure')
            error = testcase.find('error')
            if failure is not None or error is not None:
                status = 'FAIL'
                node = failure if failure is not None else error
                failure_message = (node.get('message') or (node.text or '')).strip().replace('\n', ' ')[:500]
                break
    except Exception as exc:
        status = 'PARSE_ERROR'
        failure_message = str(exc)[:500]

    device = os.path.splitext(name)[0].split('_')[-1]
    ws.append([
        flow_base,
        device,
        args.type,
        status,
        datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        path,
        failure_message,
    ])

wb.save(excel_path)
print(f'Excel updated: {excel_path}')
