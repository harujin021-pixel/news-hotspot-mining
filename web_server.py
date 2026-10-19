# -*- coding: utf-8 -*-
"""
新闻热点挖掘系统 —— 网页一键采集入口（仅标准库，零新增依赖）

面向非技术使用者：
    1. 启动：.venv\\Scripts\\python.exe web_server.py（自动打开浏览器）
    2. 在打开的页面点击"一键采集更新"按钮，等待几分钟
    3. 完成后仪表板自动刷新为最新数据

数据库凭据读取 config/local_settings.py（与命令行方式一致），
使用者无需接触命令行、环境变量或数据库配置。
"""
import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
VIS_DIR = ROOT / 'data' / 'visualizations'
EXPORT_DIR = ROOT / 'data' / 'exports'
LOG_FILE = ROOT / 'data' / 'web_run.log'
HOST, PORT = '127.0.0.1', 8000

# 运行状态（单任务，禁止并发触发）
state = {
    'running': False,
    'last_start': None,
    'last_end': None,
    'last_exit_code': None,
    'csv_file': None,  # 最近一次成功运行生成的 EchoMap CSV 文件名
}
state_lock = threading.Lock()


def latest_csv_name():
    """data/exports 中最新的 EchoMap CSV 文件名；无则 None"""
    if not EXPORT_DIR.is_dir():
        return None
    files = sorted(EXPORT_DIR.glob('echomap_news_*.csv'),
                   key=lambda p: p.stat().st_mtime)
    return files[-1].name if files else None

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>News Hotspot Mining System</title>
<style>
  body { margin:0; font-family:"Microsoft YaHei",sans-serif; background:#f5f6fa; }
  header { display:flex; align-items:center; gap:16px; padding:12px 20px; background:#2c3e50; color:#fff; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; flex:1; min-width:200px; }
  #status { font-size:13px; color:#dfe6e9; }
  #langbox { display:flex; align-items:center; gap:10px; font-size:13px; color:#dfe6e9; }
  #langbox label { display:flex; align-items:center; gap:4px; cursor:pointer; }
  #langbox input[type=radio] { accent-color:#e74c3c; width:15px; height:15px; cursor:pointer; }
  button { padding:8px 20px; font-size:14px; border:none; border-radius:6px; cursor:pointer; background:#27ae60; color:#fff; }
  button:disabled { background:#7f8c8d; cursor:not-allowed; }
  #csvBtn { background:#2980b9; display:none; }
  #modalMask { display:none; position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:10; }
  #modal { display:none; position:fixed; top:50%; left:50%; transform:translate(-50%,-50%);
           background:#fff; border-radius:10px; padding:24px 28px; z-index:11; max-width:420px;
           box-shadow:0 6px 30px rgba(0,0,0,.25); font-size:14px; color:#2c3e50; }
  #modal p { margin:0 0 16px; line-height:1.6; word-break:break-all; white-space:pre-line; }
  #modal .btns { display:flex; gap:10px; justify-content:flex-end; }
  #modal .cancel { background:#95a5a6; }
  #logwrap { display:none; padding:8px 20px; background:#1e272e; }
  #log { color:#a5b1c2; font-size:12px; white-space:pre-wrap; max-height:150px; overflow:auto; margin:0; font-family:Consolas,monospace; }
  iframe { display:block; width:100%; height:calc(100vh - 54px); border:none; background:#fff; }
</style>
</head>
<body>
<header>
  <h1 id="appTitle">News Hotspot Mining System</h1>
  <div id="langbox">
    <span>Language / 语言</span>
    <label><input type="radio" name="lang" id="lang-en" value="en" onchange="setLang('en')"> English</label>
    <label><input type="radio" name="lang" id="lang-zh" value="zh" onchange="setLang('zh')"> 中文</label>
  </div>
  <span id="status">Ready</span>
  <button id="csvBtn" onclick="openCsvModal()"></button>
  <button id="runBtn" onclick="startRun()">Collect &amp; Update</button>
</header>
<div id="logwrap"><pre id="log"></pre></div>
<iframe id="dash" src="/static/dashboard_en.html"></iframe>
<div id="modalMask"></div>
<div id="modal">
  <p id="modalText"></p>
  <div class="btns">
    <button class="cancel" onclick="closeCsvModal()" id="modalCancel"></button>
    <button onclick="saveCsv()" id="modalSave"></button>
  </div>
</div>
<script>
let timer = null;
let lastStatus = null;
const btn = document.getElementById('runBtn');
const statusEl = document.getElementById('status');
const logwrap = document.getElementById('logwrap');
const logEl = document.getElementById('log');

// 外壳与仪表板文案（仪表板本身有两套静态文件，切换 iframe 源即可）
const I18N = {
  zh: {
    title: '新闻热点挖掘系统',
    ready: '就绪',
    run: '一键采集更新',
    running: '正在采集与分析，请稍候（通常需要几分钟）…',
    done: '已完成更新（{t}），图表已刷新',
    fail: '运行失败，请展开上方日志查看原因',
    csvBtn: '保存 EchoMap CSV',
    csvReady: '已生成 EchoMap 兼容 CSV：{f}\\n可直接上传到 EchoMap 继续分析。',
    csvSave: '选择位置并保存…',
    csvCancel: '取消',
    csvFail: '保存失败，请重试',
    dash: '/static/dashboard.html'
  },
  en: {
    title: 'News Hotspot Mining System',
    ready: 'Ready',
    run: 'Collect & Update',
    running: 'Collecting and analyzing, please wait (usually a few minutes)…',
    done: 'Update completed ({t}); charts refreshed',
    fail: 'Run failed; check the log above for details',
    csvBtn: 'Save EchoMap CSV',
    csvReady: 'EchoMap-compatible CSV generated: {f}\\nYou can upload it to EchoMap for further analysis.',
    csvSave: 'Choose location & save…',
    csvCancel: 'Cancel',
    csvFail: 'Save failed, please retry',
    dash: '/static/dashboard_en.html'
  }
};
let lang = localStorage.getItem('lang') || 'en';  // 默认英文，可用右上角控件切换中文

function setLang(l) {
  if (l === lang) return;
  lang = l;
  localStorage.setItem('lang', l);
  applyLang(true);
}
function applyLang(reloadDash) {
  const t = I18N[lang];
  document.documentElement.lang = lang;
  document.title = t.title;
  document.getElementById('appTitle').textContent = t.title;
  btn.textContent = t.run;
  document.getElementById('lang-' + lang).checked = true;
  document.getElementById('csvBtn').textContent = t.csvBtn;
  document.getElementById('modalSave').textContent = t.csvSave;
  document.getElementById('modalCancel').textContent = t.csvCancel;
  if (lastCsvFile) renderModalText();  // 弹窗打开时同步切换语言
  if (reloadDash) document.getElementById('dash').src = t.dash + '?t=' + Date.now();
  if (lastStatus) renderStatus(lastStatus);
}

// —— EchoMap CSV 下载弹窗 ——
let lastCsvFile = null;
function renderModalText() {
  document.getElementById('modalText').textContent = I18N[lang].csvReady.replace('{f}', lastCsvFile);
}
function openCsvModal() {
  renderModalText();
  document.getElementById('modalMask').style.display = 'block';
  document.getElementById('modal').style.display = 'block';
}
function closeCsvModal() {
  document.getElementById('modalMask').style.display = 'none';
  document.getElementById('modal').style.display = 'none';
}
async function saveCsv() {
  const t = I18N[lang];
  closeCsvModal();
  try {
    if (window.showSaveFilePicker) {
      // Chrome/Edge：调起原生"另存为"对话框，由用户选择保存位置
      const handle = await showSaveFilePicker({
        suggestedName: lastCsvFile,
        types: [{description: 'CSV', accept: {'text/csv': ['.csv']}}]
      });
      const blob = await (await fetch('/api/download_csv')).blob();
      const w = await handle.createWritable();
      await w.write(blob);
      await w.close();
    } else {
      // 其它浏览器：回退为普通下载（保存位置由浏览器设置决定）
      const a = document.createElement('a');
      a.href = '/api/download_csv';
      a.download = lastCsvFile;
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  } catch (e) {
    if (e.name !== 'AbortError') alert(t.csvFail);  // AbortError = 用户取消，属正常操作
  }
}

function startPolling() {
  if (!timer) timer = setInterval(refresh, 3000);
}
function stopPolling() {
  clearInterval(timer);
  timer = null;
}
async function startRun() {
  const r = await (await fetch('/api/run', {method:'POST'})).json();
  if (!r.ok) statusEl.textContent = r.msg;
  btn.disabled = true;
  logwrap.style.display = 'block';
  startPolling();
  refresh();
}
function renderStatus(s) {
  const t = I18N[lang];
  if (s.running) {
    statusEl.textContent = t.running;
    btn.disabled = true;
    logwrap.style.display = 'block';
    startPolling();
  } else {
    stopPolling();
    btn.disabled = false;
    if (s.last_exit_code === 0) {
      statusEl.textContent = t.done.replace('{t}', s.last_end || '');
      logwrap.style.display = 'none';  // 成功后收起日志框
    } else if (s.last_exit_code === null) {
      statusEl.textContent = t.ready;
    } else {
      statusEl.textContent = t.fail;
      logwrap.style.display = 'block';
    }
  }
  // 有可下载的 EchoMap CSV 时显示保存按钮
  if (s.csv_file) {
    lastCsvFile = s.csv_file;
    document.getElementById('csvBtn').style.display = 'inline-block';
  }
}
async function refresh() {
  const s = await (await fetch('/api/status')).json();
  // 仅当从"运行中"变为"完成"时才强制刷新仪表板，避免语言切换后状态轮询重复刷新
  const justFinished = lastStatus && lastStatus.running && !s.running;
  lastStatus = s;
  logEl.textContent = s.log_tail || '';
  logEl.scrollTop = logEl.scrollHeight;
  renderStatus(s);
  if (justFinished && s.last_exit_code === 0) {
    document.getElementById('dash').src = I18N[lang].dash + '?t=' + Date.now();
    if (s.csv_file) openCsvModal();  // 运行刚完成：弹出 CSV 保存提示框
  }
}
applyLang(true);  // 按记忆的语言初始化界面与仪表板
refresh();  // 打开页面时同步一次状态，刷新页面也不丢失进行中的任务
</script>
</body>
</html>
"""


def run_pipeline():
    """后台线程：跑完整流水线（采集→预处理→挖掘→可视化→导出EchoMap CSV），日志写文件"""
    with state_lock:
        state['running'] = True
        state['last_start'] = datetime.now().isoformat(timespec='seconds')
        state['last_end'] = None
        state['last_exit_code'] = None
        state['csv_file'] = None
    try:
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            code = subprocess.call(
                [sys.executable, 'main.py', '--mode', 'full', '--max-news', '50',
                 '--days', '30', '--export-echomap'],
                cwd=str(ROOT), stdout=f, stderr=subprocess.STDOUT)
    except Exception as e:
        code = -1
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(f'\n流水线启动失败: {e}\n')
    with state_lock:
        state['running'] = False
        state['last_end'] = datetime.now().isoformat(timespec='seconds')
        state['last_exit_code'] = code
        state['csv_file'] = latest_csv_name() if code == 0 else None


def read_log_tail(n=3000):
    try:
        return LOG_FILE.read_text(encoding='utf-8', errors='replace')[-n:]
    except FileNotFoundError:
        return ''


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype='text/html; charset=utf-8', code=200, extra_headers=None):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass  # 静默请求日志

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/':
            self._send(INDEX_HTML)
        elif path == '/api/status':
            with state_lock:
                s = dict(state)
            s['log_tail'] = read_log_tail()
            self._send(json.dumps(s, ensure_ascii=False), 'application/json; charset=utf-8')
        elif path == '/api/download_csv':
            name = latest_csv_name()
            if not name:
                self._send('No CSV available', code=404)
                return
            self._send((EXPORT_DIR / name).read_bytes(), 'text/csv; charset=utf-8',
                       extra_headers={'Content-Disposition': f'attachment; filename="{name}"'})
        elif path.startswith('/static/'):
            self._serve_static(path[len('/static/'):])
        else:
            self._send('Not Found', code=404)

    def do_POST(self):
        if urlparse(self.path).path == '/api/run':
            with state_lock:
                busy = state['running']
            if busy:
                self._send(json.dumps({'ok': False, 'msg': '任务正在运行中，请等待完成'},
                                      ensure_ascii=False), 'application/json; charset=utf-8')
                return
            threading.Thread(target=run_pipeline, daemon=True).start()
            self._send(json.dumps({'ok': True}), 'application/json; charset=utf-8')
        else:
            self._send('Not Found', code=404)

    def _serve_static(self, rel):
        # 防目录穿越
        target = (VIS_DIR / rel).resolve()
        if not str(target).startswith(str(VIS_DIR.resolve())) or not target.is_file():
            self._send('Not Found', code=404)
            return
        ctype = ('text/html; charset=utf-8' if target.suffix == '.html'
                 else 'application/javascript' if target.suffix == '.js'
                 else 'application/octet-stream')
        self._send(target.read_bytes(), ctype)


def main():
    state['csv_file'] = latest_csv_name()  # 启动时恢复最近一次生成的 CSV，供直接下载
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    url = f'http://{HOST}:{PORT}'
    print(f'新闻热点挖掘系统已启动: {url}')
    print('在页面点击"一键采集更新"即可采集并分析最新新闻（Ctrl+C 停止服务）')
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')


if __name__ == '__main__':
    main()
