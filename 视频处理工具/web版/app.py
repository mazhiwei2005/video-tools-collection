"""
视频处理工具 Web版 — Flask Backend
"""
import os, sys, json, uuid, time, subprocess, threading, glob
from flask import Flask, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
UPLOAD = os.path.join(BASE, 'uploads')
OUTPUT = os.path.join(BASE, 'outputs')
os.makedirs(UPLOAD, exist_ok=True)
os.makedirs(OUTPUT, exist_ok=True)

FFMPEG = r'C:\Program Files\FFmpeg\bin\ffmpeg.exe'
FFPROBE = r'C:\Program Files\FFmpeg\bin\ffprobe.exe'

# ─── Task tracking ───
tasks = {}  # task_id → {status, progress, eta, log, output_file}

def _log(task_id, msg):
    if task_id in tasks:
        ts = time.strftime('%H:%M:%S')
        tasks[task_id]['log'].append(f'[{ts}] {msg}')
        # Keep last 200 lines
        if len(tasks[task_id]['log']) > 200:
            tasks[task_id]['log'] = tasks[task_id]['log'][-200:]

def _get_duration(path):
    """Get video duration in seconds via ffprobe"""
    try:
        r = subprocess.run(
            [FFPROBE, '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=15)
        return float(r.stdout.strip()) if r.returncode == 0 else 0
    except:
        return 0

def _get_info(path):
    """Get video info: duration, width, height, codec, fps"""
    try:
        r = subprocess.run(
            [FFPROBE, '-v', 'quiet', '-print_format', 'json',
             '-show_streams', '-show_format', path],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0: return {}
        data = json.loads(r.stdout)
        info = {}
        fmt = data.get('format', {})
        info['duration'] = float(fmt.get('duration', 0))
        info['size'] = int(fmt.get('size', 0))
        for s in data.get('streams', []):
            if s.get('codec_type') == 'video':
                info['width'] = int(s.get('width', 0))
                info['height'] = int(s.get('height', 0))
                info['codec'] = s.get('codec_name', '')
                info['fps'] = eval(s.get('r_frame_rate', '0/1')) if '/' in s.get('r_frame_rate','') else 0
                break
        return info
    except:
        return {}

def _even(n):
    return n // 2 * 2

def _run_ffmpeg(cmd, task_id, output_path, total_duration=0):
    """Run FFmpeg with progress monitoring"""
    _log(task_id, f'CMD: {" ".join(cmd[:8])}...')
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    start = time.time()
    last_size = 0
    while proc.poll() is None:
        time.sleep(2)
        if os.path.exists(output_path):
            cur = os.path.getsize(output_path)
            if total_duration > 0 and cur > 0:
                # Estimate progress from file size
                bitrate_est = cur / max(1, time.time() - start)
                pct = min(95, (time.time() - start) / max(1, total_duration / 8) * 100)
                tasks[task_id]['progress'] = pct
                elapsed = time.time() - start
                if pct > 5:
                    eta = elapsed / pct * (100 - pct)
                    tasks[task_id]['eta'] = f'{int(eta//60)}m{int(eta%60)}s'
            speed = (cur - last_size) / 2 / 1024 / 1024
            last_size = cur
            if speed > 0:
                _log(task_id, f'⏳ {cur/1048576:.0f}MB ({speed:.1f}MB/s)')
    if proc.returncode == 0:
        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'done'
        tasks[task_id]['eta'] = ''
        _log(task_id, f'✅ 完成: {os.path.basename(output_path)}')
    else:
        err = proc.stderr.read().decode('utf-8', errors='replace')[-1500:]
        tasks[task_id]['status'] = 'error'
        _log(task_id, f'❌ 失败: {err[-200:]}')
    proc.stderr.close()

# ─── Processing modes ───

def _process_frame(task_id, video_path, template_path, roi, output_path, codec, bitrate):
    """套框模式"""
    dur = _get_duration(video_path)
    w, h = 1920, 1080
    rx, ry, rw, rh = roi
    cmd = [FFMPEG, '-y', '-loop', '1', '-i', template_path,
           '-i', video_path,
           '-filter_complex',
           f'[0:v]scale={w}:{h}[bg];'
           f'[1:v]scale={rw}:{rh}:force_original_aspect_ratio=decrease[fg];'
           f'[bg][fg]overlay={rx}:{ry},format=yuv420p[out]',
           '-map', '[out]', '-map', '1:a?',
           '-pix_fmt', 'yuv420p',
           '-c:v', codec, '-b:v', f'{bitrate}k',
           '-c:a', 'flac', '-ar', '96000',
           '-movflags', '+faststart', '-t', str(dur), output_path]
    _run_ffmpeg(cmd, task_id, output_path, dur)

def _process_pip(task_id, video_path, template_path, regions, left_file, right_file, output_path, codec, bitrate):
    """画中画模式"""
    dur = _get_duration(video_path)
    inputs = [FFMPEG, '-y']
    filter_parts = []
    
    # Input 0: template (image needs -loop 1)
    tpl_ext = os.path.splitext(template_path)[1].lower()
    if tpl_ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp'):
        inputs += ['-loop', '1', '-i', template_path]
    else:
        inputs += ['-i', template_path]
    
    # Input 1: main video (center)
    inputs += ['-i', video_path]
    
    # Get template dimensions
    tpl_info = _get_info(template_path)
    tw, th = tpl_info.get('width', 1920), tpl_info.get('height', 1080)
    
    # Scale template
    filter_parts.append(f'[0:v]scale={tw}:{th}[bg]')
    output_label = '[bg]'
    
    # Scale center video with transpose for portrait areas
    center = regions.get('center', {'x': 0, 'y': 0, 'w': tw, 'h': th})
    cx, cy, cw, ch = center['x'], center['y'], center['w'], center['h']
    is_portrait = ch > cw
    transpose = ',transpose=2' if is_portrait else ''
    filter_parts.append(f'[1:v]{transpose.lstrip(",")},scale={cw}:{ch}:force_original_aspect_ratio=decrease[center_s]' if transpose else f'[1:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease[center_s]')
    filter_parts.append(f'{output_label}[center_s]overlay={cx}:{cy}[out_c]')
    output_label = '[out_c]'
    
    # Left decoration
    inp_idx = 2
    if left_file and os.path.exists(left_file):
        inputs += ['-stream_loop', '-1', '-i', left_file]
        left = regions.get('left', {})
        lx, ly, lw, lh = left.get('x',0), left.get('y',0), left.get('w',400), left.get('h',400)
        l_portrait = lh > lw
        lt = ',transpose=2' if l_portrait else ''
        filter_parts.append(f'[{inp_idx}:v]{lt.lstrip(",")},scale={lw}:{lh}:force_original_aspect_ratio=decrease[left_s]' if lt else f'[{inp_idx}:v]scale={lw}:{lh}:force_original_aspect_ratio=decrease[left_s]')
        filter_parts.append(f'{output_label}[left_s]overlay={lx}:{ly}[out_l]')
        output_label = '[out_l]'
        inp_idx += 1
    
    # Right decoration
    if right_file and os.path.exists(right_file):
        inputs += ['-stream_loop', '-1', '-i', right_file]
        right = regions.get('right', {})
        rx, ry, rw, rh = right.get('x',0), right.get('y',0), right.get('w',400), right.get('h',400)
        r_portrait = rh > rw
        rt = ',transpose=2' if r_portrait else ''
        filter_parts.append(f'[{inp_idx}:v]{rt.lstrip(",")},scale={rw}:{rh}:force_original_aspect_ratio=decrease[right_s]' if rt else f'[{inp_idx}:v]scale={rw}:{rh}:force_original_aspect_ratio=decrease[right_s]')
        filter_parts.append(f'{output_label}[right_s]overlay={rx}:{ry}[out_r]')
        output_label = '[out_r]'
    
    # Final scale + format
    filter_parts.append(f'{output_label}scale=1920:1080[out_scaled]')
    filter_parts.append(f'[out_scaled]format=yuv420p[out_fmt]')
    
    cmd = inputs + [
        '-filter_complex', ';'.join(filter_parts),
        '-map', '[out_fmt]', '-map', '1:a?',
        '-pix_fmt', 'yuv420p',
        '-c:v', codec, '-b:v', f'{bitrate}k',
        '-c:a', 'flac', '-ar', '96000',
        '-movflags', '+faststart', '-t', str(dur), output_path
    ]
    _run_ffmpeg(cmd, task_id, output_path, dur)

def _process_rotate(task_id, video_path, direction, output_path, codec, bitrate):
    """横转竖模式"""
    dur = _get_duration(video_path)
    info = _get_info(video_path)
    vw, vh = info.get('width', 1920), info.get('height', 1080)
    
    # Rotate
    transpose = 'transpose=1' if direction == 'cw' else 'transpose=2'
    # After rotation: 1080x1920
    new_w, new_h = vh, vw  # swap
    
    # Scale to standard portrait resolution
    target_w, target_h = 1080, 1920
    
    cmd = [FFMPEG, '-y', '-i', video_path,
           '-vf', f'{transpose},scale={target_w}:{target_h},format=yuv420p',
           '-pix_fmt', 'yuv420p',
           '-c:v', codec, '-b:v', f'{bitrate}k',
           '-c:a', 'flac', '-ar', '96000',
           '-movflags', '+faststart', '-t', str(dur), output_path]
    _run_ffmpeg(cmd, task_id, output_path, dur)

def _process_format(task_id, video_path, target_codec, output_path, bitrate):
    """格式转换"""
    dur = _get_duration(video_path)
    cmd = [FFMPEG, '-y', '-i', video_path,
           '-c:v', target_codec, '-b:v', f'{bitrate}k',
           '-c:a', 'aac', '-b:a', '192k',
           '-movflags', '+faststart', output_path]
    _run_ffmpeg(cmd, task_id, output_path, dur)

# ─── Background worker ───

def _process_worker(task_id, mode, params):
    """Background processing thread"""
    try:
        tasks[task_id]['status'] = 'processing'
        _log(task_id, f'🚀 开始处理 [{mode}]')
        
        video = params['video']
        out_name = params.get('output_name', f'output_{task_id[:8]}.mp4')
        output_path = os.path.join(OUTPUT, out_name)
        codec = params.get('codec', 'hevc_nvenc')
        bitrate = params.get('bitrate', 6000)
        
        if mode == 'frame':
            _process_frame(task_id, video, params['template'], params['roi'], output_path, codec, bitrate)
        elif mode == 'pip':
            _process_pip(task_id, video, params['template'], params.get('regions', {}),
                        params.get('left_file'), params.get('right_file'),
                        output_path, codec, bitrate)
        elif mode == 'rotate':
            _process_rotate(task_id, video, params.get('direction', 'cw'), output_path, codec, bitrate)
        elif mode == 'format':
            _process_format(task_id, video, params.get('target_codec', 'libx264'), output_path, bitrate)
        
        if os.path.exists(output_path):
            tasks[task_id]['output_file'] = out_name
            tasks[task_id]['output_size'] = os.path.getsize(output_path)
    except Exception as e:
        tasks[task_id]['status'] = 'error'
        _log(task_id, f'❌ 异常: {str(e)}')

# ─── Routes ───

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/info', methods=['POST'])
def api_info():
    """Get video info"""
    path = request.json.get('path', '')
    if not path or not os.path.exists(path):
        return jsonify({'error': '文件不存在'}), 400
    info = _get_info(path)
    info['filename'] = os.path.basename(path)
    info['duration_str'] = f'{int(info.get("duration",0)//60)}:{int(info.get("duration",0)%60):02d}'
    return jsonify(info)

@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload video files"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'error': '空文件名'}), 400
    fname = secure_filename(f.filename)
    # Preserve original name for Chinese filenames
    if not fname or fname == '_':
        fname = f.filename.replace('\\', '/').split('/')[-1]
    path = os.path.join(UPLOAD, fname)
    f.save(path)
    info = _get_info(path)
    return jsonify({
        'path': path,
        'filename': fname,
        'size': os.path.getsize(path),
        'duration': info.get('duration', 0),
        'width': info.get('width', 0),
        'height': info.get('height', 0),
        'codec': info.get('codec', '')
    })

@app.route('/api/process', methods=['POST'])
def api_process():
    """Start processing"""
    data = request.json
    mode = data.get('mode', 'frame')
    params = data.get('params', {})
    
    if not params.get('video') or not os.path.exists(params['video']):
        return jsonify({'error': '视频文件不存在'}), 400
    
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'queued',
        'progress': 0,
        'eta': '',
        'log': [],
        'output_file': None,
        'output_size': 0,
        'mode': mode,
        'start_time': time.time()
    }
    
    t = threading.Thread(target=_process_worker, args=(task_id, mode, params), daemon=True)
    t.start()
    
    return jsonify({'task_id': task_id})

@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    """SSE endpoint for real-time progress"""
    def generate():
        while True:
            if task_id not in tasks:
                yield f'data: {json.dumps({"status": "not_found"})}\n\n'
                break
            t = tasks[task_id]
            data = {
                'status': t['status'],
                'progress': t['progress'],
                'eta': t['eta'],
                'log': t['log'][-5:],  # Last 5 lines
                'output_file': t.get('output_file'),
                'output_size': t.get('output_size', 0),
                'elapsed': int(time.time() - t['start_time'])
            }
            yield f'data: {json.dumps(data)}\n\n'
            if t['status'] in ('done', 'error'):
                break
            time.sleep(1)
    return Response(generate(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/download/<filename>')
def api_download(filename):
    """Download processed file"""
    path = os.path.join(OUTPUT, filename)
    if not os.path.exists(path):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(path, as_attachment=True)

@app.route('/api/templates')
def api_templates():
    """List available templates"""
    tpl_dir = os.path.join(BASE, 'templates_img')
    if not os.path.exists(tpl_dir):
        os.makedirs(tpl_dir, exist_ok=True)
        return jsonify([])
    files = []
    for ext in ('*.png', '*.jpg', '*.jpeg', '*.bmp', '*.webp'):
        files.extend(glob.glob(os.path.join(tpl_dir, ext)))
    return jsonify([{'name': os.path.basename(f), 'path': f} for f in files])

@app.route('/api/preview', methods=['POST'])
def api_preview():
    """Generate FFmpeg command preview (no execution)"""
    data = request.json
    mode = data.get('mode', 'frame')
    params = data.get('params', {})
    
    video = params.get('video', 'input.mp4')
    codec = params.get('codec', 'hevc_nvenc')
    bitrate = params.get('bitrate', 6000)
    
    if mode == 'frame':
        tpl = params.get('template', 'template.png')
        roi = params.get('roi', [66, 51, 1447, 827])
        cmd = f'ffmpeg -y -loop 1 -i "{tpl}" -i "{video}" \\\n  -filter_complex "\\\n    [0:v]scale=1920:1080[bg];\\\n    [1:v]scale={roi[2]}:{roi[3]}:force_original_aspect_ratio=decrease[fg];\\\n    [bg][fg]overlay={roi[0]}:{roi[1]},format=yuv420p[out]" \\\n  -map [out] -map 1:a? \\\n  -c:v {codec} -b:v {bitrate}k \\\n  -c:a flac -ar 96000 \\\n  -movflags +faststart output.mp4'
    elif mode == 'pip':
        cmd = f'ffmpeg -y -loop 1 -i template.png -i "{video}" \\\n  -filter_complex "..." \\\n  -c:v {codec} -b:v {bitrate}k \\\n  -c:a flac -ar 96000 output.mp4'
    elif mode == 'rotate':
        d = params.get('direction', 'cw')
        t = 'transpose=1' if d == 'cw' else 'transpose=2'
        cmd = f'ffmpeg -y -i "{video}" \\\n  -vf "{t},scale=1080:1920,format=yuv420p" \\\n  -c:v {codec} -b:v {bitrate}k \\\n  -c:a flac -ar 96000 output.mp4'
    elif mode == 'format':
        tc = params.get('target_codec', 'libx264')
        cmd = f'ffmpeg -y -i "{video}" \\\n  -c:v {tc} -b:v {bitrate}k \\\n  -c:a aac -b:a 192k output.mp4'
    else:
        cmd = '# Unknown mode'
    
    return jsonify({'command': cmd})

# ─── Merge: concat multiple videos ───

def _concat_videos(task_id, video_list, output_path, codec, bitrate):
    """Merge multiple videos using concat demuxer"""
    import tempfile
    list_file = os.path.join(OUTPUT, f'_concat_{task_id}.txt')
    with open(list_file, 'w', encoding='utf-8') as f:
        for v in video_list:
            f.write(f"file '{v.replace(chr(39), chr(39)+chr(92)+chr(39))}'\n")
    total_dur = sum(_get_duration(v) for v in video_list)
    cmd = [FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
           '-c', 'copy', '-movflags', '+faststart', output_path]
    _run_ffmpeg(cmd, task_id, output_path, total_dur)
    try: os.remove(list_file)
    except: pass

@app.route('/api/merge', methods=['POST'])
def api_merge():
    """Merge multiple videos into one"""
    data = request.json
    videos = data.get('videos', [])
    if len(videos) < 2:
        return jsonify({'error': '至少需要2个视频'}), 400
    codec = data.get('codec', 'copy')
    bitrate = data.get('bitrate', 6000)
    out_name = data.get('output_name', f'merged_{int(time.time())}.mp4')
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'queued', 'progress': 0, 'eta': '', 'log': [],
        'output_file': None, 'output_size': 0, 'mode': 'merge',
        'start_time': time.time()
    }
    output_path = os.path.join(OUTPUT, out_name)
    t = threading.Thread(target=_concat_videos,
                         args=(task_id, videos, output_path, codec, bitrate), daemon=True)
    t.start()
    return jsonify({'task_id': task_id})

# ─── Pipeline: chain processing steps ───

def _process_pipeline(task_id, video_path, steps, params, output_path):
    """Process video through multiple steps sequentially"""
    current_input = video_path
    codec = params.get('codec', 'hevc_nvenc')
    bitrate = params.get('bitrate', 6000)

    for i, step in enumerate(steps):
        _log(task_id, f'📌 步骤 {i+1}/{len(steps)}: {step}')
        step_output = os.path.join(OUTPUT, f'_pipe_{task_id}_step{i}.mp4')

        if step == 'rotate':
            direction = params.get('direction', 'cw')
            _process_rotate(task_id, current_input, direction, step_output, codec, bitrate)
        elif step == 'frame':
            template = params.get('template', '')
            roi = params.get('roi', [66, 51, 1447, 827])
            _process_frame(task_id, current_input, template, roi, step_output, codec, bitrate)
        elif step == 'pip':
            template = params.get('template', '')
            regions = params.get('regions', {})
            left_file = params.get('left_file')
            right_file = params.get('right_file')
            _process_pip(task_id, current_input, template, regions, left_file, right_file,
                        step_output, codec, bitrate)

        if tasks[task_id]['status'] == 'error':
            return
        # Clean up previous temp (not original)
        if current_input != video_path and os.path.exists(current_input):
            try: os.remove(current_input)
            except: pass
        current_input = step_output

    # Rename final output
    if os.path.exists(current_input):
        if current_input != output_path:
            os.rename(current_input, output_path)
        tasks[task_id]['progress'] = 100
        tasks[task_id]['status'] = 'done'
        tasks[task_id]['output_file'] = os.path.basename(output_path)
        tasks[task_id]['output_size'] = os.path.getsize(output_path)
        _log(task_id, f'✅ 流水线完成: {os.path.basename(output_path)}')
    else:
        tasks[task_id]['status'] = 'error'
        _log(task_id, '❌ 流水线处理失败')
    # Clean up temp files
    for f in glob.glob(os.path.join(OUTPUT, f'_pipe_{task_id}_*')):
        try: os.remove(f)
        except: pass

@app.route('/api/pipeline', methods=['POST'])
def api_pipeline():
    """Start pipeline processing"""
    data = request.json
    video = data.get('video', '')
    steps = data.get('steps', [])
    params = data.get('params', {})

    if not video or not os.path.exists(video):
        return jsonify({'error': '视频文件不存在'}), 400
    if not steps:
        return jsonify({'error': '请选择至少一个步骤'}), 400

    out_name = data.get('output_name', f'pipeline_{int(time.time())}.mp4')
    output_path = os.path.join(OUTPUT, out_name)
    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'queued', 'progress': 0, 'eta': '', 'log': [],
        'output_file': None, 'output_size': 0, 'mode': 'pipeline',
        'start_time': time.time()
    }
    t = threading.Thread(target=_process_pipeline,
                         args=(task_id, video, steps, params, output_path), daemon=True)
    t.start()
    return jsonify({'task_id': task_id})

# ─── Layout Preview: generate preview image with region overlays ───

@app.route('/api/preview-layout', methods=['POST'])
def api_preview_layout():
    """Generate a preview image with region overlays"""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return jsonify({'error': '需要安装 opencv-python'}), 500

    data = request.json
    template_path = data.get('template', '')
    regions = data.get('regions', {})  # {name: {x, y, w, h}}

    if not template_path or not os.path.exists(template_path):
        return jsonify({'error': '模板文件不存在'}), 400

    # Read template
    ext = os.path.splitext(template_path)[1].lower()
    if ext in ('.mp4', '.mkv', '.avi', '.flv', '.ts'):
        cap = cv2.VideoCapture(template_path)
        ret, img = cap.read()
        cap.release()
        if not ret:
            return jsonify({'error': '无法读取视频帧'}), 500
    else:
        img = cv2.imread(template_path)
        if img is None:
            return jsonify({'error': '无法读取图片'}), 500

    # Draw regions
    overlay = img.copy()
    colors = {
        'left': (255, 154, 76),   # BGR blue
        'center': (196, 205, 78), # BGR green
        'right': (107, 107, 255), # BGR red
        'video': (196, 205, 78),
    }
    for name, rect in regions.items():
        if isinstance(rect, dict):
            x, y, w, h = rect.get('x',0), rect.get('y',0), rect.get('w',100), rect.get('h',100)
        elif isinstance(rect, (list, tuple)) and len(rect) == 4:
            x, y, w, h = rect
        else:
            continue
        color = colors.get(name, (255, 255, 255))
        cv2.rectangle(overlay, (x, y), (x+w, y+h), color, -1)
        cv2.rectangle(img, (x, y), (x+w, y+h), color, 3)
        label = f'{name} ({w}x{h})'
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(img, (x, y-th-10), (x+tw+8, y), color, -1)
        cv2.putText(img, label, (x+4, y-6), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)

    cv2.addWeighted(overlay, 0.2, img, 0.8, 0, img)

    # Encode to base64
    _, buf = cv2.imencode('.png', img)
    import base64
    b64 = base64.b64encode(buf).decode('utf-8')
    return jsonify({'image': f'data:image/png;base64,{b64}'})

# ─── Intro/Outro append ───

def _append_intro_outro(task_id, video_path, intro_path, outro_path, output_path):
    """Append intro and/or outro to video"""
    import tempfile
    parts = []
    if intro_path and os.path.exists(intro_path):
        parts.append(intro_path)
    parts.append(video_path)
    if outro_path and os.path.exists(outro_path):
        parts.append(outro_path)
    if len(parts) < 2:
        return  # nothing to concat

    list_file = os.path.join(OUTPUT, f'_intro_outro_{task_id}.txt')
    with open(list_file, 'w', encoding='utf-8') as f:
        for p in parts:
            f.write(f"file '{p.replace(chr(39), chr(39)+chr(92)+chr(39))}'\n")
    cmd = [FFMPEG, '-y', '-f', 'concat', '-safe', '0', '-i', list_file,
           '-c', 'copy', '-movflags', '+faststart', output_path]
    dur = sum(_get_duration(p) for p in parts)
    _run_ffmpeg(cmd, task_id, output_path, dur)
    try: os.remove(list_file)
    except: pass

if __name__ == '__main__':
    print('视频处理工具 Web版')
    print('http://localhost:8765')
    app.run(host='0.0.0.0', port=8765, debug=False, threaded=True)
