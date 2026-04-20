"""
JUnit XML'den temiz bir HTML mail raporu üretir.
Kullanım: python generate_smoke_report.py smoke-results.xml smoke-email.html
"""

import sys
import xml.etree.ElementTree as ET
from datetime import datetime

def parse_junit(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    suite = root if root.tag == 'testsuite' else root.find('testsuite')

    total   = int(suite.attrib.get('tests',    0))
    failed  = int(suite.attrib.get('failures', 0))
    errors  = int(suite.attrib.get('errors',   0))
    skipped = int(suite.attrib.get('skipped',  0))
    passed  = total - failed - errors - skipped
    elapsed = float(suite.attrib.get('time', 0))

    cases = []
    for tc in suite.findall('testcase'):
        name      = tc.attrib.get('name', '')
        classname = tc.attrib.get('classname', '')
        time_s    = float(tc.attrib.get('time', 0))

        failure = tc.find('failure')
        error   = tc.find('error')
        skip    = tc.find('skipped')

        if failure is not None:
            status  = 'FAIL'
            message = failure.attrib.get('message', failure.text or '')
        elif error is not None:
            status  = 'ERROR'
            message = error.attrib.get('message', error.text or '')
        elif skip is not None:
            status  = 'SKIP'
            message = skip.attrib.get('message', '')
        else:
            status  = 'PASS'
            message = ''

        cases.append({
            'name':      name,
            'classname': classname,
            'status':    status,
            'message':   message,
            'time':      time_s,
        })

    return {
        'total':   total,
        'passed':  passed,
        'failed':  failed + errors,
        'skipped': skipped,
        'elapsed': elapsed,
        'cases':   cases,
    }


def status_color(status):
    return {
        'PASS':  '#2e7d32',
        'FAIL':  '#c62828',
        'ERROR': '#c62828',
        'SKIP':  '#f57c00',
    }.get(status, '#555')


def status_bg(status):
    return {
        'PASS':  '#f1f8f1',
        'FAIL':  '#fdf3f3',
        'ERROR': '#fdf3f3',
        'SKIP':  '#fffaf0',
    }.get(status, '#fafafa')


def build_html(data, build_url, build_number):
    overall_ok = data['failed'] == 0
    header_bg  = '#2e7d32' if overall_ok else '#c62828'
    overall    = 'BASARILI' if overall_ok else 'BASARISIZ'
    now        = datetime.now().strftime('%d.%m.%Y %H:%M')

    rows = ''
    for c in data['cases']:
        color = status_color(c['status'])
        bg    = status_bg(c['status'])
        msg   = f"<br><small style='color:#888'>{c['message'][:200]}</small>" if c['message'] else ''
        rows += f"""
        <tr style='background:{bg}'>
            <td style='padding:10px 14px;border-bottom:1px solid #eee;font-size:13px;color:#333'>{c['name']}{msg}</td>
            <td style='padding:10px 14px;border-bottom:1px solid #eee;text-align:center'>
                <span style='background:{color};color:#fff;padding:2px 10px;border-radius:12px;font-size:12px;font-weight:bold'>{c['status']}</span>
            </td>
            <td style='padding:10px 14px;border-bottom:1px solid #eee;text-align:right;color:#888;font-size:12px'>{c['time']:.2f}s</td>
        </tr>"""

    build_link = f"<a href='{build_url}' style='color:#fff;text-decoration:underline'>#{build_number}</a>" \
        if build_url else f"#{build_number}"

    return f"""<!DOCTYPE html>
<html>
<body style='margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif'>
<table width='100%' cellpadding='0' cellspacing='0' style='max-width:680px;margin:32px auto'>
  <tr>
    <td style='background:{header_bg};padding:24px 32px;border-radius:6px 6px 0 0'>
      <span style='color:#fff;font-size:20px;font-weight:bold'>Fiyatlar Smoke Test — {overall}</span><br>
      <span style='color:rgba(255,255,255,0.8);font-size:13px'>{now} &nbsp;|&nbsp; Build {build_link}</span>
    </td>
  </tr>
  <tr>
    <td style='background:#fff;padding:24px 32px'>
      <table width='100%' cellpadding='0' cellspacing='0'>
        <tr>
          <td style='text-align:center;padding:8px'>
            <div style='font-size:28px;font-weight:bold;color:#2e7d32'>{data['passed']}</div>
            <div style='font-size:12px;color:#888;text-transform:uppercase'>Geçti</div>
          </td>
          <td style='text-align:center;padding:8px'>
            <div style='font-size:28px;font-weight:bold;color:#c62828'>{data['failed']}</div>
            <div style='font-size:12px;color:#888;text-transform:uppercase'>Hata</div>
          </td>
          <td style='text-align:center;padding:8px'>
            <div style='font-size:28px;font-weight:bold;color:#f57c00'>{data['skipped']}</div>
            <div style='font-size:12px;color:#888;text-transform:uppercase'>Atlandı</div>
          </td>
          <td style='text-align:center;padding:8px'>
            <div style='font-size:28px;font-weight:bold;color:#555'>{data['total']}</div>
            <div style='font-size:12px;color:#888;text-transform:uppercase'>Toplam</div>
          </td>
          <td style='text-align:center;padding:8px'>
            <div style='font-size:28px;font-weight:bold;color:#555'>{data['elapsed']:.1f}s</div>
            <div style='font-size:12px;color:#888;text-transform:uppercase'>Süre</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>
  <tr>
    <td style='background:#fff;padding:0 32px 24px'>
      <table width='100%' cellpadding='0' cellspacing='0' style='border:1px solid #eee;border-radius:4px'>
        <tr style='background:#fafafa'>
          <th style='padding:10px 14px;text-align:left;font-size:12px;color:#888;border-bottom:1px solid #eee'>TEST</th>
          <th style='padding:10px 14px;text-align:center;font-size:12px;color:#888;border-bottom:1px solid #eee'>SONUÇ</th>
          <th style='padding:10px 14px;text-align:right;font-size:12px;color:#888;border-bottom:1px solid #eee'>SÜRE</th>
        </tr>
        {rows}
      </table>
    </td>
  </tr>
  <tr>
    <td style='background:#f5f5f5;padding:16px 32px;border-radius:0 0 6px 6px;text-align:center'>
      <span style='font-size:11px;color:#aaa'>Fiyatlar CI — otomatik rapor</span>
    </td>
  </tr>
</table>
</body>
</html>"""


if __name__ == '__main__':
    xml_path    = sys.argv[1]
    out_path    = sys.argv[2]
    build_url   = sys.argv[3] if len(sys.argv) > 3 else ''
    build_num   = sys.argv[4] if len(sys.argv) > 4 else '?'

    data = parse_junit(xml_path)
    html = build_html(data, build_url, build_num)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Report generated: {out_path} ({data['passed']} passed, {data['failed']} failed, {data['skipped']} skipped)")
