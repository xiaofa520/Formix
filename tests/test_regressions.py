import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QObject, QSettings, QThreadPool, QTimer
from PySide6.QtGui import QFontDatabase, QImage, QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QStyle, QStyleOptionButton
from PySide6.QtCore import Qt
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from formix import background_work, engines, hls_input, main, model_store, output_safety, tasks, worker
from formix.file_import import FileScanTask
from formix.localization import LanguageManager
from formix.process_utils import run_process

APP = QApplication.instance() or QApplication([])
if sys.platform == 'win32' and not QFontDatabase.families():
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')


def wait_for(predicate, timeout=5000):
    deadline = time.monotonic() + timeout / 1000
    while not predicate() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(.005)  # Release the GIL so Python QRunnables can progress.
    if not predicate():
        raise AssertionError('Timed out waiting for Qt completion')


class Parent(QObject):
    def t(self, key, **kwargs):
        return key + str(kwargs)


class RegressionTests(unittest.TestCase):
    def test_selected_pdf_model_survives_window_restart_and_ram_change(self):
        root=self.root
        class AuditWindow(main.Window):
            @staticmethod
            def make_default_output_directory(): return root
        path=str(root/'model-preference.ini')
        first=AuditWindow(LanguageManager(QSettings(path,QSettings.Format.IniFormat)),startup_checks=False)
        try:
            first.model_combo.setCurrentIndex(first.model_combo.findData('pp-ocrv5-mobile'))
            first.model_combo.setCurrentIndex(first.model_combo.findData('granite-docling-258m'))
            persisted=QSettings(path,QSettings.Format.IniFormat)
            self.assertEqual(persisted.value('pdf/model'), 'granite-docling-258m')
        finally:
            first.close()
            APP.processEvents()
        with patch.object(main, 'available_system_memory_gib', return_value=1):
            second=AuditWindow(LanguageManager(QSettings(path,QSettings.Format.IniFormat)),startup_checks=False)
        try:
            self.assertEqual(second.model_combo.currentData(), 'granite-docling-258m')
            self.assertEqual(second.tasks.models.name, 'granite-docling-258m')
        finally:
            second.close()
            APP.processEvents()

    def test_folder_open_uses_native_shell_and_reports_rejection(self):
        errors=[]
        with patch.object(background_work.sys, 'platform', 'win32'), patch.object(background_work.os, 'startfile', create=True, side_effect=PermissionError('shell denied')) as launch:
            background_work.open_folder_async(self.root, lambda folder:errors.append(folder))
            wait_for(lambda: bool(errors))
        launch.assert_called_once_with(str(self.root), 'open')
        self.assertEqual(errors, [self.root])
        self.assertNotIn(self.root, background_work._opening_folders)

    def test_folder_open_empty_path_does_not_open_working_directory(self):
        errors=[]
        with patch.object(background_work.os, 'startfile', create=True) as launch:
            background_work.open_folder_async('', lambda folder:errors.append(folder))
            wait_for(lambda: bool(errors))
            launch.assert_not_called()

    def test_folder_open_dispatches_existing_unicode_folder(self):
        folder=self.root/'中文 空格（目录）'
        folder.mkdir()
        errors=[]
        with patch.object(background_work.sys, 'platform', 'win32'), patch.object(background_work.os, 'startfile', create=True) as launch:
            background_work.open_folder_async(folder, errors.append)
            wait_for(lambda:folder not in background_work._opening_folders)
            launch.assert_called_once_with(str(folder), 'open')
        self.assertEqual(errors, [])

    def test_conversion_stages_in_root_cache_without_touching_destination(self):
        destination = self.root/'uncreated-output'
        with patch.object(tasks, 'ROOT', self.root):
            folder, stage = tasks.prepare_conversion_output(destination)
        self.assertEqual(folder, destination)
        self.assertEqual(stage.parent, self.root/'cache')
        self.assertFalse(destination.exists())

    def test_cross_device_publication_and_existing_file(self):
        import errno
        source=self.root/'cached.txt'
        source.write_bytes(b'complete result')
        base=self.root/'output.txt'
        base.write_bytes(b'existing document')
        original=tasks.os.replace
        def replace(src, dst):
            if src == source:
                raise OSError(errno.EXDEV, 'cross device')
            return original(src, dst)
        with patch.object(tasks.os, 'replace', side_effect=replace):
            destination=tasks.publish_file(source, base)
        self.assertEqual(base.read_bytes(), b'existing document')
        self.assertEqual(destination.read_bytes(), b'complete result')
        self.assertEqual(source.read_bytes(), b'complete result')
        self.assertFalse(list(self.root.glob('.formix-copy-*')))

    def test_final_permission_failure_preserves_converted_file(self):
        service = tasks.TaskService(self.root/'models', self.parent)
        service.active_job = ('PDF 转换', self.root/'input.pdf', 'docx', '', self.root, 'cpu')
        service.stage = self.root/'stage'
        service.stage.mkdir()
        service.out = service.stage/'result.docx'
        service.out.write_bytes(b'converted document')
        service.base = self.root/'published.docx'
        with patch.object(tasks.os, 'replace', side_effect=PermissionError('permission changed')):
            service.done(0)
            wait_for(lambda:service.active_job is None)
        self.assertEqual(service.results['conversion_failed'], 1)
        self.assertEqual(service.out.read_bytes(), b'converted document')
        self.assertFalse(service.base.exists())

    def test_cross_device_copy_failure_keeps_cache_and_removes_partial_output(self):
        import errno
        source=self.root/'cached.txt'
        source.write_bytes(b'complete result')
        base=self.root/'output.txt'
        with patch.object(tasks.os, 'replace', side_effect=OSError(errno.EXDEV, 'cross device')), patch.object(tasks.shutil, 'copyfileobj', side_effect=OSError(errno.ENOSPC, 'full')):
            with self.assertRaises(OSError):
                tasks.publish_file(source, base)
        self.assertEqual(source.read_bytes(), b'complete result')
        self.assertFalse(base.exists())
        self.assertFalse(list(self.root.glob('.formix-copy-*')))

    def test_cached_hls_publishes_playlist_and_segments(self):
        service=tasks.TaskService(self.root/'models', self.parent)
        service.out=self.root/'cached.m3u8'
        service.out.write_text('#EXTM3U\nold/part.ts\n#EXT-X-ENDLIST\n','utf-8')
        service.segment_dir=self.root/'segments'
        service.segment_dir.mkdir()
        (service.segment_dir/'part.ts').write_bytes(b'segment data')
        service.base=self.root/'output'/'movie'
        result=service.commit_hls_output()
        self.assertEqual(result, self.root/'output/movie/index.m3u8')
        self.assertIn('segment_00000.ts',result.read_text('utf-8'))
        self.assertEqual((self.root/'output/movie/segment_00000.ts').read_bytes(), b'segment data')

    def test_hls_missing_segment_does_not_publish_a_package(self):
        service=tasks.TaskService(self.root/'models', self.parent)
        service.out=self.root/'cached.m3u8'
        service.out.write_text('#EXTM3U\nmissing.ts\n#EXT-X-ENDLIST\n','utf-8')
        service.segment_dir=self.root/'segments';service.segment_dir.mkdir()
        service.base=self.root/'output'/'movie'
        with self.assertRaisesRegex(ValueError,'分片缺失'):
            service.commit_hls_output()
        self.assertFalse(service.base.exists())

    def test_hls_package_collision_preserves_existing_directory(self):
        service=tasks.TaskService(self.root/'models', self.parent)
        service.out=self.root/'cached.m3u8'
        service.out.write_text('#EXTM3U\npart.ts\n#EXT-X-ENDLIST\n','utf-8')
        service.segment_dir=self.root/'segments';service.segment_dir.mkdir()
        (service.segment_dir/'part.ts').write_bytes(b'video')
        service.base=self.root/'output'/'movie';service.base.mkdir(parents=True)
        (service.base/'keep.txt').write_text('keep')
        result=service.commit_hls_output()
        self.assertEqual(result.parent.name,'movie (1)')
        self.assertEqual((service.base/'keep.txt').read_text(),'keep')
        self.assertEqual(result.read_bytes().count(b'\r'),0)

    def test_output_disk_full_is_not_hidden_as_permission_error(self):
        import errno
        with patch.object(tasks, 'create_stage', side_effect=OSError(errno.ENOSPC, 'disk full')) as create:
            with self.assertRaises(OSError) as error:
                tasks.prepare_conversion_output(self.root)
            self.assertEqual(error.exception.errno, errno.ENOSPC)
            create.assert_called_once()

    def test_denied_stage_directory_does_not_retry_or_block_qt(self):
        with patch.object(Path, 'mkdir', side_effect=PermissionError('Access denied')) as mkdir:
            with self.assertRaises(PermissionError):
                tasks.create_stage(Path('denied-output'), '.formix-')
            mkdir.assert_called_once()

    def test_stage_name_collisions_have_a_finite_retry_limit(self):
        with patch.object(Path, 'mkdir', side_effect=FileExistsError('collision')) as mkdir:
            with self.assertRaises(FileExistsError):
                tasks.create_stage(Path('output'), '.formix-')
            self.assertEqual(mkdir.call_count, 8)

    def test_denied_stage_fails_job_and_returns_to_event_loop(self):
        service = tasks.TaskService(self.root/'models', self.parent)
        service.queue.append(('PDF 转换', self.root/'scan.pdf', 'docx', '', self.root, 'cpu'))
        with patch.object(tasks, 'create_stage', side_effect=PermissionError('Access denied')) as create:
            service.next_job()
        create.assert_called_once()
        self.assertIsNone(service.active_job)
        self.assertIsNone(service.proc)
        self.assertEqual(service.results['conversion_failed'], 1)
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        wait_for(lambda: ticks)

    def test_model_log_flood_is_batched_and_bounded(self):
        parent = Parent()
        service = tasks.TaskService(Path('models'), parent)
        service.log_page = 'PDF 转换'
        service.recent_lines = {}
        batches = []
        service.log.connect(lambda page, message: batches.append(message))
        for index in range(10000):
            service.log_engine_line(f'loading tensor {index}')
        self.assertEqual(batches, [])
        wait_for(lambda: bool(batches))
        self.assertEqual(len(batches), 1)
        self.assertLessEqual(len(batches[0].splitlines()), 400)
        self.assertIn('loading tensor 9999', batches[0])
        self.assertFalse(service.engine_log_timer.isActive())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.parent = Parent()

    def tearDown(self):
        QThreadPool.globalInstance().waitForDone(5000)
        APP.processEvents()
        self.temp.cleanup()

    def test_html_is_self_contained_and_rejects_outside_resources(self):
        image = self.root/'picture.png'
        image.write_bytes(b'example-image')
        css = self.root/'sheet.css'
        css.write_text('body{background:url("picture.png")}', 'utf-8')
        html = self.root/'document.html'
        html.write_text('<link rel="stylesheet" href="sheet.css"><img src="picture.png">', 'utf-8')
        output_safety.embed_html_assets(html)
        text = html.read_text('utf-8')
        self.assertIn('data:image/png;base64,', text)
        self.assertIn('data:text/css;base64,', text)
        self.assertNotIn('src="picture.png"', text)
        folder = self.root/'nested'
        folder.mkdir()
        bad = folder/'bad.html'
        bad.write_text('<img src="../picture.png">', 'utf-8')
        with self.assertRaises(ValueError):
            output_safety.embed_html_assets(bad)

    def test_csv_formulas_are_text_without_changing_regular_cells(self):
        for value in ('=1+1', '+2+2', '-1+1', '@SUM(1,1)', '  =1', '\ttext'):
            self.assertEqual(output_safety.csv_text(value), "'"+value)
        self.assertEqual(output_safety.csv_text('ordinary text'), 'ordinary text')
        self.assertEqual(output_safety.csv_text(12.5), 12.5)
        self.assertIsNone(output_safety.csv_text(None))

    def test_pdf_csv_serialization_uses_formula_protection(self):
        class Doc:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        class Page:
            def extract_tables(self): return [[['=1+1', 'plain']]]
            def close(self): pass
        class Tables(Doc):
            pages = [Page()]
        import pypdfium2, pdfplumber
        with patch.object(pypdfium2, 'PdfDocument', return_value=Doc()), \
             patch.object(pdfplumber, 'open', return_value=Tables()):
            worker.pdf(self.root/'source.pdf', self.root/'out.csv', self.root/'models')
        self.assertIn("'=1+1,plain", (self.root/'out.csv').read_text('utf-8-sig'))

    def test_animation_preserves_frames_and_refuses_silent_static_export(self):
        source = self.root/'source.gif'
        Image.new('RGB',(20,20),'red').save(source, save_all=True,
            append_images=[Image.new('RGB',(20,20),'blue')], duration=[80,160], loop=2)
        try:
            for suffix in ('gif','webp','tiff'):
                target = self.root/('output.'+suffix)
                worker.convert_image(source,target)
                with Image.open(target) as converted:
                    self.assertEqual(converted.n_frames,2)
            for suffix in ('jpg', 'bmp', 'pdf'):
                with self.assertRaises(ValueError):
                    worker.convert_image(source,self.root/('output.'+suffix))
        finally:
            import pyvips
            pyvips.cache_set_max(0)

    def test_real_image_workers_export_readable_bmp_and_pdf(self):
        import pypdfium2
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder = Path(tmp)
            for mode in ('RGB', 'RGBA'):
                source = folder / (mode + '.png')
                Image.new(mode, (80, 60), (255, 0, 0) if mode == 'RGB' else (255, 0, 0, 0)).save(source)
                for extension in ('bmp', 'pdf'):
                    with self.subTest(mode=mode, extension=extension):
                        stage = folder / (mode + '-' + extension)
                        stage.mkdir()
                        command, target = engines.plan('图片转换', source, extension, '', stage, folder/'models')
                        run_process(command, check=True, capture_output=True, timeout=30)
                        if extension == 'bmp':
                            with Image.open(target) as image:
                                image.load()
                                self.assertEqual(image.size, (80, 60))
                                self.assertEqual(image.getpixel((40, 30)), (255, 0, 0) if mode == 'RGB' else (255, 255, 255))
                        else:
                            with pypdfium2.PdfDocument(target) as document:
                                self.assertEqual(len(document), 1)
                                page = document[0]
                                try:
                                    self.assertAlmostEqual(page.get_width()/page.get_height(), 80/60, places=3)
                                    image = page.render().to_pil().convert('RGB')
                                    expected = (255, 0, 0) if mode == 'RGB' else (255, 255, 255)
                                    self.assertTrue(all(abs(a-b) < 8 for a,b in zip(image.getpixel((image.width//2,image.height//2)),expected)))
                                finally:
                                    page.close()

    def test_real_3gp_conversion_preserves_common_video_dimensions(self):
        ffmpeg = engines.executable('ffmpeg')
        if not ffmpeg:
            self.skipTest('FFmpeg not installed')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder = Path(tmp)
            source = folder/'input.mp4'
            run_process([ffmpeg, '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                         'testsrc=size=320x240:rate=10', '-t', '0.3', '-c:v', 'libx264',
                         '-pix_fmt', 'yuv420p', str(source)], check=True, capture_output=True, timeout=30)
            command, target = engines.plan('视频转换', source, '3gp', '', folder, folder/'models')
            run_process(command, check=True, capture_output=True, timeout=30)
            decoded = run_process([ffmpeg, '-nostdin', '-i', str(target), '-f', 'null', '-'],
                                  check=True, capture_output=True, timeout=30)
            self.assertIn(b'320x240', decoded.stderr)
            self.assertIn(b'h264', decoded.stderr)

    def test_optional_image_formats_reach_gui_from_real_worker_probe(self):
        from formix import runtime_check
        root = self.root
        class AuditWindow(main.Window):
            @staticmethod
            def make_default_output_directory(): return root
        settings = QSettings(str(root/'capabilities.ini'), QSettings.Format.IniFormat)
        window = AuditWindow(LanguageManager(settings), startup_checks=False)
        try:
            page = next(p for p in window.pages if p.name == '图片转换')
            self.assertEqual(page.option.findData('heic'), -1)
            self.assertEqual(page.option.findData('avif'), -1)
            window.runtime_check.setArguments(['-X', 'utf8', str(Path(runtime_check.__file__)), '--component', 'libvips'])
            window.runtime_check.start()
            wait_for(lambda: hasattr(window, 'image_formats') and window.runtime_check.state() == window.runtime_check.ProcessState.NotRunning, timeout=40000)
            formats = worker.image_output_formats()
            self.assertEqual([page.option.itemData(i) for i in range(page.option.count())], formats)
            # Simulate an engine update adding HEVC support, then removing it.
            window.set_image_formats(engines.PAGES['图片转换'])
            page.option.setCurrentIndex(page.option.findData('heic'))
            window.set_image_formats(set(formats) - {'heic'})
            self.assertEqual(page.option.findData('heic'), -1)
            self.assertEqual(page.option.currentData(), 'jpg')
            self.assertGreaterEqual(page.option.findData('pdf'), 0)
        finally:
            window.close()
            wait_for(lambda: window.runtime_check.state() == window.runtime_check.ProcessState.NotRunning)

    def playlist(self, body, subfolder='input'):
        folder = self.root/subfolder
        folder.mkdir(exist_ok=True)
        playlist = folder/'list.m3u8'
        playlist.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n'+body+'\n#EXT-X-ENDLIST\n', 'utf-8')
        return playlist

    def test_hls_materializes_only_in_scope_resources_and_keys(self):
        playlist = self.playlist('#EXT-X-KEY:METHOD=AES-128,URI="secret.key"\n#EXTINF:1,\nclip.ts')
        (playlist.parent/'clip.ts').write_bytes(b'media')
        (playlist.parent/'secret.key').write_bytes(b'K'*16)
        safe = hls_input.materialize(playlist,self.root/'cache')
        text = safe.read_text('utf-8')
        self.assertNotIn('clip.ts',text)
        self.assertNotIn('secret.key',text)
        self.assertEqual(len(list(safe.parent.iterdir())),3)

    def test_hls_refuses_directory_escape_network_and_live_sources(self):
        outside = self.root/'outside.ts'
        outside.write_bytes(b'private')
        for i, reference in enumerate(('../outside.ts', outside.as_uri())):
            source = self.playlist('#EXTINF:1,\n'+reference, 'input'+str(i))
            with self.assertRaises(ValueError):
                hls_input.materialize(source,self.root/('cache'+str(i)))
        source=self.playlist('#EXTINF:1,\nhttp://127.0.0.1/clip.ts','private-network')
        address=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',80))]
        with patch.object(socket,'getaddrinfo',return_value=address), self.assertRaises(ValueError):
            hls_input.materialize(source,self.root/'private-network-cache')
        source = self.playlist('#EXTINF:1,\nclip.ts','live')
        source.write_text(source.read_text('utf-8').replace('#EXT-X-ENDLIST',''), 'utf-8')
        with self.assertRaisesRegex(ValueError,'Live HLS'):
            hls_input.materialize(source,self.root/'live-cache')

    def test_hls_nested_manifests_cannot_hide_behind_segment_names(self):
        source=self.playlist('#EXTINF:1,\nnested.ts')
        (source.parent/'nested.ts').write_text('#EXTM3U\n#EXTINF:1,\n../outside.ts\n#EXT-X-ENDLIST\n','utf-8')
        (self.root/'outside.ts').write_bytes(b'private')
        with self.assertRaises(ValueError):
            hls_input.materialize(source,self.root/'cache')

    def test_real_hls_worker_converts_a_verified_local_playlist(self):
        ffmpeg=engines.executable('ffmpeg')
        if not ffmpeg:
            self.skipTest('FFmpeg not installed')
        # Keep FFmpeg fixtures inside the workspace. On Windows, the system
        # temporary directory may be isolated from child converter processes.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            fixture_root=Path(tmp)
            folder=fixture_root/'input'
            folder.mkdir()
            source=folder/'list.m3u8'
            source.write_text('#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nclip.ts\n#EXT-X-ENDLIST\n','utf-8')
            run_process([ffmpeg,'-nostdin','-loglevel','error','-f','lavfi','-i',
                'testsrc=size=64x64:rate=10','-t','1','-c:v','libx264','-f','mpegts',
                str(folder/'clip.ts')],check=True,capture_output=True,timeout=15)
            stage=fixture_root/'stage'
            stage.mkdir()
            command,out=engines.plan('M3U8 合成',source,'mp4','',stage,fixture_root/'models')
            run_process(command,check=True,capture_output=True,timeout=30)
            self.assertGreater(out.stat().st_size,0)

    def test_real_office_html_commit_retains_embedded_image(self):
        if not engines.executable('soffice'):
            self.skipTest('LibreOffice not installed')
        import zipfile
        from docx import Document
        wheel=next((ROOT/'dependencies/windows-x64/wheels').glob('python_docx-*.whl'),None)
        if wheel:
            template=self.root/'template.docx'
            with zipfile.ZipFile(wheel) as archive:
                template.write_bytes(archive.read('docx/templates/default.docx'))
            document=Document(template)
        else:
            document=Document()
        picture=self.root/'picture.png'
        Image.new('RGB',(20,20),'red').save(picture)
        document.add_paragraph('Export with image')
        document.add_picture(str(picture))
        source=self.root/'document.docx'
        document.save(source)
        stage=self.root/'stage'
        stage.mkdir()
        command,out=engines.plan('文档转换',source,'html','',stage,self.root/'models')
        run_process(command,check=True,capture_output=True,timeout=60)
        service=tasks.TaskService(self.root/'models',self.parent)
        service.active_job=('文档转换',source,'html','',self.root,'cpu')
        service.stage,service.out=stage,out
        service.base=self.root/'published.html'
        service.cancelled=False
        service.label='document'
        service.done(0)
        wait_for(lambda:service.active_job is None)
        self.assertEqual(service.results['file_done'],1)
        text=service.base.read_text('utf-8')
        self.assertIn('data:image/png;base64,',text)
        self.assertNotIn('src="document_html_',text)
        wait_for(lambda:not stage.exists(),timeout=15000)

    def test_remote_hls_refuses_file_and_private_addresses(self):
        cache = hls_input.PlaylistCache('https://example.com/main.m3u8',self.root/'cache')
        with self.assertRaises(ValueError):
            cache.resolve(cache.source,'file:///private.ts')
        for address in ('127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1'):
            result = [(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,80))]
            with patch.object(socket,'getaddrinfo',return_value=result), self.assertRaises(ValueError):
                hls_input.public_addresses('example.com',80)

    def test_remote_hls_redirect_revalidates_target(self):
        class Redirect:
            status=302
            def getheader(self,name): return 'http://127.0.0.1/private.ts'
            def close(self): pass
        class Connection:
            def request(self,*args,**kwargs): pass
            def getresponse(self): return Redirect()
            def close(self): pass
        def addresses(host,port,**kwargs):
            return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1' if host=='127.0.0.1' else '8.8.8.8',port))]
        with patch.object(socket,'getaddrinfo',side_effect=addresses), \
             patch.object(hls_input,'_PinnedConnection',return_value=Connection()) as connection, \
             self.assertRaises(ValueError):
            hls_input.http_resource('https://example.com/file.ts',self.root/'part.ts',100,time.monotonic()+10)
        self.assertEqual(connection.call_count,1)

    def test_hls_connect_uses_validated_ip_without_second_dns_lookup(self):
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',80))]
        with patch.object(socket,'socket') as sock, patch.object(socket,'getaddrinfo',side_effect=AssertionError('Second resolution')):
            connection=hls_input._PinnedConnection('example.com',80,addresses,False)
            connection.connect()
            sock.return_value.connect.assert_called_once_with(('8.8.8.8',80))

    def test_damaged_model_replaced_and_failed_switch_rolls_back(self):
        target=self.root/'model'
        target.mkdir()
        (target/'old').write_text('keep')
        staged=self.root/'staged'
        staged.mkdir()
        (staged/'READY').touch()
        rename=Path.rename
        def fail(path,destination):
            if path==staged: raise OSError('Simulated failed publish')
            return rename(path,destination)
        with patch.object(Path,'rename',fail), self.assertRaises(OSError):
            model_store.publish_model(staged,target)
        self.assertEqual((target/'old').read_text(),'keep')
        backup=model_store.publish_model(staged,target)
        self.assertTrue((target/'READY').is_file())
        self.assertTrue((backup/'model/old').is_file())

    def test_file_model_status_does_not_require_filesystem_or_full_scan(self):
        model=main.FileListModel(self.parent)
        with patch.object(Path,'stat',side_effect=AssertionError('UI filesystem access')):
            model.setStringList(['/unknown/a.png','/unknown/b.png'])
            model.set_state('/unknown/a.png','file_queued')
            model.set_state('/unknown/a.png','file_done')
            self.assertEqual(model.pending_sources(),['/unknown/b.png'])
            model.set_state('/unknown/a.png','conversion_failed')
            self.assertEqual(len(model.pending),2)
        model.append_batch([('/unknown/c.png','c.png','2 kB')])
        self.assertEqual(model.rowCount(),3)

    def test_import_metadata_is_batched_without_blocking_qt(self):
        for i in range(150): (self.root/(str(i)+'.png')).touch()
        (self.root/'ignored.txt').touch()
        task=FileScanTask([str(self.root)],{'.png'})
        model=main.FileListModel(self.parent)
        finished=[]
        class Receiver(QObject):
            def batch(self,task,entries):
                model.append_batch(entries)
                task.slots.release()
            def done(self,task,skipped,error): finished.append((skipped,error))
        receiver=Receiver()
        task.signals.batch.connect(receiver.batch)
        task.signals.finished.connect(receiver.done)
        original_stat=Path.stat
        def slow(path,*args,**kwargs):
            if path.suffix=='.png': time.sleep(.002)
            return original_stat(path,*args,**kwargs)
        ticks=[]
        timer=QTimer()
        timer.setInterval(5)
        timer.timeout.connect(lambda:ticks.append(time.monotonic()))
        timer.start()
        with patch.object(Path,'stat',slow):
            QThreadPool.globalInstance().start(task)
            wait_for(lambda:bool(finished))
        timer.stop()
        self.assertEqual(model.rowCount(),150)
        self.assertEqual(finished,[(1,'')])
        self.assertGreater(len(ticks),15)
        self.assertLess(max(b-a for a,b in zip(ticks,ticks[1:])),.2)

    def test_cleanup_returns_to_qt_before_slow_deletion_finishes(self):
        stage=self.root/'stage'
        stage.mkdir()
        service=tasks.TaskService(self.root/'models',self.parent)
        service.stage=stage
        remove=background_work.remove_tree
        def slow(path):
            time.sleep(.2)
            remove(path)
        with patch.object(background_work,'remove_tree',slow):
            start=time.monotonic()
            service.discard_stage()
            self.assertLess(time.monotonic()-start,.1)
            self.assertTrue(stage.exists())
            wait_for(lambda:not stage.exists())

    def test_background_cleanup_removes_readonly_converter_resources(self):
        stage=self.root/'readonly-stage'
        stage.mkdir()
        resource=stage/'picture.png'
        resource.write_bytes(b'image')
        resource.chmod(0o444)
        finished=[]
        background_work.cleanup_path(stage,lambda result,error:finished.append(error))
        wait_for(lambda:bool(finished))
        self.assertEqual(finished,[None])
        self.assertFalse(stage.exists())

    def test_pause_preserves_process_and_continues_in_place(self):
        service=tasks.TaskService(self.root/'models',self.parent)
        service.active_job=('音频转换',self.root/'input.wav','wav','',self.root,'cpu')
        service.job_name='音频转换'
        service.label='counter'
        service.stage=self.root/'stage'
        service.stage.mkdir()
        service.out=None
        service.cancelled=False
        service.metadata_error=False
        counter=service.stage/'counter.txt'
        code="import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); n=0\nwhile True:\n n+=1; p.write_text(str(n)); time.sleep(.02)"
        service.start_process([sys.executable,'-u','-c',code,str(counter)])
        try:
            wait_for(counter.exists)
            pid=service.proc.processId()
            service.toggle_pause()
            self.assertTrue(service.paused)
            saved=counter.read_bytes()
            QTest.qWait(100)
            self.assertEqual(counter.read_bytes(),saved)
            self.assertTrue(service.stage.exists())
            service.toggle_pause()
            self.assertFalse(service.paused)
            self.assertEqual(service.proc.processId(),pid)
            wait_for(lambda:counter.read_bytes()!=saved)
        finally:
            service.stop()
            wait_for(lambda:service.proc is None)

    def test_watchdog_stops_a_task_with_no_progress(self):
        service=tasks.TaskService(self.root/'models',self.parent)
        service.active_job=('音频转换',self.root/'in.wav','wav','',self.root,'cpu')
        service.job_name='音频转换'
        service.label='stalled'
        service.stage=self.root/'stage'
        service.stage.mkdir()
        service.out=None
        service.cancelled=False
        service.metadata_error=False
        service.start_process([sys.executable,'-c','import time; time.sleep(60)'])
        wait_for(lambda:service.proc.processId()!=0)
        service.idle_timeout=.01
        service.disk_signature=(0,0)
        service.last_activity=time.monotonic()-1
        service.check_activity()
        try:
            wait_for(lambda:service.proc is None)
            self.assertEqual(service.results['conversion_failed'],1)
        finally:
            if service.proc:
                service.stop()
                wait_for(lambda:service.proc is None)

    def test_process_timeout_kills_its_spawned_child(self):
        import psutil
        pidfile=self.root/'child.pid'
        code="import subprocess,sys,pathlib,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
        with self.assertRaises(subprocess.TimeoutExpired):
            run_process([sys.executable,'-c',code,str(pidfile)],timeout=1,capture_output=True)
        pid=int(pidfile.read_text())
        wait_for(lambda:not psutil.pid_exists(pid),timeout=3000)

    def test_runtime_components_report_without_waiting_for_other_repairs(self):
        from formix import runtime_check
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from contextlib import redirect_stdout
        release=threading.Event()
        started=threading.Event()
        class Process:
            pid=12345
            def __init__(self,command,**kwargs):
                self.name=command[-1]
                self.stdout=self.lines()
            def lines(self):
                if self.name=='libreoffice':
                    started.set()
                    release.wait(2)
                yield json.dumps({'component':self.name}).encode()+b'\n'
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def wait(self): return 0
        output=io.StringIO()
        lock=threading.Lock()
        with patch.object(runtime_check.subprocess,'Popen',Process), redirect_stdout(output):
            with ThreadPoolExecutor(max_workers=2) as pool:
                slow=pool.submit(runtime_check.check_independently,'libreoffice',lock)
                try:
                    self.assertTrue(started.wait(1))
                    fast=pool.submit(runtime_check.check_independently,'ffmpeg',lock)
                    fast.result(timeout=1)
                    self.assertFalse(slow.done())
                finally:
                    release.set()
                slow.result(timeout=1)
        records=[json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([r['component'] for r in records],['ffmpeg','libreoffice'])

    def test_window_translates_each_bound_control_once_and_closes_without_waiting(self):
        root=self.root
        class AuditWindow(main.Window):
            @staticmethod
            def make_default_output_directory(): return root
        settings=QSettings(str(root/'settings.ini'),QSettings.Format.IniFormat)
        settings.setValue('interface/language','en')
        settings.setValue('interface/fontSize',13)
        language=LanguageManager(settings)
        window=AuditWindow(language,startup_checks=False)
        counts={}
        original=language._set_widget
        def count(widget,key,attribute):
            counts[id(widget)]=counts.get(id(widget),0)+1
            original(widget,key,attribute)
        try:
            window.show()
            QTest.qWait(50)
            image_page=next(page for page in window.pages if page.name=='图片转换')
            (root/'image.png').touch()
            image_page.add_files([str(root/'image.png')])
            wait_for(lambda:not image_page._folder_scans)
            self.assertEqual(image_page.files.rowCount(),1)
            self.assertTrue(image_page.submit.isEnabled())
            # Patch the Python helper instance, never the Qt widget class.
            language._set_widget=count
            window.retranslate()
            self.assertTrue(counts)
            self.assertEqual(max(counts.values()),1)
            window.grab().save(str(ROOT/'output/project_audit/fixed-ui.png'))
            start=time.monotonic()
            window.close()
            self.assertLess(time.monotonic()-start,.1)
            wait_for(lambda:not window.isVisible())
        finally:
            language._set_widget=original
            if window.isVisible():
                window.close()
                wait_for(lambda:not window.isVisible())

    def test_button_hover_press_and_fixed_size_survive_both_themes(self):
        def rendering(button,state):
            option=QStyleOptionButton()
            button.initStyleOption(option)
            option.state &= ~(QStyle.StateFlag.State_MouseOver | QStyle.StateFlag.State_HasFocus | QStyle.StateFlag.State_Sunken)
            if state!='normal':option.state |= QStyle.StateFlag.State_MouseOver
            if state=='pressed':option.state |= QStyle.StateFlag.State_Sunken
            image=QImage(button.size(),QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.magenta)
            painter=QPainter(image)
            button.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,button)
            painter.end()
            return image
        for dark in (False,True):
            main.apply_theme(APP,dark)
            for name in ('secondary','logAction','importIconAction'):
                button=QPushButton()
                button.setObjectName(name)
                if name!='logAction':button.setProperty('contentAction',True)
                button.setFixedSize(32,32)
                button.ensurePolished()
                self.assertNotEqual(rendering(button,'normal'),rendering(button,'hover'), (dark, name))
                self.assertNotEqual(rendering(button,'hover'),rendering(button,'pressed'), (dark, name))
                self.assertEqual([button.width(),button.height()],[32,32])
                button.deleteLater()


if __name__=='__main__':
    unittest.main()
