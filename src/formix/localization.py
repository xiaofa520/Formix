"""Small, offline interface translations and system-locale selection."""
from PySide6.QtCore import QObject, QLocale, QSettings, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QLabel, QLineEdit, QPushButton, QWidget


LANGUAGE_CODES = ("zh_CN", "zh_TW", "en", "ja", "ko", "ru", "fr")
LANGUAGE_NAMES = {
    "zh_CN": "简体中文",
    "zh_TW": "繁體中文",
    "en": "English",
    "ja": "日本語",
    "ko": "한국어",
    "ru": "Русский",
    "fr": "Français",
}

# Tuple order follows LANGUAGE_CODES. Keys double as stable IDs for Qt widgets.
TEXT = {
    "image_ocr_model": ("识别模型", "識別模型", "Recognition model", "認識モデル", "인식 모델", "Модель распознавания", "Modèle de reconnaissance"),
    "image_ocr_model_hint": ('<a href="settings" style="color: #ffffff; text-decoration: none;">未下载的模型请到设置中下载</a>', "獨立於 PDF 模型；請先在設定下載模型。", '<a href="settings" style="color: #ffffff; text-decoration: none;">Download missing models in Settings</a>', "PDF とは別のモデルです。設定でダウンロードしてください。", "PDF와 별도 설정입니다. 설정에서 모델을 다운로드하세요.", "Независимо от PDF. Загрузите модель в настройках.", "Indépendant du PDF. Téléchargez les modèles dans les paramètres."),
    "gpu_hybrid": ("CPU + 显卡协同", "CPU + 顯示卡協同", "CPU + GPU", "CPU + GPU", "CPU + GPU", "CPU + GPU", "CPU + GPU"),
    "video_gpu_pipeline": ("显卡视频解码 / 编码（{encoder}），CPU 处理音频和封装", "顯示卡解碼 / 編碼（{encoder}），CPU 處理音訊與封裝", "GPU video decoding / encoding ({encoder}); CPU audio and muxing", "GPU decode / encode ({encoder})", "GPU decode / encode ({encoder})", "GPU decode / encode ({encoder})", "GPU decode / encode ({encoder})"),
    "video_hybrid_pipeline": ("CPU 解码与滤镜 + 显卡编码（{encoder}）", "CPU 解碼與濾鏡 + 顯示卡編碼（{encoder}）", "CPU decoding and filters + GPU encoding ({encoder})", "CPU + GPU ({encoder})", "CPU + GPU ({encoder})", "CPU + GPU ({encoder})", "CPU + GPU ({encoder})"),
    "image_ocr_result": ("识别结果", "識別結果", "Recognized text", "認識結果", "인식 결과", "Результат распознавания", "Texte reconnu"),
    "image_ocr_only_copy": ("仅显示 / 复制（不生成文件）", "僅顯示 / 複製（不產生檔案）", "View / copy only (no file)", "表示・コピーのみ", "보기 / 복사만", "Только просмотр / копирование", "Afficher / copier sans fichier"),
    "image_ocr_copy_done": ("识别完成，可在结果区复制；未生成文档文件。", "識別完成，可複製；未產生文件。", "Text ready to copy; no document file created.", "認識完了。ファイルは作成されません。", "인식 완료. 파일 생성 없음.", "Текст готов. Файл не создан.", "Texte prêt. Aucun fichier créé."),
    "image_ocr_copy": ("复制识别文字", "複製識別文字", "Copy text", "テキストをコピー", "텍스트 복사", "Копировать текст", "Copier le texte"),
    "image_ocr_hint": ("识别完成后显示最近一张图片的文字，可编辑后复制。", "完成後顯示最近圖片文字，可編輯及複製。", "Text from the latest image appears here; edit and copy it.", "最新画像のテキストを編集してコピーできます。", "최근 이미지의 텍스트를 편집하고 복사하세요.", "Здесь можно редактировать и копировать текст последнего изображения.", "Modifiez et copiez ici le texte de la dernière image."),
    "page_image_ocr": ("图片提取文字", "圖片提取文字", "Image to text", "画像から文字抽出", "이미지 텍스트 추출", "Текст из изображения", "Image vers texte"),
    "model_download_log": ("日志", "日誌", "Log", "ログ", "로그", "Журнал", "Journal"),
    "image_icon_sizes": ("ICO 图标尺寸", "ICO 圖示尺寸", "ICO icon sizes", "ICO アイコンサイズ", "ICO 아이콘 크기", "Размеры значка ICO", "Tailles de l’icône ICO"),
    "image_icon_all": ("全部尺寸（32、64、128）", "全部尺寸（32、64、128）", "All sizes (32, 64, 128)", "すべてのサイズ（32、64、128）", "모든 크기 (32, 64, 128)", "Все размеры (32, 64, 128)", "Toutes les tailles (32, 64, 128)"),
    "image_icon_32": ("32 × 32", "32 × 32", "32 × 32", "32 × 32", "32 × 32", "32 × 32", "32 × 32"),
    "image_icon_64": ("64 × 64", "64 × 64", "64 × 64", "64 × 64", "64 × 64", "64 × 64", "64 × 64"),
    "image_icon_128": ("128 × 128", "128 × 128", "128 × 128", "128 × 128", "128 × 128", "128 × 128", "128 × 128"),
    "image_vector_svg": ("SVG（保留矢量）", "SVG（保留向量）", "SVG (preserve vectors)", "SVG（ベクターを保持）", "SVG (벡터 유지)", "SVG (сохранить векторы)", "SVG (conserver les vecteurs)"),
    "image_vector_pdf": ("PDF（保留矢量）", "PDF（保留向量）", "PDF (preserve vectors)", "PDF（ベクターを保持）", "PDF (벡터 유지)", "PDF (сохранить векторы)", "PDF (conserver les vecteurs)"),
    "log_queued_count": ("已将 {count} 个文件加入队列。", "已將 {count} 個檔案加入佇列。", "Queued {count} files.", "{count} ファイルをキューに追加しました。", "파일 {count}개를 대기열에 추가했습니다.", "В очередь добавлено файлов: {count}.", "{count} fichiers ajoutés à la file."),
    "task_stalled": ("任务长时间没有进展，已停止。请检查输入或网络后重试。", "工作長時間沒有進展，已停止。請檢查輸入或網路後重試。", "The task stopped after making no progress. Check the input or network and retry.", "長時間進捗がないため停止しました。入力またはネットワークを確認してください。", "진행이 없어 작업을 중지했습니다. 입력 또는 네트워크를 확인하세요.", "Задача остановлена из-за отсутствия прогресса. Проверьте файл или сеть.", "Tâche arrêtée faute de progression. Vérifiez le fichier ou le réseau."),
    "runtime_preparing": ("正在准备运行环境…", "正在準備執行環境…", "Preparing runtime…", "実行環境を準備中…", "실행 환경 준비 중…", "Подготовка компонентов…", "Préparation des composants…"),
    "runtime_ready": ("运行环境已就绪", "執行環境已就緒", "Runtime ready", "実行環境の準備完了", "실행 환경 준비 완료", "Компоненты готовы", "Composants prêts"),
    "runtime_failed": ("运行环境准备失败。{reason}", "執行環境準備失敗。{reason}", "Runtime preparation failed. {reason}", "実行環境の準備に失敗しました。{reason}", "실행 환경 준비 실패. {reason}", "Не удалось подготовить компоненты. {reason}", "Échec de préparation des composants. {reason}"),
    "log_export": ("导出日志", "匯出記錄", "Export log", "ログを保存", "로그 내보내기", "Экспорт журнала", "Exporter le journal"),
    "log_copy_errors": ("复制报错", "複製錯誤", "Copy errors", "エラーをコピー", "오류 복사", "Копировать ошибки", "Copier les erreurs"),
    "log_errors_copied": ("已复制 {count} 条报错日志", "已複製 {count} 則錯誤記錄", "Copied {count} error log lines", "エラーログを {count} 件コピーしました", "오류 로그 {count}개를 복사했습니다", "Скопировано строк ошибок: {count}", "{count} lignes d’erreur copiées"),
    "log_no_errors": ("当前页面没有报错日志", "目前頁面沒有錯誤記錄", "No error logs on this page", "このページにエラーログはありません", "이 페이지에 오류 로그가 없습니다", "На этой странице нет ошибок", "Aucune erreur sur cette page"),
    "runtime_title": ("缺少运行环境", "缺少執行環境", "Missing runtime", "実行環境がありません", "실행 환경 누락", "Отсутствует компонент", "Composant manquant"),
    "runtime_download": ("下载", "下載", "Download", "ダウンロード", "다운로드", "Скачать", "Télécharger"),
    "runtime_prompt": ("转换需要安装或修复 {name}。点击「下载」将在默认浏览器中打开官方下载地址。安装后，请重新开始任务。", "轉換需要安裝或修復 {name}。點選「下載」將在預設瀏覽器開啟官方下載網址。安裝後請重新開始工作。", "Install or repair {name} to convert this file. Download opens the official download in your browser. Retry the task after installation.", "{name} をインストールまたは修復してください。ダウンロード先をブラウザーで開きます。インストール後、再試行してください。", "{name} 설치 또는 복구가 필요합니다. 브라우저에서 공식 다운로드를 열고 설치한 후 다시 시도하세요.", "Установите или восстановите {name}. Кнопка откроет официальную загрузку в браузере. После установки повторите задачу.", "Installez ou réparez {name}. Le bouton ouvre le téléchargement officiel dans le navigateur. Réessayez après installation."),
    "office_preparing": ("正在从本地安装包准备 LibreOffice 文档转换环境…", "正在從本機安裝包準備 LibreOffice 文件轉換環境…", "Preparing LibreOffice from the local installer…", "ローカルのインストーラーから LibreOffice を準備中…", "로컬 설치 파일에서 LibreOffice 준비 중…", "Подготовка LibreOffice из локального установщика…", "Préparation de LibreOffice depuis le paquet local…"),
    "restore_jobs": ("恢复任务", "恢復工作", "Restore tasks", "タスクの復元", "작업 복원", "Восстановить задачи", "Reprendre les tâches"),
    "restore_jobs_prompt": ("上次关闭时有 {count} 项未完成的任务。按原顺序恢复处理吗？中途停止的任务将从头开始。", "上次關閉時有 {count} 項未完成的工作。依原順序恢復嗎？中途停止的工作將從頭開始。", "Restore the {count} unfinished tasks in their original order? Interrupted tasks will restart from the beginning.", "未完了の {count} 件を元の順序で復元しますか？中断したタスクは最初から実行します。", "미완료 작업 {count}개를 원래 순서대로 복원할까요? 중단된 작업은 처음부터 시작합니다.", "Восстановить незавершённые задачи ({count}) в прежнем порядке? Прерванная задача начнётся заново.", "Reprendre les {count} tâches inachevées dans leur ordre initial ? La tâche interrompue recommencera depuis le début."),
    "pause_hold_hint": ("短按暂停或继续；按住约 0.8 秒取消当前任务。", "短按暫停或繼續；按住約 0.8 秒取消目前工作。", "Tap to pause or resume; hold for about 0.8 seconds to cancel the current task.", "短押しで一時停止／再開、約 0.8 秒長押しで現在のタスクをキャンセルします。", "짧게 눌러 일시 정지/재개하고, 약 0.8초 길게 눌러 현재 작업을 취소합니다.", "Короткое нажатие — пауза или продолжение; удерживайте около 0,8 с, чтобы отменить задачу.", "Appuyez brièvement pour mettre en pause ou reprendre ; maintenez environ 0,8 s pour annuler la tâche."),
    "recovery_restored": ("已恢复 {count} 项待处理任务；中断的任务会从头开始。", "已恢復 {count} 項待處理工作；中斷的工作會從頭開始。", "Restored {count} pending tasks. Interrupted tasks restart from the beginning.", "未処理のタスク {count} 件を復元しました。中断したタスクは最初から再開します。", "대기 작업 {count}개를 복원했습니다. 중단된 작업은 처음부터 다시 시작합니다.", "Восстановлено задач: {count}. Прерванные задачи начнутся заново.", "{count} tâches en attente restaurées. Les tâches interrompues recommencent depuis le début."),
    "file_queued": ("等待中", "等待中", "Queued", "待機中", "대기 중", "В очереди", "En attente"),
    "file_paused": ("已暂停", "已暫停", "Paused", "一時停止中", "일시 정지", "Приостановлено", "En pause"),
    "file_done": ("已完成", "已完成", "Completed", "完了", "완료", "Завершено", "Terminé"),
    "queue_counts": ("{total} 项任务 · {state} 1 · 等待 {waiting}", "{total} 項工作 · {state} 1 · 等待 {waiting}", "{total} tasks · 1 {state} · {waiting} waiting", "全 {total} 件 · {state} 1 件 · 待機 {waiting} 件", "전체 {total}개 · {state} 1개 · 대기 {waiting}개", "Задач: {total} · {state}: 1 · В очереди: {waiting}", "{total} tâches · 1 {state} · {waiting} en attente"),
    "open_folder": ("打开文件夹", "開啟資料夾", "Open folder", "フォルダーを開く", "폴더 열기", "Открыть папку", "Ouvrir le dossier"),
    "folder_open_failed": ("无法打开文件夹：{path}", "無法開啟資料夾：{path}", "Could not open folder: {path}", "フォルダーを開けません：{path}", "폴더를 열 수 없습니다: {path}", "Не удалось открыть папку: {path}", "Impossible d’ouvrir le dossier : {path}"),
    "background_mask_opacity": ("遮罩不透明度", "遮罩不透明度", "Overlay opacity", "オーバーレイの不透明度", "오버레이 불투명도", "Непрозрачность слоя", "Opacité du voile"),
    "cpu_model": ("CPU 型号", "CPU 型號", "CPU model", "CPU 型番", "CPU 모델", "Модель процессора", "Processeur"),
    "gpu_model": ("显卡型号", "顯示卡型號", "Graphics adapters", "GPU 型番", "그래픽 카드", "Видеокарты", "Cartes graphiques"),
    "detecting_hardware": ("正在检测…", "正在偵測…", "Detecting…", "検出中…", "감지 중…", "Определение…", "Détection…"),
    "metadata_retry": ("附加信息写入失败，正在用精简元数据重试。", "附加資訊寫入失敗，正在用精簡中繼資料重試。", "Metadata could not be written. Retrying with reduced metadata.", "付加情報を書き込めないため、メタデータを減らして再試行します。", "부가 정보를 기록할 수 없어 메타데이터를 줄여 다시 시도합니다.", "Не удалось записать метаданные. Повтор с сокращёнными метаданными.", "Échec de l’écriture des métadonnées. Nouvel essai avec moins de métadonnées."),
    "interface_font_size": ("界面字号", "介面字級", "Font size", "文字サイズ", "글자 크기", "Размер шрифта", "Taille du texte"),
    "search_fonts": ("搜索字体", "搜尋字型", "Search fonts", "フォントを検索", "글꼴 검색", "Поиск шрифта", "Rechercher une police"),
    "auto_size": ("自动", "自動", "Automatic", "自動", "자동", "Авто", "Automatique"),
    "background_image_opacity": ("图片不透明度", "圖片不透明度", "Image opacity", "画像の不透明度", "이미지 불투명도", "Непрозрачность изображения", "Opacité de l’image"),
    "background_blur": ("毛玻璃模糊度", "毛玻璃模糊度", "Frosted glass blur", "すりガラスのぼかし", "유리 흐림 효과", "Размытие матового стекла", "Flou du verre dépoli"),
    "appearance_settings": ("外观", "外觀", "Appearance", "外観", "모양", "Оформление", "Apparence"),
    "interface_font": ("界面字体", "介面字型", "Interface font", "画面のフォント", "화면 글꼴", "Шрифт интерфейса", "Police de l’interface"),
    "default_font": ("系统默认字体", "系統預設字型", "System default font", "システム既定のフォント", "시스템 기본 글꼴", "Системный шрифт", "Police du système"),
    "background_image": ("背景图片", "背景圖片", "Background image", "背景画像", "배경 이미지", "Фоновое изображение", "Image de fond"),
    "select_image": ("选择图片", "選擇圖片", "Choose image", "画像を選択", "이미지 선택", "Выбрать изображение", "Choisir une image"),
    "default_background": ("恢复默认背景", "還原預設背景", "Restore default", "既定の背景に戻す", "기본 배경 복원", "Вернуть стандартный фон", "Rétablir le fond par défaut"),
    "background_read_error": ("无法读取这张图片，请选择其他图片。", "無法讀取這張圖片，請選擇其他圖片。", "This image could not be read. Choose another image.", "画像を読み込めません。別の画像を選択してください。", "이미지를 읽을 수 없습니다. 다른 이미지를 선택하세요.", "Не удалось прочитать изображение. Выберите другое.", "Impossible de lire cette image. Choisissez-en une autre."),
    "log_m3u8_merge": ("检测到 M3U8 播放列表，将按顺序合成为单个输出文件。", "偵測到 M3U8 播放清單，將依序合成單一輸出檔案。", "M3U8 playlist detected. Its segments will be combined into one output file.", "M3U8 プレイリストを検出しました。セグメントを順番にまとめて 1 つのファイルに出力します。", "M3U8 재생 목록을 찾았습니다. 세그먼트를 순서대로 하나의 파일로 합칩니다.", "Обнаружен список M3U8. Сегменты будут объединены по порядку в один файл.", "Liste M3U8 détectée. Ses segments seront réunis dans un seul fichier de sortie."),
    "pdf_export_title": ("PDF 文本导出", "PDF 文字匯出", "PDF text export", "PDF テキスト書き出し", "PDF 텍스트 내보내기", "Экспорт текста PDF", "Exportation du texte PDF"),
    "close_dialog": ("关闭", "關閉", "Close", "閉じる", "닫기", "Закрыть", "Fermer"),
    "installed_version": ("当前版本 {version}", "目前版本 {version}", "Installed version {version}", "現在のバージョン {version}", "현재 버전 {version}", "Установлена версия {version}", "Version installée : {version}"),
    "engine_percent": ("正在下载 · {percent}%", "正在下載 · {percent}%", "Downloading · {percent}%", "ダウンロード中 · {percent}%", "다운로드 중 · {percent}%", "Загрузка · {percent}%", "Téléchargement · {percent} %"),
    "engine_verify": ("正在校验安装包…", "正在驗證安裝包…", "Verifying the package…", "パッケージを検証中…", "패키지 검증 중…", "Проверка пакета…", "Vérification du paquet…"),
    "engine_install": ("正在安装并试运行新引擎…", "正在安裝並試用新引擎…", "Installing and testing the new engine…", "新しいエンジンをインストールして動作確認中…", "새 엔진 설치 및 테스트 중…", "Установка и проверка нового движка…", "Installation et essai du nouveau moteur…"),
    "engine_kept": ("更新失败，继续使用原版本。{reason}", "更新失敗，繼續使用原版本。{reason}", "Update failed. The previous version remains active. {reason}", "更新に失敗しました。以前のバージョンを使用します。{reason}", "업데이트에 실패했습니다. 이전 버전을 계속 사용합니다. {reason}", "Не удалось обновить. Прежняя версия остаётся активной. {reason}", "Échec de la mise à jour. La version précédente reste active. {reason}"),
    "update_on_startup": ("下次启动时自动检查更新", "下次啟動時自動檢查更新", "Check for updates at startup", "次回起動時に更新を自動で確認", "시작할 때 자동으로 업데이트 확인", "Проверять обновления при запуске", "Rechercher les mises à jour au démarrage"),
    "update_later": ("稍后", "稍後", "Later", "あとで", "나중에", "Позже", "Plus tard"),
    "update_now": ("马上更新", "馬上更新", "Update now", "今すぐ更新", "지금 업데이트", "Обновить сейчас", "Mettre à jour"),
    "update_versions": ("当前版本 {local} → 最新版本 {version}", "目前版本 {local} → 最新版本 {version}", "Current {local} → Latest {version}", "現在 {local} → 最新 {version}", "현재 {local} → 최신 {version}", "Текущая {local} → Новая {version}", "Actuelle {local} → Dernière {version}"),
    "update_unknown": ("未知", "未知", "Unknown", "不明", "알 수 없음", "Неизвестно", "Inconnue"),
    "visit_project_website": ("前往 {name} 官网", "前往 {name} 官網", "Visit the official {name} website", "{name} の公式サイトを開く", "{name} 공식 웹사이트로 이동", "Перейти на официальный сайт {name}", "Ouvrir le site officiel de {name}"),
    "release_notes": ("更新公告", "更新公告", "Release notes", "更新内容", "업데이트 공지", "Примечания к выпуску", "Notes de version"),
    "release_notes_loading": ("正在加载更新公告…", "正在載入更新公告…", "Loading release notes…", "更新内容を読み込み中…", "업데이트 공지를 불러오는 중…", "Загрузка описания выпуска…", "Chargement des notes de version…"),
    "release_notes_unavailable": ("暂时无法获取更新公告，本机还没有缓存。", "暫時無法取得更新公告，本機尚無快取。", "Release notes are unavailable. No copy is cached yet.", "更新内容を取得できません。保存済みの公告はありません。", "업데이트 공지를 불러올 수 없으며 저장된 공지가 없습니다.", "Не удалось загрузить описание выпуска. Сохранённой копии пока нет.", "Les notes de version sont indisponibles. Aucune copie en cache."),
    "release_notes_empty": ("此版本未附更新说明。", "此版本未附更新說明。", "No notes for this release.", "このバージョンには更新内容の記載がありません。", "이 버전에는 공지가 없습니다.", "Описание выпуска отсутствует.", "Aucune note pour cette version."),
    "app_package_unavailable": ("此版本暂无适合本机的更新包。", "此版本暫無適合本機的更新套件。", "No update package is available for this device.", "この端末向けの更新パッケージはありません。", "이 기기에 맞는 업데이트 패키지가 없습니다.", "Для этого устройства пакет обновления недоступен.", "Aucun paquet de mise à jour pour cet appareil."),
    "component_build": ("本机构建 {build} · 官方稳定版 {version}", "本機組建 {build} · 官方穩定版 {version}", "Build {build} · Stable {version}", "ビルド {build} · 安定版 {version}", "빌드 {build} · 안정 버전 {version}", "Сборка {build} · Стабильная {version}", "Build {build} · Version stable {version}"),
    "app_updates": ("软件更新", "軟體更新", "Software update", "ソフトウェア更新", "소프트웨어 업데이트", "Обновление приложения", "Mise à jour du logiciel"),
    "engine_updates": ("转换引擎更新", "轉換引擎更新", "Engine updates", "エンジン更新", "엔진 업데이트", "Обновления движков", "Mises à jour des moteurs"),
    "checking_version": ("正在检查…", "正在檢查…", "Checking…", "確認中…", "확인 중…", "Проверка…", "Vérification…"),
    "app_current": ("软件已是最新版本", "軟體已是最新版本", "App is up to date", "アプリは最新版です", "앱이 최신 버전입니다", "Приложение обновлено", "Logiciel à jour"),
    "update_available_short": ("可更新", "可更新", "Update available", "更新あり", "업데이트 가능", "Есть обновление", "Mise à jour disponible"),
    "local_unknown": ("本机版本未知 · 最新 {version}", "本機版本不明 · 最新 {version}", "Local version unknown · Latest {version}", "ローカル版不明 · 最新 {version}", "로컬 버전 미확인 · 최신 {version}", "Локальная версия неизвестна · Новая {version}", "Version locale inconnue · Dernière {version}"),
    "component_new": ("本机 {local} → 可更新至 {version}", "本機 {local} → 可更新至 {version}", "Installed {local} → Available {version}", "現在 {local} → 最新 {version}", "현재 {local} → 최신 {version}", "Установлена {local} → Доступна {version}", "Installée {local} → Disponible {version}"),
    "component_current": ("本机 {local} · 已是最新", "本機 {local} · 已是最新", "Installed {local} · Up to date", "現在 {local} · 最新です", "현재 {local} · 최신 버전", "Установлена {local} · Актуальна", "Installée {local} · À jour"),
    "bundled_engine_version": ("随附版本 {version}", "隨附版本 {version}", "Bundled {version}", "同梱版 {version}", "포함된 버전 {version}", "В комплекте {version}", "Version incluse {version}"),
    "component_cached": ("{version} 已下载到缓存", "{version} 已下載至快取", "{version} cached", "{version} をキャッシュ済み", "{version} 캐시에 저장됨", "{version} в кэше", "{version} en cache"),
    "component_download_question": ("下载 {name} {version}（{size:.0f} MiB）到更新缓存？", "下載 {name} {version}（{size:.0f} MiB）到更新快取？", "Download {name} {version} ({size:.0f} MiB) to the update cache?", "{name} {version}（{size:.0f} MiB）を更新キャッシュに保存しますか？", "{name} {version}({size:.0f} MiB)을 업데이트 캐시에 저장할까요?", "Загрузить {name} {version} ({size:.0f} МиБ) в кэш обновлений?", "Télécharger {name} {version} ({size:.0f} Mio) dans le cache ?"),
    "theme_auto": ("外观：跟随系统", "外觀：跟隨系統", "Appearance: System", "外観：システム", "화면: 시스템 설정", "Тема: системная", "Apparence : système"),
    "theme_light": ("外观：浅色", "外觀：淺色", "Appearance: Light", "外観：ライト", "화면: 라이트", "Тема: светлая", "Apparence : claire"),
    "theme_dark": ("外观：深色", "外觀：深色", "Appearance: Dark", "外観：ダーク", "화면: 다크", "Тема: тёмная", "Apparence : sombre"),
    "downloading_model": ("正在下载模型…", "正在下載模型…", "Downloading model…", "モデルをダウンロード中…", "모델 다운로드 중…", "Загрузка модели…", "Téléchargement du modèle…"),
    "model_env_notice": ("PDF 识别运行环境已内置，这里只下载模型文件。", "PDF 辨識執行環境已內建，這裡只下載模型檔案。", "The PDF recognition runtime is included. Only model files will be downloaded.", "PDF 認識の実行環境は内蔵されています。ここではモデルファイルのみをダウンロードします。", "PDF 인식 실행 환경이 포함되어 있습니다. 여기서는 모델 파일만 다운로드합니다.", "Среда распознавания PDF уже включена. Будут загружены только файлы модели.", "L’environnement de reconnaissance PDF est inclus. Seuls les fichiers du modèle seront téléchargés."),
    'preparing_runtime': ('正在安装模型运行环境…', '正在安裝模型執行環境…', 'Installing model dependencies…', '依存関係をインストール中…', '실행 환경 설치 중…', 'Установка компонентов модели…', 'Installation des dépendances du modèle…'),
    "group_audio": ("音频", "音訊", "Audio", "音声", "오디오", "Аудио", "Audio"),
    "group_video": ("视频", "影片", "Video", "動画", "비디오", "Видео", "Vidéo"),
    "group_images": ("图片", "圖片", "Images", "画像", "이미지", "Изображения", "Images"),
    "group_documents": ("文档", "文件", "Documents", "文書", "문서", "Документы", "Documents"),
    "audio_convert": ("音频转换", "音訊轉換", "Convert audio", "音声変換", "오디오 변환", "Конвертация аудио", "Convertir un son"),
    "video_convert": ("视频转换", "影片轉換", "Convert video", "動画変換", "비디오 변환", "Конвертация видео", "Convertir une vidéo"),
    "page_m3u8_merge": ("M3U8 合成", "M3U8 合成", "Merge M3U8", "M3U8 を結合", "M3U8 병합", "Объединить M3U8", "Fusionner M3U8"),
    "m3u8_url_placeholder": ("粘贴网络 M3U8 链接", "貼上網路 M3U8 連結", "Paste an online M3U8 link", "オンライン M3U8 リンクを貼り付け", "온라인 M3U8 링크 붙여넣기", "Вставьте ссылку M3U8", "Collez un lien M3U8"),
    "add_m3u8_link": ("添加链接", "新增連結", "Add link", "リンクを追加", "링크 추가", "Добавить ссылку", "Ajouter le lien"),
    "invalid_m3u8_url": ("请输入有效的 HTTP 或 HTTPS 地址。", "請輸入有效的 HTTP 或 HTTPS 位址。", "Enter a valid HTTP or HTTPS address.", "有効な HTTP または HTTPS アドレスを入力してください。", "올바른 HTTP 또는 HTTPS 주소를 입력하세요.", "Введите действительный адрес HTTP или HTTPS.", "Saisissez une adresse HTTP ou HTTPS valide."),
    "audio_compress": ("音频压缩", "音訊壓縮", "Compress audio", "音声圧縮", "오디오 압축", "Сжатие аудио", "Compresser un son"),
    "video_compress": ("视频压缩", "影片壓縮", "Compress video", "動画圧縮", "비디오 압축", "Сжатие видео", "Compresser une vidéo"),
    "image_compress": ("图片压缩", "圖片壓縮", "Compress images", "画像圧縮", "이미지 압축", "Сжатие изображений", "Compresser une image"),
    "intro_audio_convert": ("导出 MP3、WAV、FLAC 或 M4A 音频。", "匯出 MP3、WAV、FLAC 或 M4A 音訊。", "Export MP3, WAV, FLAC or M4A audio.", "MP3、WAV、FLAC、M4A に変換します。", "MP3, WAV, FLAC, M4A로 변환합니다.", "Экспорт в MP3, WAV, FLAC или M4A.", "Exporter en MP3, WAV, FLAC ou M4A."),
    "intro_video_convert": ("导出 MP4 或 MKV 视频。", "匯出 MP4 或 MKV 影片。", "Export video as MP4 or MKV.", "MP4 または MKV に変換します。", "MP4 또는 MKV로 변환합니다.", "Экспорт видео в MP4 или MKV.", "Exporter la vidéo en MP4 ou MKV."),
    "intro_audio_compress": ("按音频格式匹配编码器和压缩参数；无损音频输出 FLAC，其他格式按码率压缩。", "依音訊格式選擇編碼器與壓縮參數；無損音訊輸出 FLAC，其他格式依位元率壓縮。", "Chooses a codec and settings for each audio format. Lossless sources become FLAC; other formats use bitrate-based compression.", "音声形式に合わせてエンコーダーと設定を選びます。可逆音声は FLAC、その他はビットレートで圧縮します。", "오디오 형식에 맞는 인코더와 설정을 사용합니다. 무손실 소스는 FLAC으로, 나머지는 비트레이트로 압축합니다.", "Кодек и параметры подбираются по формату. Форматы без потерь сохраняются в FLAC, остальные сжимаются по битрейту.", "Le codec et les réglages sont adaptés au format. Les sources sans perte deviennent du FLAC, les autres sont compressées selon le débit."),
    "intro_video_compress": ("识别视频格式并匹配编码器：WebM 使用 VP9，OGV 使用 Theora，其他格式使用 H.264。", "辨識影片格式並選擇編碼器：WebM 使用 VP9、OGV 使用 Theora，其他格式使用 H.264。", "Selects an encoder by source format: VP9 for WebM, Theora for OGV, and H.264 for other formats.", "入力形式に合わせてエンコーダーを選びます。WebM は VP9、OGV は Theora、その他は H.264 です。", "입력 형식에 따라 인코더를 선택합니다. WebM은 VP9, OGV는 Theora, 그 외는 H.264를 사용합니다.", "Кодек выбирается по формату: VP9 для WebM, Theora для OGV и H.264 для остальных.", "Le codec dépend du format : VP9 pour WebM, Theora pour OGV et H.264 pour les autres."),
    "intro_image_compress": ("根据图片格式选择压缩方法：JPEG 保持 JPG，PNG 使用无损压缩，其他格式输出 WebP。", "依圖片格式選擇壓縮方式：JPEG 保留 JPG、PNG 使用無損壓縮，其他格式輸出 WebP。", "Chooses compression by image format: JPEG stays JPG, PNG uses lossless compression, and other formats export as WebP.", "形式に合わせて圧縮します。JPEG は JPG のまま、PNG は可逆圧縮し、その他は WebP に出力します。", "이미지 형식에 맞춰 압축합니다. JPEG는 JPG로 유지하고 PNG는 무손실 압축하며 그 외는 WebP로 내보냅니다.", "Метод зависит от формата: JPEG остаётся JPG, PNG сжимается без потерь, остальные форматы сохраняются как WebP.", "La compression dépend du format : JPEG reste en JPG, PNG est compressé sans perte, les autres formats deviennent WebP."),
    "static_images_only": ("此操作不支持动画或多页图片。请转换为 GIF、WebP 或 TIFF 以保留全部帧。", "此操作不支援動畫或多頁圖片。請轉換為 GIF、WebP 或 TIFF 以保留全部影格。", "This operation cannot preserve animation or multiple pages. Convert to GIF, WebP or TIFF instead.", "この操作では全フレームを保持できません。GIF、WebP、TIFF を選択してください。", "이 작업은 모든 프레임을 보존할 수 없습니다. GIF, WebP 또는 TIFF로 변환하세요.", "Операция не сохраняет все кадры. Выберите преобразование в GIF, WebP или TIFF.", "Cette opération ne conserve pas toutes les images. Choisissez GIF, WebP ou TIFF."),
    "skipped_type": ("{page}：已跳过 {count} 个类型不匹配的文件。", "{page}：已略過 {count} 個類型不符的檔案。", "{page}: skipped {count} files of other types.", "{page}：対象外のファイル {count} 件をスキップしました。", "{page}: 다른 형식의 파일 {count}개를 건너뛰었습니다.", "{page}: пропущено файлов другого типа: {count}.", "{page} : {count} fichier(s) d’un autre type ignoré(s)."),
    "app_name": ("格式转换通", "格式轉換通", "Format Studio", "フォーマット工房", "포맷 스튜디오", "Формат", "Atelier formats"),
    "group_convert": ("转换", "轉換", "Convert", "変換", "변환", "Конвертация", "Conversion"),
    "group_media": ("音视频", "影音", "Audio & video", "音声・動画", "오디오 및 비디오", "Медиа", "Audio et vidéo"),
    "group_create": ("创作与文档", "創作與文件", "Images & docs", "画像・文書", "이미지 및 문서", "Медиа и файлы", "Images et documents"),
    "group_settings": ("偏好设置", "偏好設定", "Preferences", "環境設定", "환경 설정", "Настройки", "Préférences"),
    "page_format": ("格式转换", "格式轉換", "Format conversion", "形式変換", "형식 변환", "Форматы", "Formats"),
    "page_compress": ("文件压缩", "檔案壓縮", "File compression", "ファイル圧縮", "파일 압축", "Сжатие файлов", "Compresser"),
    "page_merge": ("音视频合并", "影音合併", "Merge A/V", "音声・動画を結合", "오디오/비디오 병합", "Слияние A/V", "Fusion A/V"),
    "page_split": ("分离音视频", "分離影音", "Separate audio/video", "音声・動画を分離", "오디오/비디오 분리", "Разделить A/V", "Séparer A/V"),
    "page_image": ("图片转换", "圖片轉換", "Images", "画像", "이미지", "Изображения", "Images"),
    "page_document": ("文档转换", "文件轉換", "Documents", "文書", "문서", "Документы", "Documents"),
    "page_pdf": ("PDF 转换", "PDF 轉換", "PDF", "PDF", "PDF", "PDF", "PDF"),
    "page_settings": ("设置", "設定", "Settings", "設定", "설정", "Настройки", "Réglages"),
    "intro_format": ("把文件转换为需要的格式。\n视频与音频格式转换，保留原文件不变。", "將檔案轉換為需要的格式。\n轉換影音格式時會保留原始檔案。", "Convert files to the format you need.\nYour original audio and video files stay untouched.", "必要な形式に変換します。\n元の音声・動画ファイルはそのまま残ります。", "필요한 형식으로 변환합니다.\n원본 오디오 및 비디오 파일은 그대로 유지됩니다.", "Преобразуйте файлы в нужный формат.\nИсходные аудио- и видеофайлы сохраняются.", "Convertissez vos fichiers au format souhaité.\nLes fichiers audio et vidéo d’origine sont conservés."),
    "intro_compress": ("减小文件体积，方便保存与分享。\n可选择适合的压缩力度。", "縮小檔案，方便儲存與分享。\n可選擇合適的壓縮程度。", "Make files smaller for easier storage and sharing.\nChoose the compression level that suits you.", "ファイルを小さくして保存や共有を簡単にします。\n圧縮レベルを選択できます。", "파일 크기를 줄여 저장과 공유를 간편하게 합니다.\n압축 강도를 선택할 수 있습니다.", "Уменьшайте размер файлов для хранения и отправки.\nВыберите степень сжатия.", "Réduisez la taille des fichiers pour les stocker et les partager.\nChoisissez le niveau de compression."),
    "intro_merge": ("为视频添加一条音轨。\n合成结果会另存为新文件。", "為影片新增音軌。\n合併結果會另存為新檔案。", "Add an audio track to a video.\nThe merged result is saved as a new file.", "動画に音声トラックを追加します。\n結合結果は新しいファイルとして保存されます。", "비디오에 오디오 트랙을 추가합니다.\n병합 결과는 새 파일로 저장됩니다.", "Добавьте аудиодорожку к видео.\nРезультат сохранится в отдельный файл.", "Ajoutez une piste audio à une vidéo.\nLe résultat est enregistré dans un nouveau fichier."),
    "intro_split": ("提取视频中的音轨或画面。\n源文件不会被修改。", "從影片擷取音軌或畫面。\n來源檔案不會變更。", "Extract the audio or video stream.\nYour source file is not modified.", "動画から音声または映像を抽出します。\n元ファイルは変更されません。", "비디오에서 오디오 또는 영상을 추출합니다.\n원본 파일은 변경되지 않습니다.", "Извлеките аудио или видео.\nИсходный файл не изменится.", "Extrayez l’audio ou la vidéo.\nLe fichier source reste intact."),
    "intro_image": ("批量转换常见图片格式。\n转换后的图片另存为新文件。", "批次轉換常見圖片格式。\n轉換後的圖片會另存為新檔案。", "Convert common image formats in batches.\nConverted images are saved as new files.", "一般的な画像形式をまとめて変換します。\n変換後の画像は新規ファイルとして保存されます。", "일반적인 이미지 형식을 일괄 변환합니다.\n변환된 이미지는 새 파일로 저장됩니다.", "Пакетно преобразуйте популярные форматы изображений.\nРезультат сохраняется в новый файл.", "Convertissez plusieurs formats d’image courants.\nLes images converties sont enregistrées dans de nouveaux fichiers."),
    "intro_document": ("在常用文档格式之间转换。\n添加文件后会按文档类别筛选可用目标格式。\n使用 LibreOffice 引擎处理。", "在常用文件格式之間轉換。\n新增檔案後會依文件類別篩選可用的目標格式。\n由 LibreOffice 引擎處理。", "Convert common document formats.\nAvailable outputs are filtered by document type.\nPowered by LibreOffice.", "一般的な文書形式を変換します。\n追加した文書の種類に合わせて出力形式を絞り込みます。\nLibreOffice を使用します。", "일반적인 문서 형식 간에 변환합니다.\n추가한 문서 종류에 따라 출력 형식을 필터링합니다.\nLibreOffice를 사용합니다.", "Преобразование популярных форматов документов.\nДоступные форматы вывода зависят от типа документа.\nИспользуется LibreOffice.", "Convertissez les formats de documents courants.\nLes sorties disponibles dépendent du type de document.\nPropulsé par LibreOffice."),
    "intro_pdf": ("提取 PDF 文字、表格或页面图片。\n扫描页识别模型可在设置中按需下载。", "擷取 PDF 文字、表格或頁面圖片。\n可在設定中按需下載掃描頁辨識模型。", "Extract PDF text, tables, or page images.\nDownload the scan recognition model in Settings when needed.", "PDFからテキスト、表、ページ画像を抽出します。\nスキャン認識モデルは設定から必要なときにダウンロードできます。", "PDF에서 텍스트, 표 또는 페이지 이미지를 추출합니다.\n스캔 인식 모델은 설정에서 필요할 때 다운로드할 수 있습니다.", "Извлекайте текст, таблицы или изображения страниц PDF.\nМодель распознавания сканов можно скачать в настройках.", "Extrayez le texte, les tableaux ou les images des pages PDF.\nLe modèle de reconnaissance se télécharge dans les réglages."),
    "import_title": ("导入文件", "匯入檔案", "Import files", "ファイルを追加", "파일 가져오기", "Добавить файлы", "Importer des fichiers"),
    "file_list": ("文件列表", "檔案清單", "File list", "ファイル一覧", "파일 목록", "Список файлов", "Liste des fichiers"),
    "file_count_short": ("{count} 个文件", "{count} 個檔案", "{count} files", "{count} 個のファイル", "파일 {count}개", "Файлов: {count}", "{count} fichier(s)"),
    "import_hint": ("拖入文件，或从电脑中选择", "拖放檔案，或從電腦中選取", "Drop files here or choose from your computer", "ファイルをドロップするか、コンピューターから選択", "파일을 끌어 놓거나 컴퓨터에서 선택하세요", "Перетащите файлы или выберите на компьютере", "Déposez des fichiers ou choisissez-les sur votre ordinateur"),
    "select_file": ("选择文件", "選擇檔案", "Choose files", "ファイルを選択", "파일 선택", "Выбрать файлы", "Choisir des fichiers"),
    "add_files": ("添加文件", "新增檔案", "Add files", "ファイルを追加", "파일 추가", "Добавить файлы", "Ajouter des fichiers"),
    "add_folder": ("添加文件夹", "新增資料夾", "Add folder", "フォルダーを追加", "폴더 추가", "Добавить папку", "Ajouter un dossier"),
    "empty_files_title": ("拖放文件到这里", "將檔案拖放到這裡", "Drop files here", "ファイルをここにドロップ", "여기에 파일을 끌어 놓으세요", "Перетащите файлы сюда", "Déposez les fichiers ici"),
    "drop_files": ("也可以使用右上角的按钮添加文件", "也可以使用右上角的按鈕新增檔案", "Or use the buttons in the top right", "右上のボタンからも追加できます", "오른쪽 위 버튼으로도 추가할 수 있습니다", "Или добавьте файлы кнопками вверху справа", "Ou utilisez les boutons en haut à droite"),
    "drop_ready": ("松开鼠标即可添加文件", "放開滑鼠即可新增檔案", "Release to add files", "マウスを離すとファイルを追加します", "마우스를 놓으면 파일이 추가됩니다", "Отпустите, чтобы добавить файлы", "Relâchez pour ajouter les fichiers"),
    "drop_ready_hint": ("文件将按格式加入对应页面", "檔案將依格式加入對應頁面", "Files are sorted by format into their pages", "形式に応じて各ページに追加します", "파일 형식에 따라 해당 페이지에 추가합니다", "Файлы будут распределены по формату", "Les fichiers seront répartis par format"),
    "drop_summary": ("已添加 {count} 个文件，跳过 {skipped} 个不支持的文件", "已新增 {count} 個檔案，略過 {skipped} 個不支援的檔案", "Added {count} files, skipped {skipped} unsupported files", "{count} 件追加、未対応の {skipped} 件をスキップ", "{count}개 추가, 지원되지 않는 파일 {skipped}개 건너뜀", "Добавлено: {count}, пропущено неподдерживаемых: {skipped}", "{count} fichiers ajoutés, {skipped} fichiers non pris en charge ignorés"),
    "drop_added": ("已添加 {count} 个文件", "已新增 {count} 個檔案", "Added {count} files", "{count} 個のファイルを追加しました", "파일 {count}개를 추가했습니다", "Добавлено файлов: {count}", "{count} fichier(s) ajouté(s)"),
    "remove_selected": ("移除所选", "移除所選", "Remove selected", "選択項目を削除", "선택 항목 제거", "Удалить выбранное", "Supprimer la sélection"),
    "clear": ("清空", "清除", "Clear", "クリア", "비우기", "Очистить", "Effacer"),
    "no_files": ("尚未添加文件", "尚未新增檔案", "No files added", "ファイルはありません", "추가된 파일 없음", "Файлы не добавлены", "Aucun fichier ajouté"),
    "file_count": ("已添加 {count} 个文件", "已新增 {count} 個檔案", "{count} file(s) added", "{count} 個のファイルを追加", "파일 {count}개 추가됨", "Добавлено файлов: {count}", "{count} fichier(s) ajouté(s)"),
    "output_settings": ("输出设置", "輸出設定", "Output settings", "出力設定", "출력 설정", "Параметры вывода", "Paramètres de sortie"),
    "audio_track": ("音轨", "音軌", "Audio track", "音声トラック", "오디오 트랙", "Аудиодорожка", "Piste audio"),
    "track_placeholder": ("选择要使用的音轨", "選擇要使用的音軌", "Choose an audio track", "使用する音声を選択", "사용할 오디오 트랙 선택", "Выберите аудиодорожку", "Choisissez une piste audio"),
    "choose_audio": ("选择音频文件", "選擇音訊檔案", "Choose audio file", "音声ファイルを選択", "오디오 파일 선택", "Выбрать аудиофайл", "Choisir un fichier audio"),
    "output_format": ("目标格式", "目標格式", "Output format", "出力形式", "출력 형식", "Формат вывода", "Format de sortie"),
    "format_xlsx": ("xlsx", "xlsx", "xlsx", "xlsx", "xlsx", "xlsx", "xlsx"),
    "compression_level": ("压缩力度", "壓縮程度", "Compression level", "圧縮レベル", "압축 강도", "Степень сжатия", "Niveau de compression"),
    "compression_method": ("压缩方案", "壓縮方案", "Compression profile", "圧縮方法", "압축 방식", "Профиль сжатия", "Profil de compression"),
    "compression_balanced": ("均衡", "均衡", "Balanced", "バランス", "균형", "Сбалансированный", "Équilibré"),
    "compression_quality": ("高质量", "高品質", "Higher quality", "高品質", "고품질", "Высокое качество", "Qualité élevée"),
    "compression_small": ("小体积", "小體積", "Smaller file", "小さいサイズ", "작은 파일", "Меньший размер", "Fichier plus petit"),
    "compression_fast": ("快速无损", "快速無損", "Fast lossless", "高速・可逆", "빠른 무손실", "Быстрое сжатие без потерь", "Sans perte rapide"),
    "compression_lossless_balanced": ("均衡无损", "均衡無損", "Balanced lossless", "バランス・可逆", "균형 무손실", "Сбалансированное сжатие без потерь", "Sans perte équilibré"),
    "compression_lossless_small": ("较小体积 · 无损", "較小體積 · 無損", "Smaller · lossless", "小さいサイズ・可逆", "작은 파일 · 무손실", "Меньше · без потерь", "Plus petit · sans perte"),
    "compression_channels": ("输出声道", "輸出聲道", "Output channels", "出力チャンネル", "출력 채널", "Каналы вывода", "Canaux de sortie"),
    "compression_original_channels": ("保持原声道", "保持原聲道", "Keep original", "元のまま", "원본 유지", "Как в оригинале", "Conserver l’original"),
    "compression_mono": ("单声道", "單聲道", "Mono", "モノラル", "모노", "Моно", "Mono"),
    "compression_max_dimensions": ("分辨率上限（宽 × 高）", "解析度上限（寬 × 高）", "Resolution limit (width × height)", "解像度上限（幅 × 高さ）", "해상도 한도 (너비 × 높이)", "Ограничение разрешения (ширина × высота)", "Limite de résolution (largeur × hauteur)"),
    "compression_height_hint": ("选择“保持原分辨率”，或输入宽 × 高；支持 1920x1080、1920*1080、1920 1080。输出会保持原比例。", "選擇「保持原解析度」，或輸入寬 × 高；支援 1920x1080、1920*1080、1920 1080。輸出會保持原比例。", "Keep the original resolution or enter width × height, such as 1920x1080, 1920*1080, or 1920 1080. Aspect ratio is preserved.", "元の解像度を維持するか、幅 × 高さを入力します（例：1920x1080、1920*1080、1920 1080）。縦横比は維持されます。", "원본 해상도를 유지하거나 너비 × 높이를 입력하세요(예: 1920x1080, 1920*1080, 1920 1080). 화면 비율은 유지됩니다.", "Сохраните исходное разрешение или введите ширину × высоту, например 1920x1080, 1920*1080 или 1920 1080. Пропорции сохраняются.", "Conservez la résolution d’origine ou saisissez largeur × hauteur, par exemple 1920x1080, 1920*1080 ou 1920 1080. Les proportions sont conservées."),
    "compression_resolution_placeholder": ("输入宽×高，例如 1920x1080", "輸入寬×高，例如 1920x1080", "Enter width × height, e.g. 1920x1080", "幅×高さを入力（例：1920x1080）", "너비×높이 입력(예: 1920x1080)", "Введите ширину × высоту, например 1920x1080", "Saisissez largeur × hauteur, ex. 1920x1080"),
    "compression_resolution_invalid": ("请输入有效的宽×高，例如 1920x1080、1920*1080 或 1920 1080。宽度范围为 144–7680，高度范围为 144–4320。", "請輸入有效的寬×高，例如 1920x1080、1920*1080 或 1920 1080。寬度範圍為 144–7680，高度範圍為 144–4320。", "Enter a valid width × height, such as 1920x1080, 1920*1080, or 1920 1080. Width: 144–7680; height: 144–4320.", "有効な幅×高さを入力してください（例：1920x1080、1920*1080、1920 1080）。幅：144～7680、高さ：144～4320。", "올바른 너비×높이를 입력하세요(예: 1920x1080, 1920*1080, 1920 1080). 너비: 144–7680, 높이: 144–4320.", "Введите ширину × высоту, например 1920x1080, 1920*1080 или 1920 1080. Ширина: 144–7680, высота: 144–4320.", "Saisissez une largeur × hauteur valide, par ex. 1920x1080, 1920*1080 ou 1920 1080. Largeur : 144–7680 ; hauteur : 144–4320."),
    "compression_height_placeholder": ("输入高度，或从列表选择", "輸入高度，或從清單選擇", "Enter a height or choose a preset", "高さを入力するか、候補から選択", "높이를 입력하거나 목록에서 선택", "Введите высоту или выберите вариант", "Saisissez une hauteur ou choisissez une option"),
    "compression_bitrate": ("目标码率（有损音频）", "目標位元率（有損音訊）", "Target bitrate (lossy audio)", "目標ビットレート（非可逆音声）", "목표 비트레이트(손실 오디오)", "Целевой битрейт (сжатие с потерями)", "Débit cible (audio avec perte)"),
    "compression_profile_bitrate": ("按压缩方案", "依壓縮方案", "Use profile", "圧縮方案に従う", "압축 설정 사용", "По профилю сжатия", "Selon le profil"),
    "compression_bitrate_hint": ("选择“按压缩方案”使用上方预设码率。自定义码率适用于有损格式；FLAC 等无损格式不受影响。", "選擇「依壓縮方案」使用上方預設位元率。自訂位元率適用於有損格式；FLAC 等無損格式不受影響。", "Choose Use profile for the preset bitrate. Custom bitrate applies to lossy formats; lossless formats such as FLAC are unaffected.", "「圧縮方案に従う」を選ぶと上の設定を使います。カスタムビットレートは非可逆形式に適用され、FLAC などには影響しません。", "압축 설정 사용을 선택하면 위의 기본 비트레이트를 사용합니다. 사용자 지정 값은 손실 형식에 적용되며 FLAC 등에는 영향을 주지 않습니다.", "Выберите профиль для стандартного битрейта. Пользовательский битрейт действует для форматов с потерями, но не для FLAC.", "Choisissez le profil pour utiliser le débit prédéfini. Le débit personnalisé s’applique aux formats avec perte, pas au FLAC."),
    "compression_bitrate_placeholder": ("输入码率，或从列表选择", "輸入位元率，或從清單選擇", "Enter a bitrate or choose a preset", "ビットレートを入力するか、候補から選択", "비트레이트를 입력하거나 목록에서 선택", "Введите битрейт или выберите вариант", "Saisissez un débit ou choisissez une option"),
    "compression_original_resolution": ("保持原分辨率", "保持原解析度", "Keep original", "元の解像度", "원본 유지", "Как в оригинале", "Conserver l’original"),
    "compression_dimensions": ("图片尺寸", "圖片尺寸", "Image dimensions", "画像サイズ", "이미지 크기", "Размер изображения", "Dimensions de l’image"),
    "compression_original_dimensions": ("保持原尺寸", "保持原尺寸", "Keep original", "元のサイズ", "원본 유지", "Как в оригинале", "Conserver l’original"),
    "compression_75_percent": ("缩至 75%", "縮至 75%", "Scale to 75%", "75% に縮小", "75%로 축소", "Уменьшить до 75%", "Réduire à 75 %"),
    "compression_50_percent": ("缩至 50%", "縮至 50%", "Scale to 50%", "50% に縮小", "50%로 축소", "Уменьшить до 50%", "Réduire à 50 %"),
    "compression_result_saved": ("压缩结果：原文件 {original} → 压缩后 {compressed}，节省 {amount}（{percent}%）", "壓縮結果：原檔案 {original} → 壓縮後 {compressed}，節省 {amount}（{percent}%）", "Compressed: {original} → {compressed}; saved {amount} ({percent}%)", "圧縮結果：元ファイル {original} → 圧縮後 {compressed}、{amount} 削減（{percent}%）", "압축 결과: 원본 {original} → 압축 후 {compressed}, {amount} 절약({percent}%)", "Результат: исходный файл {original} → после сжатия {compressed}; экономия {amount} ({percent}%)", "Résultat : {original} → {compressed} après compression ; {amount} économisés ({percent} %)"),
    "compression_result_larger": ("压缩结果：原文件 {original} → 压缩后 {compressed}，体积增加 {amount}（{percent}%）", "壓縮結果：原檔案 {original} → 壓縮後 {compressed}，體積增加 {amount}（{percent}%）", "Compressed: {original} → {compressed}; file grew by {amount} ({percent}%)", "圧縮結果：元ファイル {original} → 圧縮後 {compressed}、サイズが {amount} 増加（{percent}%）", "압축 결과: 원본 {original} → 압축 후 {compressed}, 크기 {amount} 증가({percent}%)", "Результат: исходный файл {original} → после сжатия {compressed}; размер увеличился на {amount} ({percent}%)", "Résultat : {original} → {compressed} après compression ; taille augmentée de {amount} ({percent} %)"),
    "split_audio": ("仅提取音频", "僅擷取音訊", "Audio only", "音声のみ", "오디오만", "Только аудио", "Audio uniquement"),
    "split_video": ("仅提取视频", "僅擷取影片", "Video only", "動画のみ", "비디오만", "Только видео", "Vidéo uniquement"),
    "split_both": ("提取音频和视频", "擷取音訊和影片", "Audio and video separately", "音声と動画", "오디오 및 비디오", "Аудио и видео отдельно", "Audio et vidéo séparés"),
    "extract_content": ("提取内容", "擷取內容", "Extract", "抽出内容", "추출 항목", "Извлечь", "Extraire"),
    "save_to": ("保存到", "儲存至", "Save to", "保存先", "저장 위치", "Сохранить в", "Enregistrer dans"),
    "choose_folder": ("选择文件夹", "選擇資料夾", "Choose folder", "フォルダーを選択", "폴더 선택", "Выбрать папку", "Choisir un dossier"),
    "start": ("开始处理", "開始處理", "Start processing", "処理を開始", "처리 시작", "Начать обработку", "Lancer le traitement"),
    "pause": ("暂停", "暫停", "Pause", "一時停止", "일시 정지", "Пауза", "Pause"),
    "resume": ("继续", "繼續", "Resume", "再開", "재개", "Продолжить", "Reprendre"),
    "log_title": ("日志", "日誌", "Log", "ログ", "로그", "Журнал", "Journal"),
    "log_clear": ("清空日志", "清空記錄", "Clear log", "ログを消去", "로그 지우기", "Очистить журнал", "Effacer le journal"),
    "log_placeholder": ("任务开始后，转换进度和过程信息会显示在这里。", "工作開始後，轉換進度與過程資訊會顯示在這裡。", "Conversion progress and activity will appear here.", "処理の進行状況とログがここに表示されます。", "변환 진행 상황과 로그가 여기에 표시됩니다.", "Здесь будут отображаться ход обработки и журнал.", "La progression et les événements apparaîtront ici."),
    "log_queued": ("已加入队列：{file}", "已加入佇列：{file}", "Queued: {file}", "キューに追加: {file}", "대기열에 추가됨: {file}", "Добавлено в очередь: {file}", "Ajouté à la file : {file}"),
    "log_started": ("开始处理：{file}", "開始處理：{file}", "Started: {file}", "処理開始: {file}", "처리 시작: {file}", "Начата обработка: {file}", "Traitement démarré : {file}"),
    "log_paused": ("已暂停当前任务。", "已暫停目前工作。", "Current task paused.", "現在のタスクを一時停止しました。", "현재 작업을 일시 정지했습니다.", "Текущая задача приостановлена.", "Tâche en pause."),
    "log_resumed": ("继续处理当前任务。", "繼續處理目前工作。", "Current task resumed.", "現在のタスクを再開しました。", "현재 작업을 다시 시작했습니다.", "Обработка продолжена.", "Traitement repris."),
    "pause_failed": ("无法暂停任务：{reason}", "無法暫停工作：{reason}", "Could not pause task: {reason}", "タスクを一時停止できません: {reason}", "작업을 일시 정지할 수 없습니다: {reason}", "Не удалось приостановить задачу: {reason}", "Impossible de mettre en pause : {reason}"),
    "log_pdf_pages": ("PDF 页面", "PDF 頁面", "PDF pages", "PDF ページ", "PDF 페이지", "Страницы PDF", "Pages PDF"),
    "log_ffmpeg_progress": ("FFmpeg：已处理至 {time} · 速度 {speed}", "FFmpeg：已處理至 {time} · 速度 {speed}", "FFmpeg: processed {time} · speed {speed}", "FFmpeg: {time} まで処理 · 速度 {speed}", "FFmpeg: {time} 처리됨 · 속도 {speed}", "FFmpeg: обработано {time} · скорость {speed}", "FFmpeg : {time} traité · vitesse {speed}"),
    "log_worker_progress": ("{stage}：{current}/{total}（{percent}%）", "{stage}：{current}/{total}（{percent}%）", "{stage}: {current}/{total} ({percent}%)", "{stage}: {current}/{total}（{percent}%）", "{stage}: {current}/{total}（{percent}%）", "{stage}: {current}/{total} ({percent}%)", "{stage} : {current}/{total} ({percent} %)"),
    "dialog_select_files": ("选择文件", "選擇檔案", "Select files", "ファイルを選択", "파일 선택", "Выбор файлов", "Sélectionner des fichiers"),
    "user_folder": ("用户文件夹", "使用者資料夾", "User folder", "ユーザーフォルダー", "사용자 폴더", "Папка пользователя", "Dossier utilisateur"),
    "desktop": ("桌面", "桌面", "Desktop", "デスクトップ", "바탕 화면", "Рабочий стол", "Bureau"),
    "documents": ("文档", "文件", "Documents", "書類", "문서", "Документы", "Documents"),
    "downloads": ("下载", "下載", "Downloads", "ダウンロード", "다운로드", "Загрузки", "Téléchargements"),
    "pictures": ("图片", "圖片", "Pictures", "ピクチャ", "사진", "Изображения", "Images"),
    "default_output_location": ("格式转换通缓存", "格式轉換通快取", "Format Studio cache", "Format Studio キャッシュ", "Format Studio 캐시", "Кэш Format Studio", "Cache Format Studio"),
    "dialog_location": ("位置", "位置", "Location", "場所", "위치", "Расположение", "Emplacement"),
    "dialog_filename": ("文件名", "檔案名稱", "File name", "ファイル名", "파일 이름", "Имя файла", "Nom du fichier"),
    "dialog_directory": ("文件夹", "資料夾", "Folder", "フォルダー", "폴더", "Папка", "Dossier"),
    "dialog_file_type": ("文件类型", "檔案類型", "File type", "ファイルの種類", "파일 형식", "Тип файла", "Type de fichier"),
    "dialog_folder_type": ("文件夹类型", "資料夾類型", "Folder type", "フォルダーの種類", "폴더 형식", "Тип папки", "Type de dossier"),
    "dialog_choose": ("选择", "選擇", "Choose", "選択", "선택", "Выбрать", "Choisir"),
    "all_files_filter": ("所有文件 (*)", "所有檔案 (*)", "All files (*)", "すべてのファイル (*)", "모든 파일 (*)", "Все файлы (*)", "Tous les fichiers (*)"),
    "folders_filter": ("文件夹", "資料夾", "Folders", "フォルダー", "폴더", "Папки", "Dossiers"),
    "dialog_select_audio": ("选择音轨", "選擇音軌", "Select audio track", "音声トラックを選択", "오디오 트랙 선택", "Выбор аудиодорожки", "Sélectionner une piste audio"),
    "need_audio_title": ("还需要一条音轨", "還需要一條音軌", "Audio track required", "音声トラックが必要です", "오디오 트랙이 필요합니다", "Нужна аудиодорожка", "Piste audio requise"),
    "need_audio_message": ("请选择要用于合并的音频文件。", "請選擇要用於合併的音訊檔案。", "Choose the audio file to merge.", "結合する音声ファイルを選択してください。", "병합할 오디오 파일을 선택하세요.", "Выберите аудиофайл для объединения.", "Choisissez le fichier audio à fusionner."),
    "task_title": ("任务", "工作", "Tasks", "タスク", "작업", "Задачи", "Tâches"),
    "queue_empty": ("空闲", "閒置", "Idle", "待機中", "대기 중", "Ожидание", "En attente"),
    "queue_processing": ("正在处理", "處理中", "Processing", "処理中", "처리 중", "Выполняется", "Traitement en cours"),
    "log_live_elapsed": ("{detail} · 已用时 {elapsed}", "{detail} · 已用時 {elapsed}", "{detail} · Elapsed {elapsed}", "{detail} · 経過 {elapsed}", "{detail} · 경과 시간 {elapsed}", "{detail} · Прошло {elapsed}", "{detail} · Temps écoulé {elapsed}"),
    "queue_waiting": ("{count} 项等待中", "等待中：{count} 項", "{count} waiting", "{count} 件待機中", "대기 중 {count}개", "В очереди: {count}", "En attente : {count}"),
    "ready": ("已准备就绪，添加文件开始处理。", "已準備就緒，新增檔案即可開始處理。", "Ready. Add files to get started.", "準備完了です。ファイルを追加して開始してください。", "준비되었습니다. 파일을 추가해 시작하세요.", "Готово. Добавьте файлы, чтобы начать.", "Prêt. Ajoutez des fichiers pour commencer."),
    "cancel": ("取消", "取消", "Cancel", "キャンセル", "취소", "Отмена", "Annuler"),
    "conversion_failed": ("处理失败", "處理失敗", "Processing failed", "処理に失敗しました", "처리에 실패했습니다", "Ошибка обработки", "Échec du traitement"),
    "engine_no_output": ("转换引擎未生成输出文件", "轉換引擎未產生輸出檔案", "The conversion engine did not create an output file", "変換エンジンが出力ファイルを作成しませんでした", "변환 엔진이 출력 파일을 만들지 않았습니다", "Движок не создал выходной файл", "Le moteur n’a pas créé de fichier de sortie"),
    "ffmpeg_missing": ("未找到 FFmpeg 转换引擎。", "找不到 FFmpeg 轉換引擎。", "FFmpeg conversion engine was not found.", "FFmpeg 変換エンジンが見つかりません。", "FFmpeg 변환 엔진을 찾을 수 없습니다.", "Не найден движок FFmpeg.", "Le moteur FFmpeg est introuvable."),
    "office_missing": ("未找到 LibreOffice 文档引擎。", "找不到 LibreOffice 文件引擎。", "LibreOffice document engine was not found.", "LibreOffice 文書エンジンが見つかりません。", "LibreOffice 문서 엔진을 찾을 수 없습니다.", "Не найден движок LibreOffice.", "Le moteur LibreOffice est introuvable."),
    "model_disk_space": ("模型存储空间不足。", "模型儲存空間不足。", "Not enough storage space for the model.", "モデルを保存する空き容量が不足しています。", "모델을 저장할 공간이 부족합니다.", "Недостаточно места для модели.", "Espace de stockage insuffisant pour le modèle."),
    "pdf_memory_low": ("可用内存不足 {gb} GiB，请释放内存后重试。", "可用記憶體不足 {gb} GiB，請釋放記憶體後再試。", "At least {gb} GiB of available memory is required. Free memory and try again.", "使用可能なメモリが {gb} GiB 未満です。空き容量を確保して再試行してください。", "사용 가능한 메모리가 {gb}GiB 미만입니다. 메모리를 확보한 뒤 다시 시도하세요.", "Доступно менее {gb} ГиБ памяти. Освободите память и повторите попытку.", "Moins de {gb} Gio de mémoire disponible. Libérez de la mémoire puis réessayez."),
    "model_already_installed": ("模型已安装。", "模型已安裝。", "The model is already installed.", "モデルはすでにインストールされています。", "모델이 이미 설치되어 있습니다.", "Модель уже установлена.", "Le modèle est déjà installé."),
    "pdf_no_text": ("第 {page} 页没有文字层。默认识别模型尚未下载，请到设置下载模型后重试。", "第 {page} 頁沒有文字層。預設辨識模型尚未下載，請到設定下載模型後重試。", "Page {page} has no text layer. Download the default recognition model in Settings and retry.", "{page} ページにテキストレイヤーがありません。設定から既定の認識モデルをダウンロードして再試行してください。", "{page}페이지에 텍스트 레이어가 없습니다. 설정에서 기본 인식 모델을 다운로드한 뒤 다시 시도하세요.", "На странице {page} нет текстового слоя. Скачайте модель распознавания в настройках и повторите попытку.", "La page {page} ne contient pas de couche de texte. Téléchargez le modèle par défaut dans les réglages, puis réessayez."),
    "pdf_no_tables": ("没有检测到可提取的表格。", "沒有偵測到可擷取的表格。", "No extractable tables were found.", "抽出できる表が見つかりませんでした。", "추출할 수 있는 표가 없습니다.", "Не найдено таблиц для извлечения.", "Aucun tableau à extraire n’a été trouvé."),
    "settings_intro": ("管理语言、识别模型和转换引擎。", "管理語言、辨識模型與轉換引擎。", "Manage language, recognition model, and conversion engines.", "言語、認識モデル、変換エンジンを管理します。", "언어, 인식 모델 및 변환 엔진을 관리합니다.", "Управление языком, моделью распознавания и движками.", "Gérez la langue, le modèle de reconnaissance et les moteurs."),
    "language_title": ("语言", "語言", "Language", "言語", "언어", "Язык", "Langue"),
    "language_hint": ("首次启动时会根据电脑系统语言自动选择。", "首次啟動時會依照電腦系統語言自動選擇。", "On first launch, the system language is selected automatically.", "初回起動時は、システムの言語が自動的に選択されます。", "처음 실행할 때 시스템 언어를 자동으로 선택합니다.", "При первом запуске язык выбирается по настройкам системы.", "Au premier lancement, la langue du système est sélectionnée automatiquement."),
    "web_browser": ("打开网页的浏览器", "開啟網頁的瀏覽器", "Browser for web links", "リンクを開くブラウザー", "링크를 열 브라우저", "Браузер для ссылок", "Navigateur pour les liens"),
    "browser_system": ("跟随系统默认", "跟隨系統預設", "System default", "システムの既定", "시스템 기본값", "Системный по умолчанию", "Par défaut du système"),
    "language_label": ("界面语言", "介面語言", "Interface language", "表示言語", "인터페이스 언어", "Язык интерфейса", "Langue de l’interface"),
    "video_acceleration_title": ("视频硬件加速", "影片硬體加速", "Video hardware acceleration", "動画のハードウェアアクセラレーション", "동영상 하드웨어 가속", "Аппаратное ускорение видео", "Accélération vidéo matérielle"),
    "video_acceleration_hint": ("优先使用显卡，不支持或失败时自动切换 CPU。", "優先使用顯示卡，不支援或失敗時自動切換 CPU。", "Uses the GPU when supported; falls back to CPU on failure.", "GPU を優先し、非対応または失敗時は CPU に切り替えます。", "GPU를 우선 사용하며, 미지원 또는 실패 시 CPU로 전환합니다.", "Приоритет GPU. Если он недоступен или произошла ошибка, используется CPU.", "Priorité au GPU ; passage au CPU si non pris en charge ou en cas d’échec."),
    "video_acceleration": ("音视频处理方式", "音視頻處理方式", "Audio/video processing", "音声・動画の処理方法", "오디오/동영상 처리 방식", "Обработка аудио и видео", "Traitement audio/vidéo"),
    "gpu_auto": ("自动选择", "自動選擇", "Automatic", "自動選択", "자동 선택", "Автоматически", "Automatique"),
    "gpu_gpu": ("优先使用显卡", "優先使用顯示卡", "Prefer GPU", "GPU を優先", "GPU 우선", "Предпочитать GPU", "Privilégier le GPU"),
    "gpu_cpu": ("仅使用 CPU", "僅使用 CPU", "CPU only", "CPU のみ", "CPU만 사용", "Только CPU", "CPU uniquement"),
    "about_title": ("关于本软件", "關於本軟體", "About this app", "このアプリについて", "앱 정보", "О приложении", "À propos"),
    "about_hint": ("软件版本、运行平台与项目主页。", "軟體版本、執行平台與專案首頁。", "App version, platform, and project home.", "アプリのバージョン、実行環境、プロジェクトページです。", "앱 버전, 실행 플랫폼 및 프로젝트 홈페이지입니다.", "Версия приложения, платформа и страница проекта.", "Version, plateforme et page du projet."),
    "about_product": ("软件名称", "軟體名稱", "App name", "アプリ名", "앱 이름", "Название приложения", "Nom de l’application"),
    "about_version": ("软件版本", "軟體版本", "App version", "バージョン", "앱 버전", "Версия приложения", "Version de l’application"),
    "about_platform": ("运行平台", "執行平台", "Platform", "実行環境", "플랫폼", "Платформа", "Plateforme"),
    "about_project": ("GitHub 项目主页", "GitHub 專案首頁", "GitHub project", "GitHub プロジェクト", "GitHub 프로젝트", "Проект на GitHub", "Projet GitHub"),
    "development_build": ("开发版（未打包）", "開發版（未封裝）", "Development build", "開発版（未パッケージ）", "개발 빌드", "Версия для разработки", "Version de développement"),
    "video_gpu_unavailable": ("当前格式不支持显卡编码或没有可用显卡编码器，本次使用 CPU。", "目前格式不支援顯示卡編碼或沒有可用的顯示卡編碼器，本次使用 CPU。", "This format has no usable GPU encoder, so this task will use the CPU.", "この形式に対応する GPU エンコーダーがないため、CPU で処理します。", "이 형식에 사용할 수 있는 GPU 인코더가 없어 CPU로 처리합니다.", "Для этого формата нет подходящего кодировщика GPU. Используется CPU.", "Aucun encodeur GPU adapté à ce format. Le CPU sera utilisé."),
    "video_gpu_fallback": ("显卡编码器启动失败，正在自动改用 CPU 继续处理。", "顯示卡編碼器啟動失敗，正在自動改用 CPU 繼續處理。", "The GPU encoder failed to start. Retrying with the CPU.", "GPU エンコーダーを起動できなかったため、CPU に切り替えて再試行します。", "GPU 인코더를 시작하지 못해 CPU로 전환하여 다시 시도합니다.", "Не удалось запустить кодировщик GPU. Повторная попытка на CPU.", "L’encodeur GPU n’a pas démarré. Nouvelle tentative avec le CPU."),
    "model_title": ("PDF 扫描页识别", "PDF 掃描頁辨識", "PDF scan recognition", "PDF スキャン認識", "PDF 스캔 인식", "Распознавание сканов PDF", "Reconnaissance des scans PDF"),
    "model_hint": ("鼠标悬停模型名称可查看用途；模型按需下载。", "將滑鼠停在模型名稱上可查看用途；模型依需求下載。", "Hover over a model name to see its use. Models download on demand.", "モデル名にカーソルを合わせると用途を表示します。モデルは必要時にダウンロードします。", "모델 이름에 마우스를 올리면 용도를 볼 수 있습니다. 모델은 필요할 때 다운로드합니다.", "Наведите указатель на модель, чтобы узнать её назначение. Модели загружаются по запросу.", "Survolez un nom de modèle pour voir son usage. Les modèles sont téléchargés à la demande."),
    "model_desc_smoldocling": ("轻量英文文档解析模型；中文可能有明显错字，复杂表格需核对。许可：CDLA-Permissive-2.0。", "輕量英文文件解析模型；中文可能有明顯錯字，複雜表格需核對。授權：CDLA-Permissive-2.0。", "Lightweight English document parser; verify Chinese text and complex tables carefully. License: CDLA-Permissive-2.0.", "低スペック PC 向けの軽量文書解析モデルです。読み順に構造化します。ライセンス：CDLA-Permissive-2.0。", "저사양 PC용 경량 문서 분석 모델입니다. 읽기 순서대로 구조화합니다. 라이선스: CDLA-Permissive-2.0.", "Лёгкая модель разбора документов для обычных ПК; сохраняет порядок чтения. Лицензия: CDLA-Permissive-2.0.", "Modèle léger pour PC modestes, avec respect de l’ordre de lecture. Licence : CDLA-Permissive-2.0."),
    "model_desc_smolvlm-500m": ("轻量通用视觉模型，主要面向英文；不推荐用于中文扫描文档和复杂表格。Apache-2.0。", "輕量通用視覺模型，主要面向英文；不建議用於中文掃描文件和複雜表格。Apache-2.0。", "Lightweight general vision model, primarily English; not recommended for Chinese scans or complex tables. Apache-2.0.", "スキャン向けの軽量画像・テキストモデルです。複雑な表やレイアウトは苦手です。Apache-2.0。", "스캔 페이지용 경량 이미지·텍스트 모델입니다. 복잡한 표와 레이아웃은 정확도가 낮을 수 있습니다. Apache-2.0.", "Компактная модель для сканов; сложные таблицы и макеты распознаёт хуже. Apache-2.0.", "Modèle léger pour les scans ; les tableaux et mises en page complexes sont moins bien gérés. Apache-2.0."),
    "model_desc_pp-ocrv5-mobile": ("低内存 CPU 识别：自动检测文字行并识别简繁中文，支持有框线的表格。", "低記憶體 CPU 辨識：偵測文字行並辨識簡繁中文，支援有框線的表格。", "Low-memory CPU OCR for text detection, Chinese recognition, and ruled tables.", "CPU 向け軽量 OCR。中国語の検出・認識と罫線表に対応。", "저메모리 CPU용 중국어 검출·인식 및 테두리 표 처리.", "Лёгкое распознавание китайского текста и таблиц с границами на CPU.", "OCR léger sur CPU pour les lignes de texte chinois et les tableaux avec bordures."),
    "model_desc_deepseek-ocr": ("扫描页文字与表格识别。需要支持 BF16 的 NVIDIA CUDA 显卡，运行时可用显存至少 8 GiB。", "掃描頁文字與表格辨識。需要支援 BF16 的 NVIDIA CUDA 顯示卡及至少 8 GiB 可用顯示記憶體。", "Scanned text and tables. Requires a BF16-capable NVIDIA CUDA GPU with 8 GiB of free VRAM.", "スキャン文書用。BF16 対応の NVIDIA CUDA GPU と空き VRAM 8 GiB が必要です。", "스캔 문서용. BF16 지원 NVIDIA CUDA GPU와 8 GiB의 여유 VRAM이 필요합니다.", "Для сканов. Требуется NVIDIA CUDA с BF16 и 8 GiB свободной видеопамяти.", "Pour les pages numérisées. GPU NVIDIA CUDA compatible BF16 avec 8 GiB de VRAM libre requis."),
    "deepseek_gpu_required": ("DeepSeek-OCR 需要支持 BF16 的 NVIDIA CUDA 显卡及 {gb} GiB 可用显存。", "DeepSeek-OCR 需要支援 BF16 的 NVIDIA CUDA 顯示卡及 {gb} GiB 可用顯示記憶體。", "DeepSeek-OCR requires a BF16-capable NVIDIA CUDA GPU with {gb} GiB of free VRAM.", "BF16 対応の NVIDIA CUDA GPU と空き VRAM {gb} GiB が必要です。", "BF16 지원 NVIDIA CUDA GPU와 {gb} GiB의 여유 VRAM이 필요합니다.", "Требуется NVIDIA CUDA с BF16 и {gb} GiB свободной видеопамяти.", "GPU NVIDIA CUDA compatible BF16 et {gb} GiB de VRAM libre requis."),
    "model_desc_granite-docling-258m": ("258M 轻量文档转换模型，输出带结构的 Docling 标记；中文支持为实验性，Apache-2.0。", "258M 輕量文件轉換模型，輸出具結構的 Docling 標記；中文支援為實驗性，Apache-2.0。", "A lightweight 258M document conversion model that outputs structured Docling tags. Chinese is experimental. Apache-2.0.", "258M の軽量文書変換モデルで、構造化 Docling タグを出力します。中国語対応は実験段階です。Apache-2.0。", "258M 경량 문서 변환 모델로 구조화된 Docling 태그를 출력합니다. 중국어 지원은 실험 단계입니다. Apache-2.0.", "Лёгкая модель преобразования документов на 258M параметров с разметкой Docling. Китайский язык поддерживается экспериментально. Apache-2.0.", "Modèle léger de conversion de documents (258M) avec balises Docling structurées. Le chinois est expérimental. Apache-2.0."),
    "model_desc_paddleocr-vl-1.6": ("约 1B 参数，侧重中文扫描件、表格、公式和印章；模型约占 1.8 GiB。Apache-2.0。", "約 1B 參數，著重中文掃描件、表格、公式與印章；模型約佔 1.8 GiB。Apache-2.0。", "About 1B parameters for Chinese scans, tables, formulas, and stamps; about 1.8 GiB. Apache-2.0.", "約 10 億パラメーター。中国語スキャン、表、数式、印影向けです。約 1.8 GiB。Apache-2.0。", "약 10억 매개변수로 중국어 스캔, 표, 수식, 도장 인식에 중점을 둡니다. 약 1.8GiB. Apache-2.0.", "Около 1 млрд параметров; китайские сканы, таблицы, формулы и печати. Около 1,8 ГиБ. Apache-2.0.", "Environ 1 milliard de paramètres, axé sur les scans chinois, tableaux, formules et tampons ; environ 1,8 Gio. Apache-2.0."),
    "model_desc_glm-ocr": ("约 0.9B 参数，适合文字、表格和公式识别；完整页面布局分析还需额外引擎。MIT。", "約 0.9B 參數，適合文字、表格與公式辨識；完整頁面版面分析仍需額外引擎。MIT。", "About 0.9B parameters for text, tables, and formulas; full page-layout parsing needs another engine. MIT.", "約 9 億パラメーター。文字・表・数式の OCR 向けです。ページ全体の解析には別のエンジンが必要です。MIT。", "약 9억 매개변수로 텍스트, 표, 수식 OCR에 적합합니다. 전체 페이지 분석에는 별도 엔진이 필요합니다. MIT.", "Около 0,9 млрд параметров для текста, таблиц и формул; полный разбор макета требует отдельного движка. MIT.", "Environ 0,9 milliard de paramètres pour le texte, les tableaux et les formules ; l’analyse complète nécessite un autre moteur. MIT."),
    "model_desc_dots-ocr": ("多语言版面解析模型，可识别表格、公式并整理阅读顺序；体积较大，建议高内存或独显电脑。MIT。", "多語言版面解析模型，可辨識表格、公式並整理閱讀順序；體積較大，建議高記憶體或獨顯電腦。MIT。", "Multilingual layout parser for tables, formulas, and reading order. Larger; recommended for PCs with ample RAM or a dedicated GPU. MIT.", "多言語の文書レイアウト解析モデルです。表・数式・読み順を扱います。大容量のため、十分なメモリまたは GPU を推奨します。MIT。", "다국어 문서 레이아웃 모델로 표, 수식, 읽기 순서를 처리합니다. 용량이 커서 메모리나 전용 GPU가 충분한 PC에 권장합니다. MIT.", "Многоязычная модель макета: таблицы, формулы и порядок чтения. Крупная; рекомендуется ПК с большим объёмом ОЗУ или дискретной видеокартой. MIT.", "Modèle multilingue de mise en page : tableaux, formules et ordre de lecture. Volumineux, recommandé sur un PC bien équipé. MIT."),
    "model_homepage": ("前往模型主页", "前往模型首頁", "Visit model homepage", "モデルのホームページを開く", "모델 홈페이지로 이동", "Перейти на страницу модели", "Ouvrir la page du modèle"),
    "choose_model": ("选择模型", "選擇模型", "Select model", "モデルを選択", "모델 선택", "Выбрать модель", "Choisir un modèle"),
    "download_model": ("下载模型", "下載模型", "Download model", "モデルをダウンロード", "모델 다운로드", "Скачать модель", "Télécharger le modèle"),
    "delete_model": ("删除本地模型", "刪除本機模型", "Remove local model", "ローカルモデルを削除", "로컬 모델 삭제", "Удалить локальную модель", "Supprimer le modèle local"),
    "model_installed": ("已安装", "已安裝", "Installed", "インストール済み", "설치됨", "Установлена", "Installé"),
    "model_browser_handoff": ("请复制链接，在当前浏览器中打开，以保留已打开的窗口。", "請複製連結，在目前的瀏覽器中開啟，以保留現有視窗。", "Copy the link into your current browser to keep its windows open.", "リンクをコピーし、現在のブラウザーで開いてください。", "링크를 복사하여 현재 브라우저에서 여세요.", "Скопируйте ссылку и откройте её в текущем браузере.", "Copiez le lien dans votre navigateur actuel pour garder ses fenêtres ouvertes."),
    "copy_model_url": ("复制链接", "複製連結", "Copy link", "リンクをコピー", "링크 복사", "Скопировать ссылку", "Copier le lien"),
    "model_missing": ("尚未下载", "尚未下載", "Not downloaded", "未ダウンロード", "다운로드되지 않음", "Не загружена", "Non téléchargé"),
    "model_memory_info": ("所需内存 {ram}　·　GPU 模式所需显存 {vram}", "所需記憶體 {ram}　·　GPU 模式所需顯示記憶體 {vram}", "RAM required {ram} · GPU mode VRAM {vram}", "必要メモリ {ram} · GPU 使用時の VRAM {vram}", "필요 RAM {ram} · GPU 모드 VRAM {vram}", "ОЗУ {ram} · Видеопамять в режиме GPU {vram}", "RAM requise {ram} · VRAM en mode GPU {vram}"),
    "cuda_version": ("驱动支持的 CUDA：{version}", "驅動支援的 CUDA：{version}", "Driver CUDA support: {version}", "ドライバー対応 CUDA：{version}", "드라이버 CUDA 지원: {version}", "Поддержка CUDA драйвером: {version}", "CUDA pris en charge : {version}"),
    "cuda_absent": ("未检测到", "未偵測到", "Not detected", "未検出", "감지되지 않음", "Не обнаружена", "Non détecté"),
    "download_driver": ("下载 NVIDIA 驱动", "下載 NVIDIA 驅動", "Download NVIDIA driver", "NVIDIA ドライバーをダウンロード", "NVIDIA 드라이버 다운로드", "Скачать драйвер NVIDIA", "Télécharger le pilote NVIDIA"),
    "model_disk_size": ("模型文件约占用 {size} 硬盘空间", "模型檔案約佔用 {size} 硬碟空間", "Model files use about {size} of disk space", "モデルファイルの使用容量：約 {size}", "모델 파일 디스크 사용량: 약 {size}", "Файлы модели занимают около {size}", "Fichiers du modèle : environ {size}"),
    "open_model_folder": ("打开模型目录", "開啟模型目錄", "Open model folder", "モデルフォルダーを開く", "모델 폴더 열기", "Открыть папку модели", "Ouvrir le dossier du modèle"),
    "model_size_loading": ("正在获取模型硬盘占用…", "正在取得模型硬碟佔用…", "Checking model disk usage…", "モデルの容量を確認中…", "모델 디스크 사용량 확인 중…", "Проверка размера модели…", "Vérification de l’espace disque du modèle…"),
    "model_size_unavailable": ("暂时无法获取模型占用空间", "暫時無法取得模型佔用空間", "Model disk usage is currently unavailable", "現在、モデル容量を取得できません", "현재 모델 디스크 사용량을 확인할 수 없습니다", "Размер модели пока недоступен", "Taille du modèle indisponible pour le moment"),
    "engine_title": ("软件与引擎更新", "軟體與引擎更新", "App and engine updates", "アプリとエンジンの更新", "앱 및 엔진 업데이트", "Обновления приложения и движков", "Mises à jour de l’application et des moteurs"),
    "engine_hint": ("安装包包含与此设备匹配的运行引擎。应用更新会在下载后自动安装。", "安裝包包含與此裝置相符的執行引擎。應用程式更新會在下載後自動安裝。", "This package includes engines for this device. App updates install automatically after download.", "この端末に合ったエンジンを含みます。アプリの更新はダウンロード後に自動でインストールされます。", "이 장치에 맞는 엔진이 포함됩니다. 앱 업데이트는 다운로드 후 자동으로 설치됩니다.", "Пакет содержит движки для этого устройства. Обновление приложения устанавливается автоматически после загрузки.", "Ce paquet inclut les moteurs adaptés à cet appareil. Les mises à jour s’installent automatiquement après le téléchargement."),
    "engine_update_note": ("转换引擎随完整安装包一起更新。", "轉換引擎會隨完整安裝包一併更新。", "Conversion engines update with the full installer.", "変換エンジンは完全版インストーラーで更新します。", "변환 엔진은 전체 설치 프로그램으로 업데이트됩니다.", "Движки обновляются вместе с полным установщиком.", "Les moteurs sont mis à jour avec l’installeur complet."),
    "check_engine": ("检查更新", "檢查更新", "Check for updates", "更新を確認", "업데이트 확인", "Проверить обновления", "Rechercher des mises à jour"),
    "checking_engine": ("正在查询引擎版本…", "正在查詢引擎版本…", "Checking engine version…", "エンジンのバージョンを確認中…", "엔진 버전 확인 중…", "Проверка версии движка…", "Vérification de la version du moteur…"),
    "engine_latest": ("引擎已是最新版本", "引擎已是最新版本", "Engines are up to date", "エンジンは最新です", "엔진이 최신 버전입니다", "Установлены последние версии движков", "Les moteurs sont à jour"),
    "engine_update_available": ("可更新至 {version}", "可更新至 {version}", "Update available: {version}", "更新可能: {version}", "업데이트 가능: {version}", "Доступно обновление: {version}", "Mise à jour disponible : {version}"),
    "engine_download_question": ("下载 v{version} 完整安装包（{size:.0f} MiB）？", "下載 v{version} 完整安裝包（{size:.0f} MiB）？", "Download the full v{version} installer ({size:.0f} MiB)?", "v{version} の完全版インストーラー（{size:.0f} MiB）をダウンロードしますか？", "전체 v{version} 설치 프로그램({size:.0f} MiB)을 다운로드할까요?", "Скачать полный установщик v{version} ({size:.0f} МиБ)?", "Télécharger l’installeur complet v{version} ({size:.0f} Mio) ?"),
    "engine_download_status": ("正在下载安装包并校验…", "正在下載安裝包並驗證…", "Downloading and verifying installer…", "インストーラーをダウンロードして検証中…", "설치 프로그램 다운로드 및 검증 중…", "Загрузка и проверка установщика…", "Téléchargement et vérification de l’installeur…"),
    "engine_downloaded": ("安装包已校验，正在启动更新。", "安裝包已驗證，正在啟動更新。", "Installer verified. Starting the update…", "インストーラーを検証しました。更新を開始します…", "설치 프로그램을 확인했습니다. 업데이트를 시작합니다…", "Установщик проверен. Запускается обновление…", "Installeur vérifié. Démarrage de la mise à jour…"),
    "app_update_installing": ("更新包已校验，正在安装并重启软件…", "更新包已驗證，正在安裝並重新啟動軟體…", "Update verified. Installing and restarting Formix…", "更新を確認しました。インストールして Formix を再起動します…", "업데이트를 확인했습니다. 설치 후 Formix를 다시 시작합니다…", "Обновление проверено. Установка и перезапуск Formix…", "Mise à jour vérifiée. Installation et redémarrage de Formix…"),
    "app_update_launch_failed": ("无法启动自动更新，请在缓存目录中手动运行安装包。", "無法啟動自動更新，請在快取目錄中手動執行安裝包。", "Could not start the automatic update. Run the verified package from the cache folder.", "自動更新を開始できません。キャッシュ内のパッケージを手動で実行してください。", "자동 업데이트를 시작할 수 없습니다. 캐시 폴더에서 확인된 패키지를 직접 실행하세요.", "Не удалось запустить автообновление. Запустите проверенный пакет из папки кэша.", "Impossible de lancer la mise à jour automatique. Exécutez le paquet vérifié depuis le cache."),
    "app_update_packaged_only": ("源码运行环境不支持自动安装，请在缓存目录中手动运行安装包。", "原始碼執行環境不支援自動安裝，請在快取目錄中手動執行安裝包。", "Automatic installation is unavailable from a source checkout. Run the package from the cache folder.", "ソース実行環境では自動インストールできません。キャッシュ内のパッケージを実行してください。", "소스 실행 환경에서는 자동 설치를 사용할 수 없습니다. 캐시 폴더에서 패키지를 실행하세요.", "Автоустановка недоступна из исходной копии. Запустите пакет из папки кэша.", "L’installation automatique est indisponible depuis les sources. Exécutez le paquet depuis le cache."),
    "app_update_linux_permissions": ("Linux 安装目录不可写，且未找到 pkexec。请使用管理员权限更新。", "Linux 安裝目錄無法寫入，且找不到 pkexec。請使用管理員權限更新。", "The Linux install folder is not writable and pkexec is unavailable. Update with administrator access.", "Linux のインストール先に書き込めず、pkexec もありません。管理者権限で更新してください。", "Linux 설치 폴더에 쓸 수 없고 pkexec도 없습니다. 관리자 권한으로 업데이트하세요.", "Каталог Linux недоступен для записи, а pkexec не найден. Обновите приложение с правами администратора.", "Le dossier Linux n’est pas accessible en écriture et pkexec est absent. Mettez à jour avec les droits administrateur."),
    "update_changed": ("发行版本已变更，请重新检查更新", "發行版本已變更，請重新檢查更新", "The release changed. Check for updates again.", "リリースが更新されました。もう一度確認してください。", "릴리스가 변경되었습니다. 업데이트를 다시 확인하세요.", "Релиз изменился. Проверьте обновления ещё раз.", "La version a changé. Recherchez à nouveau les mises à jour."),
    "update_bad_hash": ("安装包完整性检查失败", "安裝包完整性檢查失敗", "Installer integrity check failed", "インストーラーの整合性チェックに失敗しました", "설치 프로그램 무결성 확인 실패", "Проверка целостности установщика не пройдена", "Échec de la vérification d’intégrité de l’installeur"),
    "model_components_missing": ("当前是源码运行环境。请先按 README 安装 requirements-model.txt 中的依赖。", "目前是原始碼執行環境。請先依照 README 安裝 requirements-model.txt 中的相依套件。", "This is a source checkout. Install the requirements in requirements-model.txt first; see README.", "ソース実行環境です。README に従って requirements-model.txt の依存関係を先にインストールしてください。", "소스 실행 환경입니다. README에 따라 requirements-model.txt의 종속 항목을 먼저 설치하세요.", "Запущена исходная версия. Сначала установите зависимости из requirements-model.txt по инструкции в README.", "L’application est lancée depuis les sources. Installez d’abord les dépendances de requirements-model.txt comme indiqué dans README."),
    "model_querying": ("正在查询下载大小……", "正在查詢下載大小……", "Checking download size…", "ダウンロードサイズを確認中…", "다운로드 크기 확인 중…", "Проверка размера загрузки…", "Vérification de la taille du téléchargement…"),
    "model_download_title": ("下载识别模型", "下載辨識模型", "Download recognition model", "認識モデルをダウンロード", "인식 모델 다운로드", "Скачать модель распознавания", "Télécharger le modèle de reconnaissance"),
    "model_download_question": ("从模型仓库下载 {model}（约 {size:.0f} MB）到本机？", "從模型儲存庫下載 {model}（約 {size:.0f} MB）到本機？", "Download {model} from the model repository (about {size:.0f} MB)?", "モデルリポジトリから {model}（約 {size:.0f} MB）をダウンロードしますか？", "모델 저장소에서 {model}(약 {size:.0f}MB)을 다운로드할까요?", "Скачать {model} из хранилища моделей (около {size:.0f} МБ)?", "Télécharger {model} depuis le dépôt (environ {size:.0f} Mo) ?"),
    "model_manager": ("模型管理", "模型管理", "Model manager", "モデル管理", "모델 관리자", "Управление моделями", "Gestion des modèles"),
    "model_size_error": ("无法获取模型大小，请检查网络后重试。", "無法取得模型大小，請檢查網路後再試。", "Could not get the model size. Check your connection and try again.", "モデルサイズを取得できません。ネットワークを確認して再試行してください。", "모델 크기를 확인할 수 없습니다. 네트워크를 확인하고 다시 시도하세요.", "Не удалось получить размер модели. Проверьте сеть и повторите попытку.", "Impossible d’obtenir la taille du modèle. Vérifiez le réseau et réessayez."),
    "model_busy": ("当前有任务运行，请完成后再删除模型。", "目前有工作正在執行，請完成後再刪除模型。", "A task is running. Finish it before removing the model.", "タスク実行中です。完了後にモデルを削除してください。", "작업이 실행 중입니다. 완료된 뒤 모델을 삭제하세요.", "Дождитесь завершения задачи, прежде чем удалять модель.", "Attendez la fin de la tâche avant de supprimer le modèle."),
    "model_remove_question": ("移除本机已下载的视觉模型？", "移除本機已下載的視覺模型？", "Remove the downloaded vision model from this device?", "ダウンロード済みの視覚モデルを削除しますか？", "이 장치에서 다운로드한 비전 모델을 제거할까요?", "Удалить загруженную визуальную модель с устройства?", "Supprimer le modèle visuel téléchargé de cet appareil ?"),
    "task_model_download": ("下载 PDF 识别模型", "下載 PDF 辨識模型", "Download PDF recognition model", "PDF 認識モデルをダウンロード", "PDF 인식 모델 다운로드", "Загрузка модели распознавания PDF", "Télécharger le modèle de reconnaissance PDF"),
    "task_processing": ("{file}   ·   正在处理   ·   等待 {count} 项", "{file}   ·   正在處理   ·   等待 {count} 項", "{file}   ·   Processing   ·   {count} waiting", "{file}   ·   処理中   ·   待機 {count} 件", "{file}   ·   처리 중   ·   대기 {count}개", "{file}   ·   Обработка   ·   в очереди {count}", "{file}   ·   Traitement   ·   {count} en attente"),
    "task_cancelled": ("已取消", "已取消", "Cancelled", "キャンセルしました", "취소됨", "Отменено", "Annulé"),
    "model_downloaded": ("下载完成", "下載完成", "Download complete", "ダウンロード完了", "다운로드 완료", "Загрузка завершена", "Téléchargement terminé"),
    "saved_to": ("已保存至 {path}", "已儲存至 {path}", "Saved to {path}", "保存先: {path}", "저장 위치: {path}", "Сохранено: {path}", "Enregistré dans {path}"),
    "task_result": ("{file}   ·   {result}", "{file}   ·   {result}", "{file}   ·   {result}", "{file}   ·   {result}", "{file}   ·   {result}", "{file}   ·   {result}", "{file}   ·   {result}"),
    "option.light": ("轻度", "輕度", "Light", "軽い", "낮음", "Лёгкое", "Léger"),
    "option.balanced": ("均衡", "均衡", "Balanced", "標準", "보통", "Сбалансированное", "Équilibré"),
    "option.strong": ("强力", "強力", "Strong", "強い", "강함", "Сильное", "Renforcé"),
    "option.audio": ("提取音频 · m4a", "擷取音訊 · m4a", "Extract audio · m4a", "音声を抽出 · m4a", "오디오 추출 · m4a", "Извлечь аудио · m4a", "Extraire l’audio · m4a"),
    "option.video": ("提取视频 · mkv", "擷取影片 · mkv", "Extract video · mkv", "動画を抽出 · mkv", "비디오 추출 · mkv", "Извлечь видео · mkv", "Extraire la vidéo · mkv"),
}


def system_language():
    locale = QLocale.system()
    name = locale.name().replace("-", "_").lower()
    if name.startswith("zh"):
        return "zh_TW" if any(part in name for part in ("tw", "hk", "mo", "hant")) else "zh_CN"
    if name.startswith("ja"):
        return "ja"
    if name.startswith("ko"):
        return "ko"
    if name.startswith("ru"):
        return "ru"
    if name.startswith("fr"):
        return "fr"
    return "en"


class LanguageManager(QObject):
    changed = Signal(str)

    def __init__(self, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("Formix", "Formix")
        saved = self.settings.value("interface/language", "", type=str)
        self.code = saved if saved in LANGUAGE_CODES else system_language()

    def set_language(self, code):
        if code not in LANGUAGE_CODES or code == self.code:
            return
        self.code = code
        self.settings.setValue("interface/language", code)
        self.changed.emit(code)

    def t(self, key, **values):
        row = TEXT.get(key)
        if row is None:
            return key
        result = row[LANGUAGE_CODES.index(self.code)]
        return result.format(**values) if values else result

    def bind(self, widget, key, attribute="text"):
        widget.setProperty("translationKey", key)
        widget.setProperty("translationAttribute", attribute)
        self._set_widget(widget, key, attribute)
        return widget

    def retranslate(self, root):
        widgets = [root, *root.findChildren(QWidget)]
        for widget in widgets:
            key = widget.property("translationKey")
            if key:
                self._set_widget(widget, key, widget.property("translationAttribute") or "text")
            if isinstance(widget, QComboBox):
                for index in range(widget.count()):
                    item_key = widget.itemData(index, Qt.ItemDataRole.UserRole + 3)
                    if item_key:
                        detail = widget.itemData(index, Qt.ItemDataRole.UserRole + 4)
                        text = self.t(item_key)
                        widget.setItemText(index, text + (f" · {detail}" if detail else ""))

    def _set_widget(self, widget, key, attribute):
        value = self.t(key)
        if attribute == "placeholder":
            widget.setPlaceholderText(value)
        elif attribute == "toolTip":
            widget.setToolTip(value)
        elif isinstance(widget, (QCheckBox, QLabel, QPushButton, QLineEdit)):
            widget.setText(value)

